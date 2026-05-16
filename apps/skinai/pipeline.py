"""Skin AI analysis pipeline.

Pipeline versioning:
  Bumped whenever the scoring shape changes (new metric added, math
  meaningfully retuned). Persisted on SkinAnalysis.pipeline_version
  so the serializer and result UI can hide categories the row was
  never scored on. Increment when adding a metric or restructuring;
  threshold-only tunes don't need a version bump.

    v1 — original 5 metrics (hydration/pores/wrinkles/redness/spots)
    v2 — adds pigmentation/acne/dark_circles/eyebags/white_spots,
         face-ROI center crop, sex-aware threshold factors
    v3 — mediapipe FaceMesh landmarks: precise face bbox crop +
         dedicated under-eye region for dark_circles + eyebags

Pure-Python (Pillow + numpy + DeepFace) pipeline producing a
structured skin report from a single face photo. No OpenCV — the
cv2 wheel needs system libs (libxcb / libgl / glib) that aren't
on Railway's minimal Nix containers, and fighting LD_LIBRARY_PATH
across the venv boundary wasn't worth it for the four filter-and-
colourspace operations we actually need.

Operations replaced:
  cv2.cvtColor BGR2GRAY  →  weighted-sum numpy
  cv2.cvtColor BGR2LAB   →  sRGB → linear → XYZ (D65) → LAB, numpy
  cv2.cvtColor BGR2HSV   →  vectorised numpy
  cv2.GaussianBlur       →  PIL.ImageFilter.GaussianBlur
  cv2.Canny              →  Sobel-magnitude threshold (close enough
                            for an edge-density proxy)
  cv2.Laplacian.var      →  4-neighbour Laplacian kernel, numpy

DeepFace is still in play for age estimation. We call it with
detector_backend='skip' + enforce_detection=False, which means
DeepFace uses the WHOLE image as the face — the app's capture
flow already enforces a face-fills-the-frame photo via the
front-camera selfie + sharpness gate. This also avoids DeepFace's
cv2-based detectors which would re-trip the libxcb issue.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

# Must be set BEFORE tensorflow / deepface are imported. DeepFace
# 0.0.93 was written against the standalone `keras` package; TF 2.16+
# ships its own `keras` shim that's not 100% compatible.
os.environ.setdefault('TF_USE_LEGACY_KERAS', '1')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS', '1')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS', '1')

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from . import landmarks as _landmarks

logger = logging.getLogger(__name__)

# Bumped each time the analysis pipeline gains/changes a metric — see
# the module docstring. AnalyzeView writes this onto every new
# SkinAnalysis row so older rows render with fewer categories instead
# of pretending they were scored on the newer ones.
CURRENT_PIPELINE_VERSION = 3

_DEEPFACE = None


def _load_deps():
    """Import DeepFace on first use. Raises RuntimeError with a
    friendly message if TF/DeepFace aren't installed (lets the view
    layer return 503 instead of 500)."""
    global _DEEPFACE
    if _DEEPFACE is None:
        try:
            from deepface import DeepFace
        except Exception as exc:
            raise RuntimeError(
                'Skin AI dependencies are not installed on this server. '
                f'Underlying error: {exc!r}'
            ) from exc
        _DEEPFACE = DeepFace
    return _DEEPFACE


# ── Helpers (numpy/PIL replacements for the cv2 ops we used) ───────

def _decode_rgb(image_bytes: bytes) -> np.ndarray:
    """Decode bytes → uint8 RGB numpy array with EXIF rotation applied.

    Phones store selfies in sensor orientation with an EXIF tag; PIL
    won't auto-rotate. Without exif_transpose the analysis pipeline
    operates on a sideways image — face-ROI crop misses the face,
    edge density picks up rotated hair instead of forehead, etc.
    Thumbnail + normalize_original already do this; bringing analysis
    inline closes the gap."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert('RGB')
    return np.array(img)


