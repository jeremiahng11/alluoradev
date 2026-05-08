"""Accounts API.

The Flutter app already has /auth/* on WordPress, so we don't duplicate it.
We expose /api/v1/accounts/me which returns the Django-side user record
(mirroring + Alluora-specific fields like reward points balance).
"""
from rest_framework import serializers, generics, permissions
from .models import AppUser


class AppUserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='display_name_or_email', read_only=True)
    reward_points = serializers.SerializerMethodField()

    class Meta:
        model = AppUser
        fields = (
            'id', 'wp_user_id', 'email', 'first_name', 'last_name',
            'display_name', 'phone', 'avatar_url', 'reward_points',
            'last_synced_at',
        )
        read_only_fields = fields

    def get_reward_points(self, obj):
        # Avoid circular import.
        from apps.rewards.models import RewardLedger
        return RewardLedger.balance_for(obj)


class MeView(generics.RetrieveAPIView):
    """GET /api/v1/accounts/me — current end-user (Django-side mirror)."""
    serializer_class = AppUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
