"""User model for the Alluora platform.

We have two kinds of users:
  - Admin/staff users (login to the dashboard with email + password)
  - End users (the mobile app's customers — sourced from WordPress)

End-user records are mirrored from WordPress on first contact. We store the
WP user ID and email so we can attach reward points, quiz results, etc.
without having to call WordPress for every read.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class AppUser(AbstractUser):
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

    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-date_joined',)

    def __str__(self):
        return self.email or self.username

    @property
    def display_name_or_email(self):
        return self.get_full_name() or self.email or self.username
