"""Skin AI API.

Endpoints:

  POST /api/v1/skinai/analyze/   multipart upload, returns analysis JSON.
  GET  /api/v1/skinai/history/   paginated list of the user's past scans.
  GET  /api/v1/skinai/quota/     pre-flight: what would my next scan cost?
"""
from __future__ import annotations

import logging

from django.core.files.base import ContentFile
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView


class _AnalyzeThrottle(UserRateThrottle):
    """Per-user 30/hour cap on the analyze endpoint. Tuned higher than
    the quota's 3-7 scans/week so legitimate retries (wrong photo,
    blurry photo, etc.) aren't blocked, but a runaway loop or a
    deliberate griefer gets throttled long before they drain Glow
    Coins or pin the DeepFace inference CPU."""
    scope = 'skinai_analyze'

from apps.rewards import wp_client

from . import pipeline, quota
from .models import MAX_SCANS_PER_USER, SkinAnalysis, SkinCheckIn, SkinRoutineProduct
from .serializers import (
    SkinAnalysisSerializer, SkinCheckInSerializer,
    SkinRoutineProductSerializer,
)


class _CheckInThrottle(UserRateThrottle):
    """Once per ~24 hours per user. The whole point of the daily
    check-in is to be casual + frequent; throttling tighter than
    daily defeats the feature, but >1/day would let it become a
    backdoor for free full scans."""
    scope = 'skinai_check_in'


class _IsDashboardAdmin(permissions.BasePermission):
    """Diagnostic endpoints (deps + selftest) are admin-only now —
    they reveal which ML libs are installed and run the full pipeline
    on demand. Useful for ops debugging, not something we want pinged
    by anonymous traffic in production."""

    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated
            and getattr(u, 'is_dashboard_admin', False)
        )


class DepsHealthView(APIView):
    """Diagnostic — reports whether the ML pipeline can import its
    dependencies, and exactly what fails if not. Locked to dashboard
    admins; previous version was AllowAny which leaked dep versions
    to anyone who could guess the URL."""
    permission_classes = [_IsDashboardAdmin]

    def get(self, request):
        report = {
            'numpy': _try_import('numpy'),
            'PIL': _try_import('PIL'),
            'cv2': _try_import('cv2'),
            'tf_keras': _try_import('tf_keras'),
            'tensorflow': _try_import('tensorflow'),
            'deepface': _try_import('deepface'),
        }
        ready = all(v.get('ok') for v in report.values())
        return Response({'ready': ready, 'deps': report})


