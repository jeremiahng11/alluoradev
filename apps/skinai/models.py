"""Skin AI data model.

Two tables:

  - SkinAiTierConfig — admin-managed pricing rules. One row per
    membership tier. Decides how many free scans a member gets in a
    rolling day/week/month period, and how many Glow Coins each
    over-quota scan costs. `unlimited_free=True` overrides everything
    (used for Titanium / invitation-only members).

  - SkinAnalysis — one row per scan. Stores the structured scores
    (skin age, hydration, pores, wrinkles, redness, spots, overall),
    a 256x256 thumbnail of the photo, a hi-res original (admin-only),
    the coin cost (0 if free), and a raw_results JSON blob.

History is bounded per user (see MAX_SCANS_PER_USER) so the volume
doesn't grow without limit; new scans push the oldest off the end.
"""
from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone


# Per-user history cap. Hard limit enforced by the analyze endpoint
# after every successful scan. Scans past the cap are deleted oldest-
# first; the post_delete signal below removes the JPEG files from disk
# so storage stays bounded.
MAX_SCANS_PER_USER = 6


PERIOD_DAY = 'day'
PERIOD_WEEK = 'week'
PERIOD_MONTH = 'month'
PERIOD_CHOICES = (
    (PERIOD_DAY, 'Per day'),
    (PERIOD_WEEK, 'Per week'),
    (PERIOD_MONTH, 'Per month'),
)


class SkinAiTierConfig(models.Model):
    """Per-tier pricing & quota rules for the Skin AI feature.

    Admin sets one row per tier (Guest/Silver/Gold/Platinum/Titanium).
    The view layer reads the config for the requesting user's tier on
    every analyse request and decides: allowed for free, allowed for
    coins, or blocked (insufficient balance).
    """
    # 'none' = guest / anonymous. Other values match accounts.User.TIER_*
    TIER_GUEST = 'none'
    TIER_SILVER = 'Silver'
    TIER_GOLD = 'Gold'
    TIER_PLATINUM = 'Platinum'
    TIER_TITANIUM = 'Titanium'
    TIER_CHOICES = (
        (TIER_GUEST, 'Guest (anonymous)'),
        (TIER_SILVER, 'Silver'),
        (TIER_GOLD, 'Gold'),
        (TIER_PLATINUM, 'Platinum'),
        (TIER_TITANIUM, 'Titanium'),
    )

    tier = models.CharField(max_length=24, choices=TIER_CHOICES, unique=True)
    free_scans_per_period = models.PositiveIntegerField(
        default=0,
        help_text='Number of free scans inside one period. 0 = no free scans.',
    )
    period_unit = models.CharField(
        max_length=8, choices=PERIOD_CHOICES, default=PERIOD_WEEK,
    )
    coin_cost_per_scan = models.PositiveIntegerField(
        default=50,
        help_text='Glow Coins deducted for each scan past the free quota.',
    )
    unlimited_free = models.BooleanField(
        default=False,
        help_text='Overrides everything — scans are always free and unlimited '
                  '(used for invitation-only Titanium tier).',
    )

    class Meta:
        verbose_name = 'Skin AI tier config'
        verbose_name_plural = 'Skin AI tier configs'
        ordering = ('tier',)

    def __str__(self):
        if self.unlimited_free:
            return f'{self.get_tier_display()} — unlimited free'
        return (
            f'{self.get_tier_display()} — {self.free_scans_per_period} '
            f'free/{self.period_unit}, then {self.coin_cost_per_scan} coins/scan'
        )

    def period_start(self, now=None) -> 'timezone.datetime':
        """Floor `now` to the start of the configured period. Used to
        count quota usage inside the current window."""
        now = now or timezone.now()
        if self.period_unit == PERIOD_DAY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.period_unit == PERIOD_WEEK:
            # ISO week start (Monday 00:00). Good enough — doesn't
            # need to align to calendar weeks per locale.
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start - timezone.timedelta(days=start.weekday())
        # Month
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class SkinAnalysis(models.Model):
    """One skin AI analysis row. Stores both a 256x256 thumbnail (used by
    the in-app history view via the public /media/ URL) and the higher-
    resolution original (admin-only — streamed through an auth-gated
    dashboard view, never exposed via /media/ or the mobile API)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='skin_analyses',
    )
    thumbnail = models.ImageField(
        upload_to='skinai/thumbs/%Y/%m/', blank=True, null=True,
        help_text='256x256 JPEG of the analysed face shown in the app.',
    )
    original_photo = models.ImageField(
        upload_to='skinai/originals/%Y/%m/', blank=True, null=True,
        help_text='Hi-res JPEG of the analysed face (already capped to '
                  '1600px on the long side by the Flutter app). EXIF '
                  'rotation is baked in. Streamed only through the admin '
                  'dashboard — never returned by the mobile API.',
    )

    # All scores 0-100, higher = better skin. skin_age is years.
    skin_age = models.PositiveSmallIntegerField(null=True, blank=True)
    hydration_score = models.PositiveSmallIntegerField(default=0)
    pores_score = models.PositiveSmallIntegerField(default=0)
    wrinkles_score = models.PositiveSmallIntegerField(default=0)
    redness_score = models.PositiveSmallIntegerField(default=0)
    spots_score = models.PositiveSmallIntegerField(default=0)
    # Extended findings — added on top of the original five. All are
    # CV-proxy scores (no face landmark detection in the pipeline yet),
    # so they're directional rather than medical-grade. See pipeline.
    pigmentation_score = models.PositiveSmallIntegerField(default=0)
    acne_score = models.PositiveSmallIntegerField(default=0)
    dark_circles_score = models.PositiveSmallIntegerField(default=0)
    eyebags_score = models.PositiveSmallIntegerField(default=0)
    white_spots_score = models.PositiveSmallIntegerField(default=0)
    overall_score = models.PositiveSmallIntegerField(default=0)

    # Cost paid for this scan. 0 = within free quota (or unlimited tier).
    coin_cost = models.PositiveIntegerField(default=0)

    # Full debug blob (face bbox, raw OpenCV metrics, DeepFace output).
    # Useful for tuning the score-mapping curves later without re-running.
    raw_results = models.JSONField(default=dict, blank=True)

    # User-side soft delete. The mobile app sets this when the user
    # hides a scan from their own history — the row stays in the DB and
    # remains visible in the admin dashboard. (Admin-side delete is a
    # real delete, not a flag — see SkinAiUserBulkDeleteView.)
    hidden_from_user = models.BooleanField(default=False)

    # True when the pipeline couldn't read a face age (DeepFace returned
    # None) or the metrics looked degenerate. Surfaced as a "low
    # confidence — retake in better light" banner on the result screen
    # so the user knows the reading might be off.
    low_confidence = models.BooleanField(default=False)

    # Bumped whenever the scoring pipeline changes shape (new metrics,
    # different math). Old rows default to 1; current pipeline is 2.
    # The serializer exposes this so the result screen can hide
    # categories the row was never scored on.
    pipeline_version = models.PositiveSmallIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]
        verbose_name_plural = 'Skin analyses'

    def __str__(self):
        return f'{self.user_id} — age {self.skin_age}, overall {self.overall_score}'


class SkinCheckIn(models.Model):
    """Lightweight progress snapshot — daily 30-second tracking that
    runs the same pipeline as a full SkinAnalysis but persists only
    the headline numbers + a thumbnail. No insights, no recommendations,
    no hi-res original. Free, throttled to 1/day per user, capped at
    90 records (3 months of dailies).

    Sits alongside SkinAnalysis rather than reusing it because the
    use cases diverge: full scans drive insights + product recs +
    Glow Coin economics; check-ins exist to plot a trend line."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='skin_check_ins',
    )
    thumbnail = models.ImageField(
        upload_to='skinai/checkins/%Y/%m/', blank=True, null=True,
        help_text='256x256 face crop. Same encode as SkinAnalysis.thumbnail.',
    )
    skin_age = models.PositiveSmallIntegerField(null=True, blank=True)
    overall_score = models.PositiveSmallIntegerField(default=0)
    # Carry the most-asked-about per-metric scores so the trend chart
    # can split by category if we add that view later.
    hydration_score = models.PositiveSmallIntegerField(default=0)
    redness_score = models.PositiveSmallIntegerField(default=0)
    low_confidence = models.BooleanField(default=False)
    pipeline_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    MAX_PER_USER = 90  # ~3 months of daily check-ins

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]
        verbose_name = 'Skin check-in'
        verbose_name_plural = 'Skin check-ins'

    def __str__(self):
        return f'{self.user_id} check-in — overall {self.overall_score}'


