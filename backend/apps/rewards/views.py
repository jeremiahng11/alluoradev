"""Rewards API for the mobile app and dashboard."""
from rest_framework import serializers, generics, permissions
from rest_framework.response import Response
from .models import RewardLedger, Badge, UserBadge


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
    """GET /api/v1/rewards/balance/ — current user's points balance + badges."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        return Response({
            'balance': RewardLedger.balance_for(user),
            'badges': UserBadgeSerializer(
                UserBadge.objects.filter(user=user).select_related('badge'),
                many=True,
            ).data,
        })


class HistoryView(generics.ListAPIView):
    """GET /api/v1/rewards/history/ — paginated ledger for current user."""
    serializer_class = RewardLedgerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RewardLedger.objects.filter(user=self.request.user)
