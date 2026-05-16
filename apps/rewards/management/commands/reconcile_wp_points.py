"""Backfill the local ledger from WordPress.

For every AppUser with a wp_user_id, fetch their current WPS Points balance
via the bridge plugin and insert a single SOURCE_MANUAL ledger row
representing the opening balance. Idempotent — re-runs skip users that
already have an opening-balance row (matched by reference_id).

    python manage.py reconcile_wp_points
    python manage.py reconcile_wp_points --dry-run
    python manage.py reconcile_wp_points --user-id 1683

Run this once after deploying the bridge v2.2.2 + ALLUORA_BRIDGE_SECRET so
the Django ledger has a starting point. Future Django-originated earns
(quiz, video) append on top via the normal push path.
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import AppUser
from apps.rewards import wp_client
from apps.rewards.models import RewardLedger


class Command(BaseCommand):
    help = 'Backfill the local ledger with current WPS Points balance per user.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would happen, do not write to the ledger.',
        )
        parser.add_argument(
            '--user-id', type=int, default=None,
            help='Only reconcile this WP user_id (otherwise: all AppUsers).',
        )

    def handle(self, *args, **opts):
        dry_run = opts.get('dry_run', False)
        only_user = opts.get('user_id')

        qs = AppUser.objects.filter(wp_user_id__isnull=False).exclude(wp_user_id=0)
        if only_user:
            qs = qs.filter(wp_user_id=only_user)

        total = qs.count()
        if total == 0:
            self.stdout.write('No AppUsers with wp_user_id to reconcile.')
            return

        self.stdout.write(f'Reconciling {total} user(s){" (dry run)" if dry_run else ""}...')

        inserted = 0
        skipped = 0
        failed = 0

        for user in qs.iterator():
            ref = f'wp_opening_balance_{user.wp_user_id}'

            if RewardLedger.objects.filter(user=user, reference_id=ref).exists():
                self.stdout.write(f'  skip wp_user={user.wp_user_id}: already reconciled')
                skipped += 1
                continue

            try:
                summary = wp_client.get_user_summary(user.wp_user_id, use_cache=False)
            except wp_client.BridgeError as exc:
                self.stderr.write(f'  fail wp_user={user.wp_user_id}: {exc}')
                failed += 1
                continue

            balance = int(summary.get('total_points') or 0)
            if balance == 0:
                self.stdout.write(f'  skip wp_user={user.wp_user_id}: WP balance is 0')
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  WOULD insert {balance} pts for wp_user={user.wp_user_id} '
                    f'(django user pk={user.pk})'
                )
                continue

            RewardLedger.objects.create(
                user=user,
                points=balance,
                source=RewardLedger.SOURCE_MANUAL,
                description='Opening balance from WordPress',
                reference_id=ref,
            )
            self.stdout.write(
                f'  ok   wp_user={user.wp_user_id}: +{balance} pts'
            )
            inserted += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. inserted={inserted} skipped={skipped} failed={failed}'
        ))
