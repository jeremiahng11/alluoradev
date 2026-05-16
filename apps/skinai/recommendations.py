"""Product recommendations for Skin AI scans.

Pulls the WooCommerce product catalog via the existing public bridge
endpoint at /wp-json/alluora/v1/products, runs each product's name +
short_description + description through a keyword tagger, and returns
the top-N matching products for whichever skin concerns scored worst
on a given analysis.

This is a "Phase 1" implementation — keyword-based, no admin override
yet. If the keyword matches turn out to be noisy in practice, add
SkinAiProductTag (wc_product_id, manual_concerns) and prefer that
mapping over the keyword auto-tag.

Cache:
  Products are pulled once per CACHE_TTL and held in Django's cache.
  Recommendation calls are cheap; only the per-TTL refresh hits WP.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


CACHE_KEY = 'skinai_products_v1'
CACHE_TTL = 60 * 60  # 1 hour
WP_TIMEOUT = 8
WP_PER_PAGE = 100  # WC max
WP_MAX_PAGES = 5   # 500-product safety cap


# Concern slug → list of keywords (lowercase, substring match against
# product name + descriptions). Tuned for skincare ingredient names +
# common marketing phrases. Add to these as you notice patterns in the
# real catalog — they live here so changes don't need a deploy of any
# external service.
CONCERN_KEYWORDS: dict[str, tuple[str, ...]] = {
    'hydration': (
        'hydrating', 'hydration', 'moistur', 'hyaluronic', 'glycerin',
        'plumping', 'dewy', 'water cream', 'aqua', 'h2o',
    ),
    'aging': (
        'anti-aging', 'anti aging', 'antiaging', 'wrinkle', 'fine line',
        'retinol', 'retinoid', 'peptide', 'collagen', 'firming',
        'lifting', 'youth', 'rejuvenat',
    ),
    'acne': (
        'acne', 'breakout', 'blemish', 'pimple', 'salicylic',
        'benzoyl', 'tea tree', 'spot treatment', 'spot patch',
        'pore-clearing', 'mattifying', 'oil-control',
    ),
    'brightening': (
        'brightening', 'brighten', 'radiance', 'glow', 'illuminat',
        'vitamin c', 'l-ascorbic', 'kojic', 'arbutin', 'luminous',
    ),
    'sensitivity': (
        'sensitive', 'soothing', 'calming', 'centella', 'cica',
        'niacinamide', 'redness', 'gentle', 'fragrance-free',
        'panthenol', 'allantoin',
    ),
    'pigmentation': (
        'pigmentation', 'dark spot', 'melasma', 'discoloration',
        'even tone', 'tone correct', 'fade dark', 'hyperpigmen',
    ),
    'dark_circles': (
        'dark circle', 'eye cream', 'caffeine', 'under-eye',
        'undereye', 'under eye', 'eye serum',
    ),
    'eyebags': (
        'puffiness', 'puffy', 'eye bag', 'depuff', 'de-puff',
        'eye cream', 'eye gel',
    ),
    'white_spots': (
        'milia', 'white bump', 'white spot', 'keratin', 'exfoliant',
        'aha',
    ),
    'pores': (
        'pore', 'pore-refining', 'pore minimiser', 'pore minimizer',
        'bha', 'salicylic', 'clay mask', 'kaolin', 'charcoal',
        'mattifying', 'sebum',
    ),
}


def _strip_html(text: str) -> str:
    if not text:
        return ''
    return re.sub(r'<[^>]+>', ' ', text)


def tag_product(product: dict) -> list[str]:
    """Return the list of concern slugs that match this product's
    visible copy. Greedy — a product can be tagged with multiple
    concerns. Uses substring match against lowercased text; not
    stemmed.

    The bridge plugin's /products list call only includes `name` +
    `short_description` (full `description` is detail-only). That's
    enough for the keyword sweep so long as merchants pack the most
    important ingredients into the short copy; if matches feel sparse,
    we can do a second pass through /products/<id> for richer text.
    """
    name = (product.get('name') or '').lower()
    short = _strip_html(product.get('short_description') or '').lower()
    # `description` is detail-only but include if present (the
    # function is called from both list and detail contexts).
    full = _strip_html(product.get('description') or '').lower()
    haystack = f' {name} {short} {full} '
    matched = []
    for concern, keywords in CONCERN_KEYWORDS.items():
        for kw in keywords:
            if kw in haystack:
                matched.append(concern)
                break  # one keyword hit is enough to tag this concern
    return matched


def _fetch_products() -> list[dict]:
    """Page through the WP bridge plugin's products endpoint and
    return a list of normalized product dicts. Cached for CACHE_TTL."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    base = settings.WORDPRESS_BASE_URL.rstrip('/')
    products: list[dict] = []
    for page in range(1, WP_MAX_PAGES + 1):
        try:
            resp = requests.get(
                f'{base}/wp-json/alluora/v1/products',
                params={'page': page, 'per_page': WP_PER_PAGE},
                timeout=WP_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning('Skin AI rec: WP product fetch failed: %s', exc)
            break
        if resp.status_code != 200:
            logger.warning(
                'Skin AI rec: WP returned %s for products page %s',
                resp.status_code, page,
            )
            break
        try:
            payload = resp.json()
        except ValueError:
            logger.warning('Skin AI rec: non-JSON product response')
            break
        # Bridge plugin's AAB_Helpers::ok wraps responses as
        #   {success: true, data: {products: [...], total: N,
        #                          total_pages: N, page: N,
        #                          per_page: N}}
        # so reach through both .data and .products. Accept a bare
        # list too in case the plugin shape ever changes.
        items: list = []
        if isinstance(payload, dict):
            data = payload.get('data')
            if isinstance(data, dict) and isinstance(data.get('products'), list):
                items = data['products']
            elif isinstance(data, list):
                items = data
        elif isinstance(payload, list):
            items = payload
        if not items:
            break
        products.extend(items)
        if len(items) < WP_PER_PAGE:
            break

    cache.set(CACHE_KEY, products, CACHE_TTL)
    return products


def _score_against_concerns(
    product: dict,
    target_concerns: Iterable[str],
) -> int:
    """Return the number of target concerns this product matches.
    Higher = more relevant for the user's lowest-scoring categories."""
    tags = tag_product(product)
    targets = set(target_concerns)
    return sum(1 for t in tags if t in targets)


def lowest_concerns(scores: dict, top_n: int = 3) -> list[str]:
    """Return the top_n worst-scoring concern slugs (the ones the
    recommendation should target). Maps from the *_score field name
    back to the concern slug used for keyword tagging."""
    score_to_concern = {
        'hydration_score': 'hydration',
        'wrinkles_score': 'aging',
        'acne_score': 'acne',
        'spots_score': 'brightening',  # spots ≈ brightening concern
        'redness_score': 'sensitivity',
        'pigmentation_score': 'pigmentation',
        'dark_circles_score': 'dark_circles',
        'eyebags_score': 'eyebags',
        'white_spots_score': 'white_spots',
        'pores_score': 'pores',
    }
    pairs = [
        (concern, scores[key])
        for key, concern in score_to_concern.items()
        if isinstance(scores.get(key), int)
    ]
    pairs.sort(key=lambda kv: kv[1])
    # Dedupe concerns while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for concern, _ in pairs:
        if concern in seen:
            continue
        seen.add(concern)
        out.append(concern)
        if len(out) >= top_n:
            break
    return out


def _why_blurb(concerns: list[str]) -> str:
    """One-line "why this product" string built from the matched
    concerns. Kept short for card layout."""
    if not concerns:
        return ''
    pretty = {
        'hydration': 'hydration',
        'aging': 'fine lines',
        'acne': 'breakouts',
        'brightening': 'brightening',
        'sensitivity': 'sensitivity',
        'pigmentation': 'pigmentation',
        'dark_circles': 'dark circles',
        'eyebags': 'puffiness',
        'white_spots': 'white spots',
        'pores': 'pores',
    }
    labels = [pretty.get(c, c) for c in concerns[:2]]
    if len(labels) == 1:
        return f'Targets {labels[0]}'
    return f'Targets {labels[0]} + {labels[1]}'


def recommend_for_analysis(analysis, limit: int = 4) -> list[dict]:
    """Return up to `limit` product recommendations tailored to an
    analysis row's worst-scoring categories.

    Each item is:
      {
        'id':            int,    # WC product id
        'name':          str,
        'price':         str,    # raw HTML / '' if missing
        'image_url':     str,
        'permalink':     str,    # storefront URL
        'concerns':      list,   # the slugs this product matches
        'why':           str,    # one-line blurb for the card
      }
    """
    scores = {
        'hydration_score': analysis.hydration_score,
        'pores_score': analysis.pores_score,
        'wrinkles_score': analysis.wrinkles_score,
        'redness_score': analysis.redness_score,
        'spots_score': analysis.spots_score,
        'pigmentation_score': getattr(analysis, 'pigmentation_score', 0),
        'acne_score': getattr(analysis, 'acne_score', 0),
        'dark_circles_score': getattr(analysis, 'dark_circles_score', 0),
        'eyebags_score': getattr(analysis, 'eyebags_score', 0),
        'white_spots_score': getattr(analysis, 'white_spots_score', 0),
    }
    targets = lowest_concerns(scores, top_n=3)
    if not targets:
        return []
    products = _fetch_products()
    if not products:
        return []

    scored: list[tuple[int, dict, list[str]]] = []
    for p in products:
        tags = tag_product(p)
        matches = [t for t in tags if t in targets]
        if not matches:
            continue
        # Order matches by the order of targets so the most-needed
        # concern leads the why-blurb.
        ordered_matches = [t for t in targets if t in matches]
        scored.append((len(matches), p, ordered_matches))

    scored.sort(key=lambda triple: triple[0], reverse=True)

    out = []
    for _, p, matches in scored[:limit]:
        # The bridge plugin returns a single `image` URL on list items
        # (string, not array). Detail responses use `gallery` for
        # extras — not needed for the carousel thumbnail.
        image_url = p.get('image') or ''
        if not isinstance(image_url, str):
            image_url = ''
        # Format the price with the storefront currency when present.
        price_raw = p.get('price') or ''
        currency = (p.get('currency') or '').upper()
        if price_raw and currency:
            price_display = f'{currency} {price_raw}'
        else:
            price_display = str(price_raw)
        out.append({
            'id': p.get('id'),
            'name': p.get('name') or '',
            'price': price_display,
            'image_url': image_url,
            'permalink': p.get('permalink') or '',
            'concerns': matches,
            'why': _why_blurb(matches),
        })
    return out
