"""User model for the Alluora platform.

We have two kinds of users:
  - Admin/staff users (login to the dashboard with email + password)
  - End users (the mobile app's customers — sourced from WordPress)

End-user records are mirrored from WordPress on first contact. We store the
WP user ID and email so we can attach reward points, quiz results, etc.
without having to call WordPress for every read.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class AppUser(AbstractUser):
    TIER_SILVER = 'Silver'
    TIER_GOLD = 'Gold'
    TIER_PLATINUM = 'Platinum'
    TIER_TITANIUM = 'Titanium'
    TIER_CHOICES = (
        (TIER_SILVER, 'Silver'),
        (TIER_GOLD, 'Gold'),
        (TIER_PLATINUM, 'Platinum'),
        (TIER_TITANIUM, 'Titanium'),
    )

    # WordPress-sourced fields. Null/blank for staff-only accounts.
    wp_user_id = models.PositiveIntegerField(
        unique=True, null=True, blank=True,
        help_text='Mirrors the WordPress user ID. Null for dashboard-only admins.',
    )
    phone = models.CharField(max_length=32, blank=True, default='')
    avatar_url = models.URLField(blank=True, default='')

    # Distinguish dashboard staff from app customers without abusing is_staff.
    is_dashboard_admin = models.BooleanField(
        default=False,
        help_text='Can sign into the custom admin dashboard.',
    )
    # The "main admin" — typically the bootstrap account created by
    # `manage.py create_admin`. Hidden from the Admins list/edit views
    # for every OTHER dashboard admin, and cannot be revoked by anyone
    # else. Only one row should have this set at a time (enforced by
    # the dashboard create-admin view, which never raises the flag).
    is_main_admin = models.BooleanField(
        default=False,
        help_text='Owner account — invisible to other dashboard admins '
                  'and protected from being demoted/deleted by them.',
    )

    # Membership card. The 8-digit prefix is generated server-side on first
    # sync and never changes; the visible card number on the app combines
    # this prefix with the user's wp_user_id (zero-padded to 4 digits) for
    # the trailing block, e.g. "1234 5678 1683" for prefix 12345678 + WP
    # user 1683.
    card_number_prefix = models.CharField(
        max_length=8, null=True, blank=True, unique=True,
        help_text='8-digit prefix; combined with last 4 of wp_user_id to form the visible membership card number.',
    )
    tier = models.CharField(
        max_length=24, choices=TIER_CHOICES, default=TIER_SILVER,
        help_text='Membership tier — managed on Django, not WordPress.',
    )
    welcome_bonus_granted = models.BooleanField(
        default=False,
        help_text='True once the 500-point Silver welcome bonus has been '
                  'pushed to the WP rewards plugin via the bridge.',
    )

    # WooCommerce-mirrored lifetime spend. Synced from the bridge plugin
    # via /sync/customers/{id}/spending and used by TierRule to decide
    # automatic upgrades (e.g. spend > $1000 → Gold).
    total_spent = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Lifetime WooCommerce spend in store currency.',
    )
    spending_synced_at = models.DateTimeField(null=True, blank=True)

    last_synced_at = models.DateTimeField(null=True, blank=True)

    # Skin AI personalisation. Captured by the in-app onboarding bottom
    # sheet on first scan attempt. Used by apps/skinai/pipeline.analyse
    # to retune sex-specific thresholds and by apps/skinai/insights to
    # weight the recommendation copy toward the user's primary concern.
    SKIN_SEX_UNSPECIFIED = ''
    SKIN_SEX_FEMALE = 'female'
    SKIN_SEX_MALE = 'male'
    SKIN_SEX_OTHER = 'other'
    SKIN_SEX_CHOICES = (
        (SKIN_SEX_UNSPECIFIED, 'Not set'),
        (SKIN_SEX_FEMALE, 'Female'),
        (SKIN_SEX_MALE, 'Male'),
        (SKIN_SEX_OTHER, 'Prefer not to say'),
    )
    skin_sex = models.CharField(
        max_length=12, blank=True, default=SKIN_SEX_UNSPECIFIED,
        choices=SKIN_SEX_CHOICES,
    )

    # Stored as a comma-separated list of concern slugs from
    # SKIN_CONCERN_VALID. Empty string = "not set". Multi-select so the
    # insight engine can target whichever of the user's stated concerns
    # is currently scoring lowest.
    SKIN_CONCERN_VALID = (
        'hydration', 'aging', 'acne', 'brightening', 'sensitivity',
        'pigmentation', 'dark_circles', 'eyebags', 'white_spots',
        'pores',
    )
    skin_primary_concern = models.CharField(
        max_length=128, blank=True, default='',
        help_text='Comma-separated concern slugs: any of '
                  + ', '.join(SKIN_CONCERN_VALID),
    )
    # Optional. Used by apps/skinai/insights to compare DeepFace's
    # skin_age estimate against the user's real age and surface
    # "reads N years older / younger than you actually are" guidance.
    birthday = models.DateField(blank=True, null=True)

    @property
    def age_years(self):
        """Real age in whole years from birthday, or None if unset."""
        if not self.birthday:
            return None
        from datetime import date
        today = date.today()
        years = today.year - self.birthday.year
        if (today.month, today.day) < (self.birthday.month, self.birthday.day):
            years -= 1
        return max(0, years)

    class Meta:
        ordering = ('-date_joined',)

    def __str__(self):
        return self.email or self.username

    @property
    def display_name_or_email(self):
        return self.get_full_name() or self.email or self.username

    @property
    def membership_number(self):
        """Full 12-digit membership number, prefix + zero-padded WP id."""
        if not self.card_number_prefix or not self.wp_user_id:
            return None
        return f'{self.card_number_prefix}{str(self.wp_user_id).zfill(4)}'


class AlluoraSessionToken(models.Model):
    """Long-lived bearer token issued after the first WP-cookie auth.

    Lets the app skip the WP `/auth/me` HTTP roundtrip on every Django
    call — a token lookup hits the local DB in a few ms vs ~500ms for
    the WP roundtrip. Token is per-user (one row each) and is reissued
    on logout.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='alluora_token',
    )
    key = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_or_issue(cls, user) -> 'AlluoraSessionToken':
        import secrets
        token, _ = cls.objects.get_or_create(
            user=user,
            defaults={'key': secrets.token_hex(32)},
        )
        return token


