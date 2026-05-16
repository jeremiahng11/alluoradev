"""HMAC-signed client for the WordPress alluora-app-bridge /sync/ routes.

The bridge plugin exposes service-to-service routes that take an HMAC
signature instead of a logged-in user cookie:

  GET  /wp-json/alluora/v1/sync/rewards/user/{id}   — read points
  POST /wp-json/alluora/v1/sync/rewards/award       — adjust points

Signature scheme (matches AAB_Helpers::verify_hmac_request in PHP):

    string_to_sign = METHOD + "\\n" + PATH + "\\n" + TIMESTAMP + "\\n" + md5(body)
    signature      = "sha256=" + hex( HMAC_SHA256(secret, string_to_sign) )

PATH is the REST route only (e.g. `/alluora/v1/sync/rewards/user/1683`),
without host or query string. TIMESTAMP is unix seconds; the bridge
rejects requests with skew > 300 seconds.
"""
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8
_CACHE_KEY_FMT = 'wp_rewards_summary:{wp_user_id}'


class BridgeError(Exception):
    """The bridge plugin returned an error or was unreachable."""


def _signed_request(method: str, path: str, body: str = '') -> dict:
    secret = settings.ALLUORA_BRIDGE_SECRET
    if not secret:
        raise BridgeError('ALLUORA_BRIDGE_SECRET is not configured')

    method = method.upper()
    timestamp = int(time.time())
    body_bytes = body.encode('utf-8') if isinstance(body, str) else body
    body_md5 = hashlib.md5(body_bytes).hexdigest()
    string_to_sign = f'{method}\n{path}\n{timestamp}\n{body_md5}'
    signature = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    url = f"{settings.WORDPRESS_BASE_URL.rstrip('/')}/wp-json{path}"
    headers = {
        'X-Alluora-Signature': signature,
        'X-Alluora-Timestamp': str(timestamp),
        'Accept': 'application/json',
    }
    if method == 'POST':
        headers['Content-Type'] = 'application/json'

    try:
        resp = requests.request(
            method,
            url,
            data=body_bytes if method == 'POST' else None,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning('WP bridge %s %s failed: %s', method, path, exc)
        raise BridgeError(f'Bridge unreachable: {exc}') from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise BridgeError(
            f'Non-JSON response from bridge ({resp.status_code})'
        ) from exc

    if resp.status_code >= 400 or not data.get('success'):
        msg = data.get('message') or f'Bridge error ({resp.status_code})'
        raise BridgeError(msg)

    return data.get('data', {})


def get_user_summary(wp_user_id: int, *, use_cache: bool = True) -> dict:
    """Read a user's points balance + tier from WP. Cached briefly.

    Returns the bridge's `data` payload:
        { user_id, total_points, referral_link, user_level }
    """
    cache_key = _CACHE_KEY_FMT.format(wp_user_id=int(wp_user_id))
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    path = f'/alluora/v1/sync/rewards/user/{int(wp_user_id)}'
    data = _signed_request('GET', path)

    if use_cache:
        cache.set(cache_key, data, settings.ALLUORA_POINTS_CACHE_TTL)
    return data


def award_points(
    wp_user_id: int,
    delta: int,
    *,
    source: str = 'manual',
    reference_id: Optional[str] = None,
) -> dict:
    """Adjust a user's points balance. delta may be negative (deduct).

    Returns: { user_id, previous, delta, total_points, source, reference_id }
    """
    body = json.dumps({
        'wp_user_id': int(wp_user_id),
        'delta': int(delta),
        'source': source,
        'reference_id': reference_id or '',
    }, separators=(',', ':'))

    path = '/alluora/v1/sync/rewards/award'
    data = _signed_request('POST', path, body=body)

    # The cached balance is now stale.
    cache.delete(_CACHE_KEY_FMT.format(wp_user_id=int(wp_user_id)))
    return data


def invalidate_cache(wp_user_id: int) -> None:
    cache.delete(_CACHE_KEY_FMT.format(wp_user_id=int(wp_user_id)))


def get_customer_spending(wp_user_id: int) -> dict:
    """Read a customer's lifetime WooCommerce spending via the bridge.

    Returns the bridge's `data` payload:
        { wp_user_id, total_spent (float), currency,
          order_count (int), last_order_at (ISO 8601 or null) }

    Used by `apps.accounts.spending.sync_user_spending` to mirror the
    value onto AppUser.total_spent and trigger a tier upgrade.
    """
    path = f'/alluora/v1/sync/customers/{int(wp_user_id)}/spending'
    return _signed_request('GET', path)
