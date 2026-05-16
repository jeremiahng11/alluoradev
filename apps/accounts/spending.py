"""Customer-spending sync + tier auto-upgrade.

Pulls lifetime WooCommerce spending from the bridge plugin
(/sync/customers/{id}/spending) and, after persisting it onto the
AppUser, picks the highest TierRule the user qualifies for. Invite-only
tiers (Titanium) are skipped — admins assign those manually.

Called from:
  - The dashboard `Sync Spending` button on the user detail page.
  - The dashboard `Sync All` button on the Membership page (in a
    ThreadPoolExecutor for speed).
  - Future: a periodic management command / cron.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.rewards import wp_client

User = get_user_model()
logger = logging.getLogger(__name__)


def sync_user_spending(user) -> Optional[dict]:
    """Fetch the user's WC spending and persist it. Returns the bridge
    payload, or None if the user has no wp_user_id or the bridge call
    fails. Always best-effort — never raises."""
    if not getattr(user, 'wp_user_id', None):
        return None
    try:
        data = wp_client.get_customer_spending(user.wp_user_id)
    except wp_client.BridgeError as exc:
        logger.warning(
            'Spending sync failed for user %s (wp=%s): %s',
            user.pk, user.wp_user_id, exc,
        )
        return None

    total = Decimal(str(data.get('total_spent', 0) or 0))
    user.total_spent = total
    user.spending_synced_at = timezone.now()

    new_tier = pick_tier_for_spend(total, current_tier=user.tier)
    update_fields = ['total_spent', 'spending_synced_at']
    if new_tier and new_tier != user.tier:
        user.tier = new_tier
        update_fields.append('tier')
    user.save(update_fields=update_fields)
    return data


def pick_tier_for_spend(total_spent: Decimal,
                        current_tier: Optional[str] = None) -> Optional[str]:
    """Return the tier the user qualifies for based on their spend.

    Rules:
      1. Invite-only tiers (TierRule.is_invite_only=True) are never
         picked automatically — once an admin assigns them, we don't
         downgrade no matter what the spending says.
      2. Otherwise pick the highest-min-spent rule whose threshold the
         user has met.

    Returns None if there are no rules or no rule matches.
    """
    from .models import TierRule

    # Don't strip invite-only tiers — admins set those manually and a
    # spend-based check shouldn't downgrade them.
    if current_tier:
        try:
            current_rule = TierRule.objects.get(tier=current_tier)
            if current_rule.is_invite_only:
                return current_tier
        except TierRule.DoesNotExist:
            pass

    qualifying = (
        TierRule.objects
        .filter(is_invite_only=False, min_spent__lte=total_spent)
        .order_by('-min_spent')
    )
    rule = qualifying.first()
    return rule.tier if rule else None
