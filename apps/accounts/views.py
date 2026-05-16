"""Accounts API.

The Flutter app already has /auth/* on WordPress, so we don't duplicate it.
We expose /api/v1/accounts/me which returns the Django-side user record
(mirroring + Alluora-specific fields like reward points balance), and
/api/v1/accounts/tiers/ which returns the public membership ladder so
the app can render the tier benefits section on the card screen.
"""
import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers, generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AppUser, TierRule

logger = logging.getLogger(__name__)

# /accounts/me triggers a spending re-sync if the cached value is older
# than this. Keeps the card screen's "Lifetime spend" current without
# hammering the WC bridge.
SPENDING_SYNC_TTL = timedelta(hours=24)


class AppUserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='display_name_or_email', read_only=True)
    reward_points = serializers.SerializerMethodField()
    card_label_subtitle = serializers.SerializerMethodField()
    auth_token = serializers.SerializerMethodField()

    class Meta:
        model = AppUser
        fields = (
            'id', 'wp_user_id', 'email', 'first_name', 'last_name',
            'display_name', 'phone', 'avatar_url', 'reward_points',
            'last_synced_at',
            'card_number_prefix', 'tier', 'membership_number',
            'card_label_subtitle',
            'total_spent', 'spending_synced_at',
            'auth_token',
            # Skin AI personalisation. Captured by the in-app
            # onboarding sheet on first scan. Empty string until set.
            'skin_sex', 'skin_primary_concern', 'birthday',
        )
        read_only_fields = fields

    def get_auth_token(self, obj) -> str:
        """Long-lived bearer token the app uses for subsequent Django
        calls — skips the WP /auth/me HTTP roundtrip. Issued on first
        /me, reused thereafter."""
        from .models import AlluoraSessionToken
        return AlluoraSessionToken.get_or_issue(obj).key

    def get_card_label_subtitle(self, obj) -> str:
        """The text rendered under the tier name on the membership
        card. Pulled from TierRule.card_label_subtitle (admin-editable)
        and falls back to 'MEMBER' if the rule is missing or blank."""
        from .models import TierRule
        try:
            rule = TierRule.objects.get(tier=obj.tier)
            if rule.card_label_subtitle.strip():
                return rule.card_label_subtitle
        except TierRule.DoesNotExist:
            pass
        return 'MEMBER'

    def get_reward_points(self, obj):
        # Mirror from WordPress (canonical points store). Falls back to the
        # local ledger if the bridge is unreachable so /accounts/me still
        # returns *something* rather than failing the whole user payload.
        from apps.rewards import wp_client
        from apps.rewards.models import RewardLedger
        if obj.wp_user_id:
            try:
                summary = wp_client.get_user_summary(obj.wp_user_id)
                return int(summary.get('total_points') or 0)
            except wp_client.BridgeError:
                pass
        return RewardLedger.balance_for(obj)


class MeView(generics.RetrieveAPIView):
    """GET /api/v1/accounts/me — current end-user (Django-side mirror).

    Side-effect: lazily syncs the user's WooCommerce lifetime spending
    if it's stale (>24h or never synced). Best-effort — never fails
    /me if the bridge is unreachable.
    """
    serializer_class = AppUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        # `?refresh=1` forces a background spending sync regardless
        # of the 24h staleness check. The app passes this on every
        # fresh login (AuthService.login / register) so the admin
        # dashboard sees a current total + spending_synced_at right
        # after the user signs in.
        force = self.request.query_params.get('refresh') == '1'
        if user.wp_user_id:
            stale = force or (
                user.spending_synced_at is None
                or (timezone.now() - user.spending_synced_at) > SPENDING_SYNC_TTL
            )
            if stale:
                # Spawn the sync in a background thread so /me returns
                # immediately. The next /me call (or a manual refresh)
                # will pick up the new total_spent. This trades "fresh
                # numbers on the first request after stale" for
                # "/me always responds in under a second" — which the
                # app cares about a lot more.
                import threading
                threading.Thread(
                    target=self._safe_sync,
                    args=(user.pk,),
                    daemon=True,
                ).start()
        return user

    @staticmethod
    def _safe_sync(user_pk: int) -> None:
        """Best-effort spending sync running off the request thread.
        Re-fetches the user from the DB (since the original instance
        may be GC'd) and swallows every exception."""
        try:
            user = AppUser.objects.get(pk=user_pk)
            from . import spending as spending_service
            spending_service.sync_user_spending(user)
        except Exception as exc:
            logger.warning(
                'Background spending sync failed for user %s: %s',
                user_pk, exc,
            )


