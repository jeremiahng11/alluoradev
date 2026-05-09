"""Rewards API for the mobile app and dashboard.

Balance flow: WordPress is the canonical points store (WPS Points & Rewards
plugin owns the value — purchases, redemptions, and admin tweaks all happen
there). Django's RewardLedger is an audit log of *Django-originated* events
(quiz pass, video watched). The /balance/ endpoint mirrors WP's number; the
/history/ endpoint serves the local ledger.
"""
import logging

from rest_framework import serializers, generics, permissions, status
from rest_framework.response import Response

from . import wp_client
from .models import RewardLedger, Badge, UserBadge

logger = logging.getLogger(__name__)


class RewardLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardLedger
        fields = ('id', 'points', 'source', 'description', 'reference_id', 'created_at')


class BadgeSerializer(serializers.ModelSerializer):
    icon = serializers.CharField(source='icon_resolved', read_only=True)

    class Meta:
        model = Badge
        fields = ('id', 'name', 'slug', 'description', 'icon')


class UserBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = UserBadge
        fields = ('id', 'badge', 'awarded_at')


class BalanceView(generics.GenericAPIView):
    """GET /api/v1/rewards/balance/ — current user's points balance + badges.

    `balance` mirrors WP's WPS plugin (canonical). `badges` are Django-only.
    If the bridge is unreachable, we fall back to the local ledger sum and
    flag the response with `stale: true` so the client can decide whether to
    surface a refresh banner.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        badges_data = UserBadgeSerializer(
            UserBadge.objects.filter(user=user).select_related('badge'),
            many=True,
        ).data

        wp_user_id = getattr(user, 'wp_user_id', None)
        if not wp_user_id:
            # No mapping to WP yet — only the local ledger has anything.
            return Response({
                'balance': RewardLedger.balance_for(user),
                'badges': badges_data,
                'source': 'ledger',
            })

        try:
            summary = wp_client.get_user_summary(wp_user_id)
            return Response({
                'balance': int(summary.get('total_points') or 0),
                'badges': badges_data,
                'source': 'wp',
                'referral_link': summary.get('referral_link'),
                'user_level': summary.get('user_level'),
            })
        except wp_client.BridgeError as exc:
            logger.warning('WP rewards bridge unavailable for user %s: %s',
                           user.pk, exc)
            return Response({
                'balance': RewardLedger.balance_for(user),
                'badges': badges_data,
                'source': 'ledger',
                'stale': True,
            })


class HistoryView(generics.ListAPIView):
    """GET /api/v1/rewards/history/ — paginated ledger for current user."""
    serializer_class = RewardLedgerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RewardLedger.objects.filter(user=self.request.user)