class TierRule(models.Model):
    """Admin-editable rules that drive automatic tier upgrades.

    Each row maps one tier to a minimum spending threshold. When the
    spending sync runs we pick the highest-rank tier whose threshold
    the user has met (skipping any rule with `is_invite_only=True` —
    Titanium etc are admin-assigned only and ignore spend).

    The rules are seeded with the four production tiers but admins can
    edit thresholds via the Membership page on the dashboard.
    """
    TIER_RANK = {
        'Silver': 1,
        'Gold': 2,
        'Platinum': 3,
        'Titanium': 4,
    }

    tier = models.CharField(
        max_length=24, unique=True,
        help_text='One of Silver / Gold / Platinum / Titanium.',
    )
    min_spent = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Minimum lifetime WooCommerce spend (store currency) '
                  'required to qualify. Ignored if invite-only.',
    )
    is_invite_only = models.BooleanField(
        default=False,
        help_text="When true, this tier ignores spending — admins must "
                  "assign it manually. The app's card screen also "
                  "displays a custom label (e.g. 'INVITE ONLY' for "
                  "Titanium) instead of '<TIER> MEMBER'.",
    )
    card_label_subtitle = models.CharField(
        max_length=64, blank=True, default='',
        help_text="Subtitle shown under the tier name on the membership "
                  "card in the app (e.g. 'VIP MEMBER', 'INVITE ONLY'). "
                  "Leave empty to show the default 'MEMBER'.",
    )
    perks_description = models.TextField(
        blank=True, default='',
        help_text="Member benefits for this tier — shown in the app's "
                  "tier ladder. One perk per line works best; the app "
                  "renders bullet points.",
    )

    class Meta:
        ordering = ('min_spent',)

    def __str__(self):
        if self.is_invite_only:
            return f'{self.tier} (invite only)'
        return f'{self.tier} ≥ ${self.min_spent}'

    @property
    def rank(self) -> int:
        return self.TIER_RANK.get(self.tier, 0)