class HealthView(APIView):
    """GET /api/v1/skinai/health/ — runs a synthetic 256x256 image
    through the full pipeline (mediapipe + DeepFace + thumbnail +
    JSON encode) and returns 200 only when every stage succeeds.

    Public so external monitors can poll without an auth handshake.
    Returns minimal info on success ({status, took_ms, version})
    and a 503 with stage info on failure — never the full traceback.
    Use SelfTestView (admin-gated) when you need the traceback."""
    permission_classes = [permissions.AllowAny]
    # Throttle public health pings so this can't be used to pin
    # DeepFace CPU. Per-IP, very loose.
    from rest_framework.throttling import AnonRateThrottle

    class _HealthThrottle(AnonRateThrottle):
        scope = 'skinai_health'

    throttle_classes = [_HealthThrottle]

    def get(self, request):
        import io
        import time
        try:
            import numpy as np
            from PIL import Image
            arr = np.full((256, 256, 3), 200, dtype=np.uint8)
            arr[..., 0] = 220
            arr[..., 1] = 180
            arr[..., 2] = 160
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format='JPEG', quality=85)
            jpeg_bytes = buf.getvalue()
        except Exception:
            return Response(
                {'status': 'fail', 'stage': 'fixture'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        t0 = time.monotonic()
        try:
            result = pipeline.analyse(jpeg_bytes)
            pipeline.make_thumbnail(jpeg_bytes)
        except Exception as exc:
            logger.exception('Skin AI healthcheck failed: %s', exc)
            return Response(
                {'status': 'fail', 'stage': 'pipeline'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({
            'status': 'ok',
            'took_ms': int((time.monotonic() - t0) * 1000),
            'pipeline_version': pipeline.CURRENT_PIPELINE_VERSION,
            'low_confidence': result.get('low_confidence'),
        })


class SelfTestView(APIView):
    """Diagnostic — runs the pipeline on a synthetic in-memory photo
    and reports the result OR the full exception traceback. Dashboard
    admins only; previous version was AllowAny."""
    permission_classes = [_IsDashboardAdmin]

    def get(self, request):
        import io
        import traceback
        try:
            import numpy as np
            from PIL import Image
            # Solid skin-toned square — enough for the pipeline to
            # decode + score, and a clean test of DeepFace's age
            # path even though the result will be meaningless.
            arr = np.full((400, 400, 3), 200, dtype=np.uint8)
            arr[..., 0] = 220  # warm tone
            arr[..., 1] = 180
            arr[..., 2] = 160
            buf = io.BytesIO()
            Image.fromarray(arr).save(buf, format='JPEG', quality=85)
            jpeg_bytes = buf.getvalue()
        except Exception as exc:
            return Response({
                'stage': 'fixture',
                'error': repr(exc),
                'traceback': traceback.format_exc(),
            }, status=500)

        try:
            result = pipeline.analyse(jpeg_bytes)
            return Response({
                'stage': 'ok',
                'result': result,
            })
        except Exception as exc:
            return Response({
                'stage': 'pipeline',
                'error': repr(exc),
                'traceback': traceback.format_exc(),
            }, status=500)


def _try_import(name: str) -> dict:
    try:
        import importlib
        mod = importlib.import_module(name)
        version = getattr(mod, '__version__', '?')
        return {'ok': True, 'version': str(version)}
    except Exception as exc:
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}

logger = logging.getLogger(__name__)


def _user_balance(user) -> int:
    """Fetch the user's current Glow Coin balance from the WP bridge.
    Returns 0 (and logs) on any bridge error — the caller treats this
    as "no coins available" so the user gets a clear out-of-coins
    message instead of a 500."""
    wp_id = getattr(user, 'wp_user_id', None)
    if not wp_id:
        return 0
    try:
        summary = wp_client.get_user_summary(wp_id, use_cache=False)
        return int(summary.get('total_points', 0) or 0)
    except Exception as exc:
        logger.warning('Skin AI: balance fetch failed for wp=%s: %s', wp_id, exc)
        return 0


class QuotaView(APIView):
    """Pre-flight check — used by the app's capture screen to show
    "1 free scan left this week" or "next scan costs 50 Glow Coins"
    before the user takes a photo."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        balance = _user_balance(request.user)
        decision = quota.check_quota(request.user, balance)
        return Response({
            'allowed': decision.allowed,
            'cost': decision.cost,
            'reason': decision.reason,
            'used_in_period': decision.used_in_period,
            'free_quota': decision.free_quota,
            'unlimited': decision.unlimited,
            'period_unit': decision.period_unit,
            'balance': balance,
        })


class AnalyzeView(APIView):
    """Run a skin AI analysis on the uploaded image and (if past free
    quota) deduct Glow Coins. Returns the SkinAnalysis row."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_classes = [_AnalyzeThrottle]

    def post(self, request):
        upload = request.FILES.get('photo')
        if not upload:
            return Response(
                {'detail': 'Upload field "photo" is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Cheap size cap. 10 MB is way more than enough for a 1024x1024 JPEG.
        if upload.size > 10 * 1024 * 1024:
            return Response(
                {'detail': 'Photo is too large (10 MB max).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Pre-flight quota check.
        balance = _user_balance(request.user)
        decision = quota.check_quota(request.user, balance)
        if not decision.allowed:
            return Response(
                {
                    'detail': decision.reason or 'Scan not available.',
                    'cost': decision.cost,
                    'balance': balance,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        # 2. Read bytes ONCE — we throw away the file handle right after.
        image_bytes = upload.read()

        # 3. Run the pipeline. Pass the user's stored skin sex so the
        # threshold tweaks fire (men get pore leniency, women get
        # wrinkle leniency); falls back to the unisex defaults if the
        # user hasn't completed the onboarding sheet.
        sex_hint = getattr(request.user, 'skin_sex', '') or ''
        try:
            result = pipeline.analyse(image_bytes, sex_hint=sex_hint)
        except ValueError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RuntimeError as exc:
            logger.error('Skin AI deps missing: %s', exc)
            return Response(
                {'detail': 'Skin AI is temporarily unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception('Skin AI pipeline crashed: %s', exc)
            return Response(
                {'detail': 'Sorry — analysis failed. Try again with a '
                           'clearer photo.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Log the scoring breakdown for every scan so we can debug
        # regressions like "all metrics came back 0" without needing
        # to reproduce the exact image.
        logger.info(
            'Skin AI scan for user=%s sex=%r scores=%s low_conf=%s',
            request.user.id, sex_hint,
            {k: v for k, v in result.items()
             if k.endswith('_score') or k == 'skin_age'},
            result.get('low_confidence'),
        )

        # 4. Build thumbnail + normalized original, then persist. The
        #    raw uploaded bytes are dropped after this scope — only the
        #    re-encoded JPEGs touch disk.
        thumb_bytes = pipeline.make_thumbnail(image_bytes)
        original_bytes = pipeline.normalize_original(image_bytes)
        low_conf = bool(result.get('low_confidence', False))
        # Zero the coin cost on low-confidence reads so the user
        # isn't billed when DeepFace couldn't actually read a face.
        # The scan still saves (the numeric scores may be useful);
        # we just don't deduct.
        billed_cost = 0 if low_conf else decision.cost
        analysis = SkinAnalysis(
            user=request.user,
            skin_age=result['skin_age'],
            hydration_score=result['hydration_score'],
            pores_score=result['pores_score'],
            wrinkles_score=result['wrinkles_score'],
            redness_score=result['redness_score'],
            spots_score=result['spots_score'],
            pigmentation_score=result.get('pigmentation_score', 0),
            acne_score=result.get('acne_score', 0),
            dark_circles_score=result.get('dark_circles_score', 0),
            eyebags_score=result.get('eyebags_score', 0),
            white_spots_score=result.get('white_spots_score', 0),
            overall_score=result['overall_score'],
            coin_cost=billed_cost,
            raw_results=result['raw_results'],
            low_confidence=low_conf,
            pipeline_version=pipeline.CURRENT_PIPELINE_VERSION,
        )
        # Save first so the row gets a real id and created_at — then
        # we can name the files with a stable unique filename instead of
        # the bare "skin-{user_id}-new.jpg" the previous version
        # produced (analysis.created_at was always None at this point
        # since auto_now_add doesn't fire until .save()).
        analysis.save()
        filename = f'skin-{request.user.id}-{analysis.id}.jpg'
        analysis.thumbnail.save(filename, ContentFile(thumb_bytes), save=False)
        analysis.original_photo.save(
            filename, ContentFile(original_bytes), save=False,
        )
        analysis.save()

        # Cap per-user history at MAX_SCANS_PER_USER. Anything past the
        # most recent N gets deleted oldest-first; the post_delete
        # signal in models.py removes the JPEG files from the volume.
        ids_to_drop = list(
            SkinAnalysis.objects
            .filter(user=request.user)
            .order_by('-created_at')
            .values_list('id', flat=True)[MAX_SCANS_PER_USER:]
        )
        trimmed_count = 0
        if ids_to_drop:
            SkinAnalysis.objects.filter(id__in=ids_to_drop).delete()
            trimmed_count = len(ids_to_drop)

        # 5. Deduct coins (after the analysis row is saved so we have
        #    an id for reference_id, which lets WP audit the charge).
        #    Skipped on low-confidence reads — billed_cost is 0 there.
        if billed_cost > 0:
            wp_id = getattr(request.user, 'wp_user_id', None)
            if wp_id:
                try:
                    wp_client.award_points(
                        wp_id, -billed_cost,
                        source='skinai',
                        reference_id=str(analysis.id),
                    )
                except Exception as exc:
                    # Deduction failed AFTER analysis. Log loudly; we
                    # don't refund the analysis row because re-running
                    # would re-incur DeepFace work. The next scan's
                    # quota check still counts this one.
                    logger.error(
                        'Skin AI coin deduction failed for analysis=%s '
                        'wp=%s: %s', analysis.id, wp_id, exc,
                    )

        # Surface trim metadata + actual billed cost as runtime-only
        # fields on the response. The client uses cap_trimmed to show
        # a "Your oldest scan was archived" toast on the entry screen.
        payload = SkinAnalysisSerializer(analysis).data
        payload['cap_trimmed'] = trimmed_count
        payload['quota_cost'] = decision.cost
        return Response(payload, status=status.HTTP_201_CREATED)


class CheckInView(APIView):
    """POST /api/v1/skinai/check-in/ — daily lightweight progress
    snapshot. Same pipeline as /analyze/ but only persists the
    overall + skin-age + hydration + redness scores plus the
    thumbnail. No coin charge. Throttled to 1/day per user. Old
    check-ins past 90 are rolled off oldest-first."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_classes = [_CheckInThrottle]

    def post(self, request):
        upload = request.FILES.get('photo')
        if not upload:
            return Response(
                {'detail': 'Upload field "photo" is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > 10 * 1024 * 1024:
            return Response(
                {'detail': 'Photo is too large (10 MB max).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image_bytes = upload.read()
        sex_hint = getattr(request.user, 'skin_sex', '') or ''
        try:
            result = pipeline.analyse(image_bytes, sex_hint=sex_hint)
        except ValueError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RuntimeError:
            return Response(
                {'detail': 'Skin AI is temporarily unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception('Skin AI check-in pipeline crashed: %s', exc)
            return Response(
                {'detail': 'Sorry — check-in failed. Try again with a '
                           'clearer photo.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        thumb_bytes = pipeline.make_thumbnail(image_bytes)
        check_in = SkinCheckIn(
            user=request.user,
            skin_age=result['skin_age'],
            overall_score=result['overall_score'],
            hydration_score=result['hydration_score'],
            redness_score=result['redness_score'],
            low_confidence=bool(result.get('low_confidence', False)),
            pipeline_version=pipeline.CURRENT_PIPELINE_VERSION,
        )
        check_in.save()
        check_in.thumbnail.save(
            f'checkin-{request.user.id}-{check_in.id}.jpg',
            ContentFile(thumb_bytes),
            save=True,
        )

        # Cap per-user check-in history. Same pattern as the 6-cap
        # on full scans, just at SkinCheckIn.MAX_PER_USER (~3 months
        # of dailies). post_delete signal cleans the JPEGs.
        ids_to_drop = list(
            SkinCheckIn.objects
            .filter(user=request.user)
            .order_by('-created_at')
            .values_list('id', flat=True)[SkinCheckIn.MAX_PER_USER:]
        )
        if ids_to_drop:
            SkinCheckIn.objects.filter(id__in=ids_to_drop).delete()

        return Response(
            SkinCheckInSerializer(check_in).data,
            status=status.HTTP_201_CREATED,
        )


class CheckInsListView(generics.ListAPIView):
    """GET /api/v1/skinai/check-ins/ — current user's check-in history,
    newest first. Used by the in-app trend view."""
    serializer_class = SkinCheckInSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return SkinCheckIn.objects.filter(user=self.request.user)


class CheckInThumbView(APIView):
    """GET /api/v1/skinai/check-ins/<pk>/thumb/ — auth-gated thumbnail
    streaming, parallel to ThumbnailView. Owner OR dashboard admin."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        from django.http import FileResponse, Http404
        try:
            row = SkinCheckIn.objects.get(pk=pk)
        except SkinCheckIn.DoesNotExist:
            raise Http404
        is_owner = row.user_id == request.user.id
        is_admin = bool(getattr(request.user, 'is_dashboard_admin', False))
        if not (is_owner or is_admin):
            return Response(
                {'detail': 'Not allowed.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not row.thumbnail:
            raise Http404
        try:
            fh = row.thumbnail.open('rb')
        except FileNotFoundError:
            raise Http404
        return FileResponse(fh, content_type='image/jpeg')


class RoutineProductListCreateView(generics.ListCreateAPIView):
    """GET / POST /api/v1/skinai/routine/ — list or add a product the
    user is using in their daily skincare routine. Owner-scoped."""
    serializer_class = SkinRoutineProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return SkinRoutineProduct.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RoutineProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH / DELETE /api/v1/skinai/routine/<id>/ — edit or
    remove a routine product. Owner-only."""
    serializer_class = SkinRoutineProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SkinRoutineProduct.objects.filter(user=self.request.user)


class HistoryView(generics.ListAPIView):
    """List the requesting user's past skin analyses, newest first.

    Filters out scans the user has soft-deleted from their phone
    (hidden_from_user=True). Those rows remain in the database and
    still appear on the admin dashboard — the two visibilities are
    independent.
    """
    serializer_class = SkinAnalysisSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SkinAnalysis.objects.filter(
            user=self.request.user,
            hidden_from_user=False,
        )


class ThumbnailView(APIView):
    """GET /api/v1/skinai/<id>/thumb/ — stream the 256x256 thumbnail.

    Owner OR dashboard admin only. Previous version of the app
    referenced the thumbnail via /media/skinai/thumbs/... which was
    served unauthenticated; an attacker who guessed the path could
    pull any user's face image. This view gates by ownership while
    keeping the file path internal.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        from django.http import FileResponse, Http404
        try:
            analysis = SkinAnalysis.objects.get(pk=pk)
        except SkinAnalysis.DoesNotExist:
            raise Http404
        is_owner = analysis.user_id == request.user.id
        is_admin = bool(
            getattr(request.user, 'is_dashboard_admin', False)
        )
        if not (is_owner or is_admin):
            return Response(
                {'detail': 'Not allowed.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not analysis.thumbnail:
            raise Http404
        try:
            fh = analysis.thumbnail.open('rb')
        except FileNotFoundError:
            raise Http404
        return FileResponse(fh, content_type='image/jpeg')


class RecommendationsView(APIView):
    """GET /api/v1/skinai/<id>/recommendations/

    Returns up to 4 WooCommerce products tailored to the analysis's
    worst-scoring categories. Owner-only — admins viewing other users'
    scans use the dashboard endpoint instead.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        try:
            analysis = SkinAnalysis.objects.get(pk=pk, user=request.user)
        except SkinAnalysis.DoesNotExist:
            return Response({'detail': 'Not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        from . import recommendations as rec
        return Response({
            'analysis_id': analysis.id,
            'recommendations': rec.recommend_for_analysis(analysis),
        })


class DeleteAnalysisView(APIView):
    """Soft-delete the analysis from the user's app history.

    DELETE /api/v1/skinai/<id>/

    Sets hidden_from_user=True on the row, which removes it from
    /history/ and the result-detail fetch. The admin dashboard
    keeps seeing the row (until the admin separately hides it on
    their side). User can only delete their own analyses.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk: int):
        try:
            analysis = SkinAnalysis.objects.get(pk=pk, user=request.user)
        except SkinAnalysis.DoesNotExist:
            return Response(
                {'detail': 'Not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not analysis.hidden_from_user:
            analysis.hidden_from_user = True
            analysis.save(update_fields=['hidden_from_user'])
        return Response(status=status.HTTP_204_NO_CONTENT)
