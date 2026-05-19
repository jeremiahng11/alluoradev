"""Bootstrap the dashboard admin user from environment variables.

Idempotent — safe to run on every deploy. If the user exists, it will
reset the password and ensure admin flags are set, but won't duplicate.

Trigger: include `python manage.py create_admin` in the Railway release command.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = 'Create or refresh the dashboard admin user from BOOTSTRAP_ADMIN_* env vars.'

    def handle(self, *args, **options):
        email = settings.BOOTSTRAP_ADMIN_EMAIL
        password = settings.BOOTSTRAP_ADMIN_PASSWORD
        username = settings.BOOTSTRAP_ADMIN_USERNAME or 'admin'

        if not email or not password:
            self.stdout.write(self.style.WARNING(
                'BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD not set; skipping.'
            ))
            return

        user, created = User.objects.get_or_create(
            email=email,
            defaults={'username': username},
        )

        # Always enforce admin flags + current password from env.
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.is_dashboard_admin = True
        # The bootstrap admin is the "main" / owner account — invisible
        # to and unrevokable by any other admin created later through
        # the dashboard. Only ever raises the flag, never lowers it,
        # and ALSO only takes effect if no other main admin already
        # exists (so a transferred-ownership setup isn't clobbered by
        # the next deploy).
        if not user.is_main_admin:
            other_main = (
                User.objects
                .filter(is_main_admin=True)
                .exclude(pk=user.pk)
                .exists()
            )
            if not other_main:
                user.is_main_admin = True
        if not user.username:
            user.username = username
        user.save()

        verb = 'Created' if created else 'Updated'
        main_note = ' (main)' if user.is_main_admin else ''
        self.stdout.write(self.style.SUCCESS(
            f'{verb} dashboard admin: {email}{main_note}'
        ))
