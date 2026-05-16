"""Per-tier score averaging for the in-app "vs <tier> average" block.

Currently dormant — the helper returns {} until each tier has at
least settings.SKINAI_TIER_AVG_MIN_USERS distinct users with at
least one scan in the last 90 days. Once that threshold is met the
serializer starts emitting tier_comparison and the Flutter side can
render the "your hydration is 8 above the Gold average" delta.

Cached for settings.SKINAI_TIER_AVG_CACHE_TTL seconds so the
expensive aggregation only runs once per refresh window.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Mapping, Optional

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY = 'skinai_tier_averages_v1'

# Score fields we average. Headline + the five user-facing concerns.
_AVG_FIELDS = (
    'overall_score',
    'hydration_score',
    'pores_score',
    'wrinkles_score',
    'redness_score',
    'spots_score',
)

# Window for "recent" — older scans are excluded so the averages
# track the current population's skin, not historical noise.
_WINDOW_DAYS = 90


def _compute() -> dict:
    """Heavy aggregation. Wrapped by `tier_averages()` for caching.

    Returns a {tier_slug: {avg_field: int, sample_size: int}} map,
    or {} when any participating tier is below the user-count floor.
    """
    from apps.skinai.models import SkinAnalysis
    from apps.accounts.models import AppUser

    floor = getattr(settings, 'SKINAI_TIER_AVG_MIN_USERS', 10)
    cutoff = timezone.now() - timedelta(days=_WINDOW_DAYS)

    # Distinct users per tier with at least one recent scan.
    distinct_per_tier = (
        SkinAnalysis.objects
        .filter(created_at__gte=cutoff)
        .values('user__tier')
        .annotate(distinct_users=Count('user', distinct=True))
    )
    tier_counts = {
        row['user__tier']: row['distinct_users']
        for row in distinct_per_tier
        if row['user__tier']
    }
    if not tier_counts:
        return {}

    # If ANY tier has data but is below floor, suppress the whole map.
    # Showing some tiers but not others would surface "no average for
    # your tier" inconsistently to users; better all-or-nothing until
    # the population is healthy across the board.
    if any(c < floor for c in tier_counts.values()):
        logger.info(
            'Skin AI tier averages: below %s-user floor (counts=%s) — '
            'returning empty', floor, tier_counts,
        )
        return {}

    out: dict = {}
    for tier in tier_counts:
        agg_args = {
            f'_avg_{f}': Avg(f) for f in _AVG_FIELDS
        }
        agg = (
            SkinAnalysis.objects
            .filter(user__tier=tier, created_at__gte=cutoff)
            .aggregate(**agg_args)
        )
        out[tier] = {
            f: int(round(agg[f'_avg_{f}'])) if agg.get(f'_avg_{f}') else 0
            for f in _AVG_FIELDS
        }
        out[tier]['sample_size'] = tier_counts[tier]

    # Suppress AppUser import warning on linters.
    _ = AppUser
    return out


def tier_averages(force_refresh: bool = False) -> dict:
    """Cached entry point. Empty dict means the feature is dormant
    (below floor) — callers should treat that as "don't render the
    comparison UI"."""
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached
    try:
        result = _compute()
    except Exception as exc:
        logger.warning('Skin AI tier_averages compute failed: %s', exc)
        result = {}
    ttl = getattr(settings, 'SKINAI_TIER_AVG_CACHE_TTL', 3600)
    cache.set(CACHE_KEY, result, ttl)
    return result


def comparison_for(analysis) -> dict:
    """Build the per-analysis comparison dict the serializer surfaces
    as `tier_comparison`. Returns {} when:
      - Tier averages are dormant (below floor)
      - Or the user has no tier set
      - Or the user's tier isn't represented in recent data

    Otherwise:
      {
        'tier':         tier slug,
        'sample_size':  int,
        'deltas':       {<score field>: int signed delta vs avg},
      }
    """
    user_tier = getattr(getattr(analysis, 'user', None), 'tier', None)
    if not user_tier:
        return {}
    averages = tier_averages()
    tier_block = averages.get(user_tier)
    if not tier_block:
        return {}
    deltas: dict = {}
    for field in _AVG_FIELDS:
        own = getattr(analysis, field, None)
        avg = tier_block.get(field)
        if isinstance(own, int) and isinstance(avg, int):
            deltas[field] = own - avg
    if not deltas:
        return {}
    return {
        'tier': user_tier,
        'sample_size': tier_block.get('sample_size', 0),
        'deltas': deltas,
    }
