"""Reward points and badges for the Alluora app.

Architecture: an event-sourced ledger. Every points adjustment is an immutable
row. The user's balance is a sum. This makes auditing trivial and prevents the
usual race conditions of mutable counters.
"""
from django.conf import settings
from django.db import models
from django.db.models import Sum


class RewardLedger(models.Model):
    """Append-only ledger of points adjustments."""
    SOURCE_PURCHASE = 'purchase'
    SOURCE_QUIZ = 'quiz'
    SOURCE_VIDEO = 'video'
    SOURCE_REFERRAL = 'referral'
    SOURCE_REDEMPTION = 'redemption'
    SOURCE_MANUAL = 'manual'
    SOURCE_CHOICES = (
        (SOURCE_PURCHASE, 'Purchase'),
        (SOURCE_QUIZ, 'Quiz completion'),
        (SOURCE_VIDEO, 'Video watched'),
        (SOURCE_REFERRAL, 'Referral'),
        (SOURCE_REDEMPTION, 'Redemption'),
        (SOURCE_MANUAL, 'Manual adjustment'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reward_entries',
    )
    points = models.IntegerField(help_text='Positive = earn, negative = spend.')
    source = models.CharField(max_length=24, choices=SOURCE_CHOICES)
    description = models.CharField(max_length=200, blank=True)
    reference_id = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Optional external id (Woo order id, quiz id, etc).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reward_entries_created',
    )

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=['user', '-created_at'])]
        verbose_name_plural = 'Reward ledger entries'

    def __str__(self):
        return f'{self.user_id}: {self.points:+d} ({self.source})'

    @classmethod
    def balance_for(cls, user) -> int:
        return cls.objects.filter(user=user).aggregate(total=Sum('points'))['total'] or 0


class Badge(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.CharField(max_length=300, blank=True)
    icon = models.ImageField(upload_to='badges/', blank=True, null=True)
    icon_url = models.URLField(blank=True, default='')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    @property
    def icon_resolved(self) -> str:
        return self.icon.url if self.icon else self.icon_url


class UserBadge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='badges',
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('user', 'badge'),)
        ordering = ('-awarded_at',)

    def __str__(self):
        return f'{self.user_id}: {self.badge.name}'
