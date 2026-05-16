"""mediapipe Face Mesh wrapper for Skin AI region extraction.

We don't need 468 landmarks for what we're doing — just a precise
face bounding box (better than the static 70%×80% center crop) plus
the under-eye region for dark-circles + eyebags scoring. This module
hides the mediapipe import behind a lazy loader so a missing wheel
or a failed init can't crash the whole pipeline; callers handle the
None return as "fall back to the heuristic crop".

Landmark index reference:
    https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png

Indices below were picked from that canonical model; tweaking them
nudges where each region sits without re-importing mediapipe.
"""
from __future__ import annotations

import logging
from typing import NamedTuple, Optional

import numpy as np

logger = logging.getLogger(__name__)


# Lazy-init singleton. None = not yet tried, False = init failed,
# otherwise a FaceMesh instance.
_FACE_MESH = None


class FaceRegions(NamedTuple):
    """Bounding boxes (x1, y1, x2, y2) in pixel coords of the input
    image. Empty arrays / zero-area boxes are filtered by the caller."""
    face_bbox: tuple
    under_eye_bbox: tuple


# Mediapipe FaceMesh indices for the lower edge of both eyes. Picked
# from the canonical model so the under-eye box covers the band where
# circles / bags actually show.
_LEFT_EYE_LOWER = (33, 7, 163, 144, 145, 153, 154, 155, 133)
_RIGHT_EYE_LOWER = (263, 249, 390, 373, 374, 380, 381, 382, 362)


def _load() -> Optional[object]:
    """Initialise the FaceMesh singleton on first call. Returns None
    when mediapipe isn't installed / failed to load — pipeline falls
    back to the static center crop in that case."""
    global _FACE_MESH
    if _FACE_MESH is False:
        return None
    if _FACE_MESH is not None:
        return _FACE_MESH
    try:
        import mediapipe as mp
        _FACE_MESH = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=False,  # iris landmarks not needed
            min_detection_confidence=0.5,
        )
        logger.info('Skin AI: mediapipe FaceMesh ready')
    except Exception as exc:
        logger.warning(
            'Skin AI: mediapipe init failed (%s) — falling back '
            'to center-crop heuristic', exc,
        )
        _FACE_MESH = False
        return None
    return _FACE_MESH


def detect_regions(rgb: np.ndarray) -> Optional[FaceRegions]:
    """Run FaceMesh on `rgb` (uint8 H×W×3, RGB order) and return the
    face + under-eye bounding boxes. None when no face is detected or
    mediapipe is unavailable.

    The face bbox is padded ~10% on each side so hairline + chin
    aren't clipped. The under-eye bbox extends ~1.5× the eye height
    below the lower eyelid landmarks — covers the band where dark
    circles and puffiness actually live."""
    mesh = _load()
    if mesh is None:
        return None
    try:
        results = mesh.process(rgb)
    except Exception as exc:
        logger.warning('Skin AI: mediapipe inference failed: %s', exc)
        return None
    if not results.multi_face_landmarks:
        return None

    landmarks = results.multi_face_landmarks[0].landmark
    h, w = rgb.shape[:2]

    # Face bbox from all 468 landmarks (more accurate than relying on
    # corner indices). Pad outward to keep the hairline + chin.
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    fx1 = max(0, int(min(xs) * w))
    fy1 = max(0, int(min(ys) * h))
    fx2 = min(w, int(max(xs) * w))
    fy2 = min(h, int(max(ys) * h))
    pad_x = int((fx2 - fx1) * 0.10)
    pad_y_top = int((fy2 - fy1) * 0.15)  # forehead/hairline a bit more
    pad_y_bot = int((fy2 - fy1) * 0.08)
    face_bbox = (
        max(0, fx1 - pad_x),
        max(0, fy1 - pad_y_top),
        min(w, fx2 + pad_x),
        min(h, fy2 + pad_y_bot),
    )

    # Under-eye region — union of both eyes' lower-eyelid points,
    # extended downward.
    def _pts(indices):
        pts_x = [int(landmarks[i].x * w) for i in indices]
        pts_y = [int(landmarks[i].y * h) for i in indices]
        return min(pts_x), min(pts_y), max(pts_x), max(pts_y)

    lx1, ly1, lx2, ly2 = _pts(_LEFT_EYE_LOWER)
    rx1, ry1, rx2, ry2 = _pts(_RIGHT_EYE_LOWER)
    eye_height = max(1, max(ly2 - ly1, ry2 - ry1))
    # Skip the eyelashes + lower eyelid edge by starting the box
    # below the lashline. Without this offset the under-eye region
    # opens with very dark pixels (lashes) right against light cheek
    # skin, which spikes L-channel std on every face — pigmentation
    # was reading 0 for clean skin as a result.
    skip_lashes = int(eye_height * 0.45)
    extend_down = int(eye_height * 1.4)
    top_y = max(ly2, ry2) + skip_lashes
    under_eye_bbox = (
        max(0, min(lx1, rx1)),
        min(h, top_y),
        min(w, max(lx2, rx2)),
        min(h, top_y + extend_down),
    )

    return FaceRegions(face_bbox=face_bbox, under_eye_bbox=under_eye_bbox)