def _rgb_to_gray(rgb: np.ndarray) -> np.ndarray:
    """ITU-R BT.601 luma. uint8 in → uint8 out."""
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return rgb.astype(np.float32).dot(weights).clip(0, 255).astype(np.uint8)


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (D65) → CIE L*a*b*. Returns float ndarray with L in
    [0, 100] and a,b roughly in [-128, 127]. Standard conversion:
    sRGB → linear-RGB → XYZ (D65 reference white) → LAB."""
    r = rgb.astype(np.float32) / 255.0
    # Inverse sRGB companding.
    mask = r > 0.04045
    lin = np.where(mask, ((r + 0.055) / 1.055) ** 2.4, r / 12.92)
    # Linear sRGB → XYZ. Matrix from IEC 61966-2-1.
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ], dtype=np.float32)
    xyz = lin @ M.T
    # Normalize by D65 white point.
    Xn, Yn, Zn = 0.95047, 1.00000, 1.08883
    xyz[..., 0] /= Xn
    xyz[..., 1] /= Yn
    xyz[..., 2] /= Zn
    delta = 6.0 / 29.0
    delta3 = delta ** 3
    mask = xyz > delta3
    f = np.where(
        mask,
        np.cbrt(xyz),
        xyz / (3 * delta * delta) + 4.0 / 29.0,
    )
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """uint8 RGB → float HSV with H in [0,360), S,V in [0,1]."""
    r = rgb[..., 0].astype(np.float32) / 255.0
    g = rgb[..., 1].astype(np.float32) / 255.0
    b = rgb[..., 2].astype(np.float32) / 255.0
    mx = np.max(rgb, axis=-1).astype(np.float32) / 255.0
    mn = np.min(rgb, axis=-1).astype(np.float32) / 255.0
    diff = mx - mn
    # Hue
    h = np.zeros_like(mx)
    mask_r = (mx == r) & (diff > 0)
    mask_g = (mx == g) & (diff > 0)
    mask_b = (mx == b) & (diff > 0)
    h = np.where(mask_r, ((g - b) / np.where(diff == 0, 1, diff)) % 6, h)
    h = np.where(mask_g, ((b - r) / np.where(diff == 0, 1, diff)) + 2, h)
    h = np.where(mask_b, ((r - g) / np.where(diff == 0, 1, diff)) + 4, h)
    h *= 60.0
    s = np.where(mx == 0, 0, diff / np.where(mx == 0, 1, mx))
    return np.stack([h, s, mx], axis=-1)


def _gaussian_blur(gray: np.ndarray, radius: float = 1.5) -> np.ndarray:
    """PIL-backed 2D Gaussian. Fast, doesn't need scipy."""
    pil = Image.fromarray(gray)
    blurred = pil.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.array(blurred)


def _edge_density(gray: np.ndarray) -> float:
    """Sobel-magnitude threshold → fraction of "edge" pixels in
    [0,1]. Pillow's Sobel-like FIND_EDGES is roughly equivalent to
    OpenCV's Canny on smooth skin, which is what we want for a
    wrinkle proxy."""
    pil = Image.fromarray(gray)
    edges = np.array(pil.filter(ImageFilter.FIND_EDGES))
    # FIND_EDGES leaves the border at zero — clip the 1px frame so
    # it doesn't skew the mean down.
    if edges.shape[0] > 4 and edges.shape[1] > 4:
        inner = edges[2:-2, 2:-2]
    else:
        inner = edges
    return float(inner.mean()) / 255.0


