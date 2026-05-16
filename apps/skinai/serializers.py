from rest_framework import serializers

from . import insights
from .models import SkinAnalysis, SkinCheckIn, SkinRoutineProduct


class SkinRoutineProductSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = SkinRoutineProduct
        fields = (
            'id', 'name', 'brand', 'slot',
            'started_at', 'ended_at', 'notes',
            'is_active', 'created_at',
        )
        read_only_fields = ('id', 'created_at', 'is_active')

    def validate_name(self, value: str) -> str:
        v = (value or '').strip()
        if not v:
            raise serializers.ValidationError('Name is required.')
        return v[:120]


class SkinCheckInSerializer(serializers.ModelSerializer):
    """Light counterpart to SkinAnalysisSerializer. Mirrors the
    auth-gated thumbnail URL pattern; no insights, no recommendations.
    Used by both the POST /skinai/check-in/ response and the GET list."""
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = SkinCheckIn
        fields = (
            'id', 'thumbnail_url', 'skin_age', 'overall_score',
            'hydration_score', 'redness_score',
            'low_confidence', 'pipeline_version', 'created_at',
        )
        read_only_fields = fields

    def get_thumbnail_url(self, obj) -> str:
        if not obj.thumbnail:
            return ''
        return f'/api/v1/skinai/check-ins/{obj.pk}/thumb/'


class SkinAnalysisSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()
    # Insight copy is computed server-side (apps/skinai/insights.py) so
    # the Flutter app can render it without duplicating the strings.
    # The compute() call also reads the user's stored primary concern
    # off `analysis.user.skin_primary_concern` so the recommendation
    # targets what they care about (unless something else is much worse).
    insight_summary = serializers.SerializerMethodField()
    insight_headline = serializers.SerializerMethodField()
    insight_body = serializers.SerializerMethodField()
    skin_type = serializers.SerializerMethodField()
    skin_type_label = serializers.SerializerMethodField()
    # Compares DeepFace's skin_age estimate against the user's real
    # age (from AppUser.birthday). Empty/available=False if either is
    # unset — UI just hides the banner.
    age_comparison = serializers.SerializerMethodField()
    # Per-tier population benchmarking. Empty dict until each tier has
    # >= settings.SKINAI_TIER_AVG_MIN_USERS users with recent scans
    # — the helper auto-activates when the threshold is reached, no
    # code change needed. UIs hide the comparison block when this is
    # empty.
    tier_comparison = serializers.SerializerMethodField()
    # Detailed per-category breakdown (label / score / band /
    # what_it_is / what_yours_says) for the in-app "Detailed analysis"
    # section. Computed cheaply from the existing scores by
    # insights.compute_details — no extra DB hit.
    insight_details = serializers.SerializerMethodField()

    class Meta:
        model = SkinAnalysis
        fields = (
            'id',
            'thumbnail_url',
            'skin_age',
            'hydration_score',
            'pores_score',
            'wrinkles_score',
            'redness_score',
            'spots_score',
            'pigmentation_score',
            'acne_score',
            'dark_circles_score',
            'eyebags_score',
            'white_spots_score',
            'overall_score',
            'coin_cost',
            'created_at',
            'low_confidence',
            'pipeline_version',
            'insight_summary',
            'insight_headline',
            'insight_body',
            'skin_type',
            'skin_type_label',
            'age_comparison',
            'tier_comparison',
            'insight_details',
        )
        read_only_fields = fields

    def get_thumbnail_url(self, obj) -> str:
        """Return the auth-gated /skinai/<id>/thumb/ path instead of
        the raw /media/ URL. The Flutter app already prepends
        AppConfig.djangoBase to relative URLs, so this works
        transparently. Empty string when no thumb is on file."""
        if not obj.thumbnail:
            return ''
        return f'/api/v1/skinai/{obj.pk}/thumb/'

    def _insight(self, obj) -> dict:
        # Cache on the instance so the four SerializerMethodFields
        # below don't each rebuild the dict during one serialize pass.
        cached = getattr(obj, '_insight_cache', None)
        if cached is None:
            concern = getattr(obj.user, 'skin_primary_concern', '') or ''
            cached = insights.compute(obj, primary_concern=concern)
            obj._insight_cache = cached
        return cached

    def get_insight_summary(self, obj) -> str:
        return self._insight(obj)['summary']

    def get_insight_headline(self, obj) -> str:
        return self._insight(obj)['headline']

    def get_insight_body(self, obj) -> str:
        # Raw markdown-style body with **bold** markers. The Flutter
        # app parses these client-side into TextSpans; the admin uses
        # `body_html` instead.
        return self._insight(obj)['body']

    def get_skin_type(self, obj) -> str:
        return self._insight(obj)['skin_type']

    def get_skin_type_label(self, obj) -> str:
        return self._insight(obj)['skin_type_label']

    def get_insight_details(self, obj) -> list:
        return insights.compute_details(obj)

    def get_tier_comparison(self, obj) -> dict:
        # Best-effort — never let this block the rest of the
        # serialization. Returns {} when the feature is dormant.
        try:
            from . import tier_averages as _ta
            return _ta.comparison_for(obj)
        except Exception:
            return {}

    def get_age_comparison(self, obj) -> dict:
        return self._insight(obj)['age_comparison']