@receiver(post_delete, sender=SkinCheckIn)
def _cleanup_check_in_files(sender, instance, **kwargs):
    """Same file-cleanup pattern as SkinAnalysis — when a check-in
    row is deleted (cap rollover, account delete, manual), drop the
    thumbnail JPEG from the volume."""
    if instance.thumbnail:
        try:
            instance.thumbnail.delete(save=False)
        except Exception:
            pass


class SkinRoutineProduct(models.Model):
    """A product the user is actively using in their skincare routine.
    Captured manually — name + brand + slot (am/pm/both) + start date
    + optional notes. Doesn't sync with WooCommerce; this is the user's
    own log so the trend chart can correlate "started using vitamin C"
    against scan score moves later.

    Soft-end via `ended_at` so historical routines stay visible — the
    user can see "I used X for 6 weeks, my brightening went from
    50 → 72 in that window"."""

    SLOT_AM = 'am'
    SLOT_PM = 'pm'
    SLOT_BOTH = 'both'
    SLOT_CHOICES = (
        (SLOT_AM, 'Morning'),
        (SLOT_PM, 'Evening'),
        (SLOT_BOTH, 'Morning + evening'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='skin_routine_products',
    )
    name = models.CharField(max_length=120)
    brand = models.CharField(max_length=80, blank=True, default='')
    slot = models.CharField(
        max_length=8, choices=SLOT_CHOICES, default=SLOT_BOTH,
    )
    started_at = models.DateField(blank=True, null=True)
    ended_at = models.DateField(
        blank=True, null=True,
        help_text='When set, the product is no longer active. Kept for '
                  'historical correlation against past scans.',
    )
    notes = models.CharField(max_length=240, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-started_at', '-created_at')
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]
        verbose_name = 'Skin routine product'

    def __str__(self):
        end = f' (ended {self.ended_at})' if self.ended_at else ''
        return f'{self.user_id}: {self.brand} {self.name}{end}'

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


@receiver(post_delete, sender=SkinAnalysis)
def _cleanup_skin_analysis_files(sender, instance, **kwargs):
    """When a SkinAnalysis row is deleted (admin cleanup, the per-user
    cap rolling oldest off the end, or anything else), remove the
    thumbnail and the hi-res original from the volume too. Default
    Django behavior leaves the JPEGs orphaned on disk — we want them
    gone so storage stays bounded."""
    for field in (instance.thumbnail, instance.original_photo):
        if field:
            try:
                field.delete(save=False)
            except Exception:
                # Best-effort — a missing file (e.g., wiped by an
                # earlier ephemeral-disk redeploy) shouldn't block the
                # row delete itself.
                pass
