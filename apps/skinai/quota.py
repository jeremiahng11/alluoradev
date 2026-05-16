"""Tier-aware quota & pricing for Skin AI.

Resolves "can this user run another scan, and if so, does it cost
coins" by reading SkinAiTierConfig for the user's tier, counting
existing scans in the current period, and consulting the user's
Glow Coin balance (via WP bridge) if a paid scan is required.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .models import SkinAiTierConfig, SkinAnalysis

logger = logging.getLogger(__name__)


@dataclass
class QuotaDecision:
    """Result of the pre-flight check the view runs before analysing."""
    allowed: bool
    cost: int               # Glow Coins to deduct (0 = free)
    reason: Optional[str]   # Human-readable; surfaced to the user
    used_in_period: int     # How many scans the user already did this period
    free_quota: int         # The tier's free allocation
    unlimited: bool         # Titanium / invitation-only override
    period_unit: str        # day / week / month


def _config_for_tier(tier: str) -> SkinAiTierConfig:
    """Look up the rules for a tier. Falls back to a sane default if
    admin hasn't created a row yet (no scans, 50 coins/each)."""
    try:
        return SkinAiTierConfig.objects.get(tier=tier)
    except SkinAiTierConfig.DoesNotExist:
        logger.info(
            'No SkinAiTierConfig for tier=%s — using default (50/scan, '
            'no free quota)', tier,
        )
        return SkinAiTierConfig(
            tier=tier,
            free_scans_per_period=0,
            period_unit='week',
            coin_cost_per_scan=50,
            unlimited_free=False,
        )


def check_quota(user, balance: int) -> QuotaDecision:
    """Decide whether `user` is allowed to run another scan right now.
    `balance` is the user's current Glow Coin balance (caller fetches
    it via WP bridge before calling). The decision is read-only — the
    caller must call `consume_scan` after a successful analysis to
    actually deduct coins and refresh balances."""
    tier = getattr(user, 'tier', None) or SkinAiTierConfig.TIER_GUEST
    cfg = _config_for_tier(tier)

    if cfg.unlimited_free:
        return QuotaDecision(
            allowed=True, cost=0, reason=None,
            used_in_period=0, free_quota=0, unlimited=True,
            period_unit=cfg.period_unit,
        )

    period_start = cfg.period_start()
    used = SkinAnalysis.objects.filter(
        user=user, created_at__gte=period_start,
    ).count()

    if used < cfg.free_scans_per_period:
        return QuotaDecision(
            allowed=True, cost=0, reason=None,
            used_in_period=used, free_quota=cfg.free_scans_per_period,
            unlimited=False, period_unit=cfg.period_unit,
        )

    # Free quota exhausted — need to pay coins.
    cost = cfg.coin_cost_per_scan
    if cost <= 0:
        # Misconfigured (no free quota, no paid path either) — block.
        return QuotaDecision(
            allowed=False, cost=0,
            reason='Skin AI is not available for your tier right now.',
            used_in_period=used, free_quota=cfg.free_scans_per_period,
            unlimited=False, period_unit=cfg.period_unit,
        )

    if balance < cost:
        return QuotaDecision(
            allowed=False, cost=cost,
            reason=(
                f'You’ve used your {cfg.free_scans_per_period} free scans '
                f'this {cfg.period_unit}. Next scan costs {cost} Glow Coins '
                f'— you currently have {balance}.'
            ),
            used_in_period=used, free_quota=cfg.free_scans_per_period,
            unlimited=False, period_unit=cfg.period_unit,
        )

    return QuotaDecision(
        allowed=True, cost=cost,
        reason=(
            f'Free quota exhausted — this scan will cost {cost} Glow Coins.'
        ),
        used_in_period=used, free_quota=cfg.free_scans_per_period,
        unlimited=False, period_unit=cfg.period_unit,
    )