def _laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian — the classic blur /
    texture metric. Higher → more high-frequency detail (sharper or
    more textured)."""
    g = gray.astype(np.float32)
    # Pad with edge replication so the kernel fires over the border.
    pad = np.pad(g, 1, mode='edge')
    lap = (pad[:-2, 1:-1] + pad[2:, 1:-1] +
           pad[1:-1, :-2] + pad[1:-1, 2:] - 4 * pad[1:-1, 1:-1])
    return float(lap.var())


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _score(v: float) -> int:
    return int(round(_clamp01(v) * 100))


def _crop_to_face_roi(rgb: np.ndarray) -> np.ndarray:
    """Crop the image to a face-shaped center ROI before scoring.

    Without proper landmark detection the next-best move for accuracy
    is to throw away the obvious non-skin pixels (hair, neck, shoulder,
    background) by trimming to a centered rectangle that approximates
    where the face actually sits in a phone selfie.

    Picks the central 70% horizontally and the central 80% vertically
    biased a touch upward (faces in selfies sit ~5% above center on
    average). Returns a contiguous copy so downstream numpy ops can't
    write into the original. Falls back to the input on degenerate
    sizes."""
    h, w = rgb.shape[:2]
    if h < 100 or w < 100:
        return rgb
    crop_h = int(h * 0.80)
    crop_w = int(w * 0.70)
    # Pull the top edge up by 5% of height so chin + neck get clipped
    # more aggressively than forehead.
    top = max(0, (h - crop_h) // 2 - int(h * 0.05))
    bottom = min(h, top + crop_h)
    left = (w - crop_w) // 2
    right = left + crop_w
    return np.ascontiguousarray(rgb[top:bottom, left:right])


def _resize_for_analysis(rgb: np.ndarray, max_side: int = 768) -> np.ndarray:
    """Cap the long edge so analysis cost stays predictable. 768 is
    a sweet spot — plenty of detail for skin metrics, fast on CPU."""
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return rgb
    scale = max_side / longest
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    pil = Image.fromarray(rgb).resize((new_w, new_h), Image.LANCZOS)
    return np.array(pil)


# ── Public API ─────────────────────────────────────────────────────

def analyse(image_bytes: bytes, sex_hint: str = '') -> dict:
    """Run the full skin-AI pipeline on raw image bytes.

    Args:
      image_bytes: raw JPEG/PNG bytes from the upload.
      sex_hint:   optional 'male' / 'female' / '' from the user's
                  skin profile. Nudges a couple of thresholds —
                  men's skin reads thicker / oilier at the same
                  numeric metric, so we ease the pores penalty;
                  women's skin shows finer-line detail earlier, so
                  we ease the wrinkles penalty for younger ages.

    Returns a dict matching SkinAnalysis fields, plus a `raw_results`
    sub-dict with debug metrics and a `low_confidence` flag (True when
    DeepFace couldn't read an age — usually means face wasn't found).
    Higher scores are always "better skin".

    Raises:
      ValueError — input image is unreadable / too small. Surfaced
        as 400 by the view layer.
      RuntimeError — ML deps missing. View returns 503.
    """
    DeepFace = _load_deps()
    rgb = _decode_rgb(image_bytes)
    if rgb.shape[0] < 80 or rgb.shape[1] < 80:
        raise ValueError(
            'Photo is too small — please retake closer to your face.'
        )

    # Trim to the actual face region before scoring. mediapipe
    # FaceMesh gives a precise bbox + under-eye region; if that
    # fails (no face detected, mediapipe missing) we fall back to
    # the static 70%×80% center crop. Under-eye region (when
    # available) drives the dark-circles + eyebags metrics later
    # in the pipeline.
    regions = _landmarks.detect_regions(rgb)
    crop_method = 'mediapipe'
    rgb_under_eye = None
    if regions is not None:
        fx1, fy1, fx2, fy2 = regions.face_bbox
        if fx2 > fx1 + 20 and fy2 > fy1 + 20:
            rgb_face = np.ascontiguousarray(rgb[fy1:fy2, fx1:fx2])
        else:
            rgb_face = _crop_to_face_roi(rgb)
            crop_method = 'mediapipe_bbox_too_small'
        ux1, uy1, ux2, uy2 = regions.under_eye_bbox
        if ux2 > ux1 + 10 and uy2 > uy1 + 5:
            rgb_under_eye = np.ascontiguousarray(rgb[uy1:uy2, ux1:ux2])
    else:
        rgb_face = _crop_to_face_roi(rgb)
        crop_method = 'center_crop_fallback'
    rgb_small = _resize_for_analysis(rgb_face, max_side=768)
    gray = _rgb_to_gray(rgb_small)
    lab = _rgb_to_lab(rgb_small)
    hsv = _rgb_to_hsv(rgb_small)

    # ── 1. Age estimation via DeepFace. detector_backend='skip'
    #       sidesteps DeepFace's cv2-based face detectors and uses
    #       the input image as-is. The capture flow already enforces
    #       a face-fills-the-frame selfie, so this works in practice.
    skin_age: Optional[int]
    try:
        # DeepFace.analyze wants a numpy array OR a file path. We
        # pass the RGB array directly.
        result = DeepFace.analyze(
            img_path=rgb,
            actions=['age'],
            detector_backend='skip',
            enforce_detection=False,
            silent=True,
        )
        if isinstance(result, list):
            result = result[0]
        skin_age = int(result.get('age', 0)) or None
    except Exception as exc:
        logger.warning('Skin AI: age estimation failed: %s', exc)
        skin_age = None

    # Sex-aware multipliers. Defaults are 1.0 (sex unspecified). Male
    # skin is structurally thicker with larger pores at the same
    # "quality"; ease the penalty so an average male read doesn't tank
    # the score. Female skin shows finer-line detail earlier; ease the
    # wrinkles penalty modestly. The shifts are deliberately small —
    # we'd rather under-correct than fight the physics with a heavy
    # constant.
    pores_factor = 1.25 if sex_hint == 'male' else 1.0
    wrinkles_factor = 1.10 if sex_hint == 'female' else 1.0

    # ── 2. Wrinkle / fine line proxy: edge density on a blurred
    #       grayscale. More edges → more lines → worse.
    # On the mediapipe face crop, eyebrows + lips + nose contribute a
    # large baseline edge density even on smooth skin. Subtract a 0.05
    # floor and slow the slope so a typical face doesn't bottom out
    # the metric. Wrinkles_factor (1.10 for women) eases further.
    blur = _gaussian_blur(gray, radius=1.5)
    edge_density = _edge_density(blur)
    wrinkles_score = _score(
        1.0 - min(max(edge_density - 0.05, 0) * 6 / wrinkles_factor, 1.0)
    )

    # ── 3. Pore proxy: high-frequency texture via Laplacian variance.
    # Modern phone selfies typically run lap_var 800–3000+; the
    # original (lap_var-30)/400 threshold tanked any sharp photo to
    # zero. Wider band + sex factor (men's larger pores get more
    # leniency) keeps the score useful across phones.
    lap_var = _laplacian_variance(gray)
    pores_quality = 1.0 - min(
        max(lap_var - 300, 0) / (3000.0 * pores_factor), 1.0,
    )
    pores_score = _score(max(pores_quality, 0.0))

    # ── 4. Redness: mean of LAB 'a' channel (higher a = more red).
    # Healthy skin sits around a_mean 138-142 in our shift convention.
    # Old baseline of 130 treated normal warmth as inflammation;
    # raise to 138 and tighten the range so only meaningfully red
    # faces (rosacea-band 145+) start losing points.
    a_mean = float(lab[..., 1].mean()) + 128.0  # shift to 0-255 band
    red_excess = max((a_mean - 138) / 12.0, 0.0)
    redness_score = _score(1.0 - min(red_excess, 1.0))

    # ── 5. Spots / pigmentation: stddev of L channel. Uneven
    #       lightness = blotches / dark spots.
    l_std = float(lab[..., 0].std())
    spots_quality = 1.0 - min((l_std - 8) / 25.0, 1.0)
    spots_score = _score(max(spots_quality, 0.0))

    # ── 6. Hydration proxy: V-channel stddev. Reward mid-band
    #       variance (dehydrated skin tends to be either matte-flat
    #       or oily-shiny — both extremes).
    v_std = float(hsv[..., 2].std()) * 255.0  # back to 0-255 band
    if v_std < 5 or v_std > 45:
        hydration_quality = 0.4
    else:
        hydration_quality = 1.0 - abs(v_std - 15) / 30.0
    hydration_score = _score(hydration_quality)

    # ── Extended findings: each metric runs in its own try/except so
    # a single proxy can't tank the rest of the reading. Defaults to
    # 70 ("looks fine") when the proxy crashes; logged for tuning.
    L = lab[..., 0].astype(np.float32)  # native L in 0..100
    h_l, w_l = L.shape

    # 7. Pigmentation — residual L on a clean-skin patch.
    # The face-wide L residual was picking up eyebrows, eyelashes,
    # lips, and nostrils as "patches" because radius-20 blur doesn't
    # smooth features that big. Switch to the under-eye region from
    # mediapipe (when available) — that's clean cheek skin with no
    # anatomical features. Falls back to face-wide with a much wider
    # threshold when no landmarks.
    pigment_residual_std = 0.0
    try:
        if rgb_under_eye is not None and rgb_under_eye.size > 100:
            patch_L = _rgb_to_lab(rgb_under_eye)[..., 0].astype(np.float32)
            patch_uint8 = np.clip(patch_L * 2.55, 0, 255).astype(np.uint8)
            if patch_uint8.shape[0] >= 8 and patch_uint8.shape[1] >= 8:
                # radius=14 is stronger than the previous 8 so natural
                # under-eye gradient (tear-trough shadow, mild texture)
                # gets smoothed out — only abrupt patches survive.
                patch_smooth = _gaussian_blur(
                    patch_uint8, radius=14.0,
                ).astype(np.float32) / 2.55
                residual = patch_L - patch_smooth
                pigment_residual_std = float(residual.std())
            # Real under-eye skin sits around residual std 1.5-3.5
            # even when clean (natural pore + skin texture noise
            # after blur). Widen the band: baseline 1.5, ramp over
            # 6 so the score only meaningfully drops on genuine tone
            # patches (residual ≥4) and floors at 0 only when
            # residual hits ~7.5 — heavy melasma territory.
            pigmentation_score = _score(
                1.0 - min(max(pigment_residual_std - 1.5, 0) / 6.0, 1.0)
            )
        else:
            # Face-wide fallback. Wider threshold because eyebrows /
            # lips / nostrils still leak into the residual on the
            # full face crop.
            L_uint8 = np.clip(L * 2.55, 0, 255).astype(np.uint8)
            L_smooth = _gaussian_blur(
                L_uint8, radius=20.0,
            ).astype(np.float32) / 2.55
            residual = L - L_smooth
            pigment_residual_std = float(residual.std())
            pigmentation_score = _score(
                1.0 - min(max(pigment_residual_std - 4, 0) / 14.0, 1.0)
            )
    except Exception as exc:
        logger.warning('Skin AI: pigmentation proxy failed: %s', exc)
        pigmentation_score = 70

    # 8. Acne / breakout — red-hue mask. _rgb_to_hsv returns H in
    # degrees [0,360), so the wraparound check is in degrees too.
    # Previous thresholds (sat > 0.40, *12 multiplier) treated every
    # photo with lips visible as covered in acne — lipstick and
    # natural cheek flush easily exceed 8% of pixels. Tighter
    # saturation floor and a smaller multiplier so the score only
    # reacts to clearly inflamed blemishes, not normal facial colour.
    blob_density = 0.0
    try:
        h_ch = hsv[..., 0]
        s_ch = hsv[..., 1]
        v_ch = hsv[..., 2]
        red_mask = (((h_ch < 12) | (h_ch > 348))
                    & (s_ch > 0.55) & (v_ch > 0.30) & (v_ch < 0.80))
        blob_density = float(red_mask.mean())
        # Subtract a baseline (~2% red pixels is normal for a face
        # with visible lips) so unblemished skin floors near 100.
        acne_excess = max(blob_density - 0.02, 0.0)
        acne_score = _score(
            1.0 - min(acne_excess * 8, 1.0)
        )
    except Exception as exc:
        logger.warning('Skin AI: acne proxy failed: %s', exc)
        acne_score = 70

    # 9 + 10. Dark circles + eyebags — use the precise under-eye
    # region from mediapipe when available; fall back to the
    # bottom-third heuristic on the face-cropped image otherwise.
    darkness_drop = 0.0
    eyebag_grad = 0.0
    eye_region_method = 'fallback'
    try:
        if rgb_under_eye is not None and rgb_under_eye.size > 100:
            # Under-eye L vs cheek L (the band of face just below the
            # eyes vs the rest of the face). True dark-circles read.
            under_lab = _rgb_to_lab(rgb_under_eye)
            under_L = under_lab[..., 0].astype(np.float32)
            face_L_mean = float(L.mean())
            under_L_mean = float(under_L.mean())
            darkness_drop = max(face_L_mean - under_L_mean, 0.0)
            # Eyebags: vertical L gradient within the under-eye strip.
            if under_L.shape[0] >= 2:
                gy = np.diff(under_L, axis=0)
                eyebag_grad = float(np.abs(gy).mean())
            eye_region_method = 'mediapipe'
        else:
            third = max(1, h_l // 3)
            top_l = float(L[:third].mean())
            bottom_l = float(L[-third:].mean())
            darkness_drop = max(top_l - bottom_l, 0.0)
            bottom_band = L[-third:]
            if bottom_band.shape[0] >= 2:
                gy = np.diff(bottom_band, axis=0)
                eyebag_grad = float(np.abs(gy).mean())
        dark_circles_score = _score(
            1.0 - min(darkness_drop / 12.0, 1.0)
        )
        eyebags_score = _score(
            1.0 - min(max(eyebag_grad - 1, 0) / 5.0, 1.0)
        )
    except Exception as exc:
        logger.warning(
            'Skin AI: dark-circles/eyebags proxy failed: %s', exc,
        )
        dark_circles_score = 70
        eyebags_score = 70

    # 11. White spots — bright outliers vs a heavy local mean. Use a
    # uint8 blur path to dodge PIL's spotty float-mode filter support.
    # Previous threshold (>10 L delta, *30 multiplier) clipped to 0
    # on any normal face with forehead / nose / cheekbone specular
    # highlights. Tighter delta + smaller multiplier so the score
    # only reacts to genuinely abrupt bright spots (milia, hyper-
    # pigmentation light patches) rather than natural shine.
    bright_outliers = 0.0
    try:
        L_uint8 = np.clip(L * 2.55, 0, 255).astype(np.uint8)
        L_blurred = _gaussian_blur(L_uint8, radius=8.0).astype(np.float32) / 2.55
        bright_outliers = float(((L - L_blurred) > 18).mean())
        # Subtract a baseline (~1% bright outliers from natural T-zone
        # shine) so clean skin floors near 100 rather than 70.
        white_excess = max(bright_outliers - 0.01, 0.0)
        white_spots_score = _score(
            1.0 - min(white_excess * 12, 1.0)
        )
    except Exception as exc:
        logger.warning('Skin AI: white-spots proxy failed: %s', exc)
        white_spots_score = 70

    # ── Overall: weighted blend. Extended findings are weighted
    # lightly so the headline "overall" remains comparable to scans
    # taken before this commit.
    overall_score = int(round(
        0.18 * wrinkles_score
        + 0.18 * pores_score
        + 0.13 * redness_score
        + 0.16 * spots_score
        + 0.20 * hydration_score
        + 0.05 * pigmentation_score
        + 0.05 * acne_score
        + 0.02 * dark_circles_score
        + 0.02 * eyebags_score
        + 0.01 * white_spots_score
    ))

    # Confidence: skin_age None means DeepFace couldn't read the face
    # (poor light, blurry, off-angle). The numeric scores above still
    # come back from the OpenCV path, but the user should know the
    # reading is shaky.
    low_confidence = skin_age is None

    return {
        'skin_age': skin_age,
        'hydration_score': hydration_score,
        'pores_score': pores_score,
        'wrinkles_score': wrinkles_score,
        'redness_score': redness_score,
        'spots_score': spots_score,
        'pigmentation_score': pigmentation_score,
        'acne_score': acne_score,
        'dark_circles_score': dark_circles_score,
        'eyebags_score': eyebags_score,
        'white_spots_score': white_spots_score,
        'overall_score': overall_score,
        'low_confidence': low_confidence,
        'raw_results': {
            'image_shape': list(rgb_small.shape),
            'edge_density': round(edge_density, 4),
            'laplacian_var': round(lap_var, 2),
            'a_mean': round(a_mean, 2),
            'l_std': round(l_std, 2),
            'v_std': round(v_std, 2),
            'pigment_residual_std': round(pigment_residual_std, 2),
            'blob_density': round(blob_density, 4),
            'darkness_drop': round(darkness_drop, 2),
            'eyebag_grad': round(eyebag_grad, 2),
            'bright_outliers': round(bright_outliers, 4),
            'sex_hint': sex_hint or '',
            'pores_factor': pores_factor,
            'wrinkles_factor': wrinkles_factor,
            'crop_method': crop_method,
            'eye_region_method': eye_region_method,
            'note': 'Extended findings still rely on CV proxies; '
                    'mediapipe FaceMesh now provides face + under-eye '
                    'regions for dark_circles + eyebags specifically.',
        },
    }


def normalize_original(image_bytes: bytes) -> bytes:
    """Re-encode the uploaded photo as a JPEG with EXIF rotation baked
    into the pixels. The Flutter app already caps dimensions at 1600px,
    so no resize here — we just want the admin's hi-res view to show
    the photo upright and stripped of EXIF metadata."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90, optimize=True)
    return buf.getvalue()


def make_thumbnail(image_bytes: bytes, size: int = 256) -> bytes:
    """Produce a square JPEG thumbnail of the analysed face. Used by the
    in-app history list and the result-screen hero — both assume a 1:1
    crop and were showing light-grey padding bars from the previous
    "thumbnail + paste onto bigger square" approach."""
    img = Image.open(io.BytesIO(image_bytes))
    # Phones store the photo in sensor orientation with an EXIF rotation
    # tag — without exif_transpose() the saved JPEG comes out sideways
    # or upside-down even though the on-phone preview looked right.
    img = ImageOps.exif_transpose(img).convert('RGB')
    # Center-crop the long axis down to the short axis so the output is
    # square *and* fully covered by the photo. ImageOps.fit does the
    # crop + resize in one step using the same LANCZOS filter the old
    # path used.
    img = ImageOps.fit(img, (size, size), method=Image.LANCZOS,
                       centering=(0.5, 0.5))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85, optimize=True)
    return buf.getvalue()