class SkinProfileView(generics.UpdateAPIView):
    """PATCH /api/v1/accounts/me/skin-profile/ — write the two Skin AI
    personalisation fields captured by the onboarding bottom sheet:
    `skin_sex` (single choice) and `skin_primary_concern` (comma-
    separated multi-select).

    Missing keys are left untouched. Empty strings clear the value back
    to "not set". Concerns that aren't in AppUser.SKIN_CONCERN_VALID
    are silently dropped (the API doesn't 400 on a typo'd slug — it
    just stores the valid subset).
    """
    permission_classes = [permissions.IsAuthenticated]

    class _Serializer(serializers.ModelSerializer):
        class Meta:
            model = AppUser
            fields = ('skin_sex', 'skin_primary_concern', 'birthday')

        def validate_birthday(self, value):
            # Accept null to clear; reject implausible dates so a
            # mistyped year can't tank the age delta.
            if value is None:
                return value
            from datetime import date
            today = date.today()
            min_d = date(today.year - 120, 1, 1)
            if value > today:
                raise serializers.ValidationError(
                    "Birthday can't be in the future.")
            if value < min_d:
                raise serializers.ValidationError(
                    'Birthday looks unrealistic — please re-enter.')
            return value

        def validate_skin_primary_concern(self, value: str) -> str:
            if not value:
                return ''
            valid = set(AppUser.SKIN_CONCERN_VALID)
            kept = [
                s.strip() for s in value.split(',')
                if s.strip() in valid
            ]
            # Dedupe while preserving order so the round-trip is stable.
            seen = set()
            deduped = []
            for s in kept:
                if s not in seen:
                    seen.add(s)
                    deduped.append(s)
            return ','.join(deduped)

        def validate_skin_sex(self, value: str) -> str:
            valid = {slug for slug, _ in AppUser.SKIN_SEX_CHOICES}
            return value if value in valid else ''

    serializer_class = _Serializer
    http_method_names = ('patch',)

    def get_object(self):
        return self.request.user


class DeleteMeView(APIView):
    """DELETE /api/v1/accounts/me/ — wipe the requesting user's
    account + all FK-cascaded data (skin analyses, reward ledger,
    quiz submissions, video views, session tokens). Returns 204 on
    success.

    Note: doesn't touch the WordPress side. The WP user record stays;
    re-registering with the same email gets a fresh Django user.
    Acceptable trade-off for a single-system delete.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        from django.db import transaction
        user = request.user
        # Belt-and-braces — keep the delete inside a transaction so
        # a half-cascade can't leave orphaned skin analyses or reward
        # rows behind. on_delete=CASCADE on the FK fields handles the
        # rest.
        with transaction.atomic():
            user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TierRuleSerializer(serializers.ModelSerializer):
    perks = serializers.SerializerMethodField()

    class Meta:
        model = TierRule
        fields = (
            'id', 'tier', 'min_spent', 'is_invite_only',
            'card_label_subtitle', 'perks_description', 'perks',
        )
        read_only_fields = fields

    def get_perks(self, obj):
        """Split perks_description into a list of non-empty lines so
        the app can render bullet points without re-parsing."""
        return [
            line.strip()
            for line in (obj.perks_description or '').splitlines()
            if line.strip()
        ]


class TierLadderView(generics.ListAPIView):
    """GET /api/v1/accounts/tiers/ — public membership ladder.

    Returned in ascending spend order so the app can render the tier
    progression as-is. Open to all authenticated users (and guests).
    """
    serializer_class = TierRuleSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        return TierRule.objects.all().order_by('is_invite_only', 'min_spent')
