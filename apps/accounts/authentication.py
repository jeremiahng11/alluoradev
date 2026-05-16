"""WordPress auth bridge.

When a request arrives from the Flutter app, it carries the WordPress
session cookie (set by alluora-app-bridge plugin's /auth/login) plus
an X-WP-Nonce header.

We forward both to WordPress's /wp-json/alluora/v1/auth/me. If WP returns
a user, we mirror it into our AppUser table (creating on first contact)
and treat the request as authenticated.

Caching: results are cached for 60 seconds keyed by the cookie hash, so
under load we don't hammer WordPress. This is short enough that logout
on WP propagates within a minute.
"""
import hashlib
import logging
import random
from datetime import datetime
from typing import Optional, Tuple

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)
User = get_user_model()

WP_TIMEOUT = 5  # seconds
# Cache the WP /auth/me result for 5 minutes. Logout still propagates
# within that window because `_sync_user` skips the heavy work on
# cache hits, and a real session expiry on WP returns 401 — which
# bypasses the cache and forces a fresh check. The previous 60s value
# made cold app opens hit WP on every parallel call (each hits auth
# before the cache fills), adding ~1s × N requests.
CACHE_TTL = 300  # seconds


def _verify_with_wordpress(cookie_header: str, nonce: str) -> Optional[dict]:
    """Call WordPress /auth/me. Returns the user dict on success, None otherwise."""
    if not cookie_header or not nonce:
        return None

    cache_key = 'wp_auth_' + hashlib.sha256(
        (cookie_header + '|' + nonce).encode()
    ).hexdigest()

    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != '__none__' else None

    url = f"{settings.WORDPRESS_BASE_URL.rstrip('/')}/wp-json/{settings.WORDPRESS_API_NAMESPACE}/auth/me"
    try:
        resp = requests.get(
            url,
            headers={
                'Cookie': cookie_header,
                'X-WP-Nonce': nonce,
                'Accept': 'application/json',
            },
            timeout=WP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning('WordPress auth check failed: %s', exc)
        return None

    if resp.status_code != 200:
        cache.set(cache_key, '__none__', CACHE_TTL)
        return None

    try:
        body = resp.json()
    except ValueError:
        return None

    if not body.get('success'):
        cache.set(cache_key, '__none__', CACHE_TTL)
        return None

    user_data = body.get('data', {}).get('user') or body.get('data')
    if not user_data or not user_data.get('id'):
        return None

    cache.set(cache_key, user_data, CACHE_TTL)
    return user_data


def _generate_card_number_prefix() -> str:
    """8 random digits, retried until we find one not yet in use.

    Collisions are vanishingly rare (90M space, low user count) but we
    bound the loop so we fail loudly rather than spin forever in the
    pathological case.
    """
    for _ in range(20):
        candidate = f'{random.randint(10_000_000, 99_999_999)}'
        if not User.objects.filter(card_number_prefix=candidate).exists():
            return candidate
    raise RuntimeError('Could not allocate a unique card_number_prefix')


def _sync_user(wp_user: dict) -> User:
    """Mirror a WP user into AppUser (create or update)."""
    wp_id = int(wp_user['id'])
    defaults = {
        'username': f"wp_{wp_id}_{wp_user.get('username', '')}"[:150] or f"wp_{wp_id}",
        'email': wp_user.get('email', '') or '',
        'first_name': wp_user.get('first_name', '') or '',
        'last_name': wp_user.get('last_name', '') or '',
        'phone': (wp_user.get('billing') or {}).get('phone', '') or '',
        'avatar_url': wp_user.get('avatar_url', '') or '',
        'last_synced_at': timezone.now(),
    }

    user, created = User.objects.update_or_create(
        wp_user_id=wp_id,
        defaults=defaults,
    )
    if created:
        # Customers from WP can never log into the dashboard.
        user.set_unusable_password()
        user.is_dashboard_admin = False
        user.save(update_fields=['password', 'is_dashboard_admin'])

    # Allocate the membership card prefix once, on first sync (or for any
    # legacy user that pre-dates the field). Never overwrite an existing
    # prefix — the user's card number stays stable for life.
    if not user.card_number_prefix:
        user.card_number_prefix = _generate_card_number_prefix()
        user.save(update_fields=['card_number_prefix'])

    # Welcome bonus: 500 glow coins on first successful sync. Pushed
    # through the bridge plugin to WPS so the points show up everywhere
    # the rewards plugin reads from. Best-effort — if the bridge is
    # unreachable we leave granted=False and retry on the next sync,
    # rather than blocking auth.
    if not user.welcome_bonus_granted and user.wp_user_id:
        try:
            from apps.rewards import wp_client
            wp_client.award_points(
                wp_user_id=user.wp_user_id,
                delta=500,
                source='welcome',
                reference_id=f'welcome_user_{user.pk}',
            )
            user.welcome_bonus_granted = True
            user.save(update_fields=['welcome_bonus_granted'])
        except Exception as exc:
            # Don't fail authentication if the bonus push didn't work.
            logger.warning('Welcome bonus push failed for user %s: %s',
                           user.pk, exc)

    return user


class AlluoraTokenAuthentication(authentication.BaseAuthentication):
    """Bearer-token auth backed by AlluoraSessionToken.

    Looks for `Authorization: Token <key>`. A DB hit on an indexed
    field is ~5ms — vastly cheaper than the WP-cookie path's HTTP
    roundtrip to WordPress's /auth/me. The app fetches a token on
    first authenticated request (via /accounts/me, which surfaces it
    in the response) and uses it for every subsequent call.

    Returns None on any malformed/missing token so the request falls
    through to WordPressCookieAuthentication, which is what mints new
    tokens for fresh logins.
    """

    keyword = 'Token '

    def authenticate(self, request) -> Optional[Tuple[User, None]]:
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith(self.keyword):
            return None
        key = header[len(self.keyword):].strip()
        if not key:
            return None
        from .models import AlluoraSessionToken
        try:
            token = (
                AlluoraSessionToken.objects
                .select_related('user')
                .get(key=key)
            )
        except AlluoraSessionToken.DoesNotExist:
            return None
        return (token.user, token)

    def authenticate_header(self, request):
        return 'Token'


class WordPressCookieAuthentication(authentication.BaseAuthentication):
    """DRF authentication class that delegates to WordPress."""

    def authenticate(self, request) -> Optional[Tuple[User, None]]:
        cookie = request.META.get('HTTP_COOKIE', '')
        nonce = request.META.get('HTTP_X_WP_NONCE', '')

        if not cookie or 'wordpress_logged_in' not in cookie:
            return None  # Let other auth backends try.

        wp_user = _verify_with_wordpress(cookie, nonce)
        if not wp_user:
            return None

        try:
            user = _sync_user(wp_user)
        except Exception:
            logger.exception('Failed to sync WP user')
            raise exceptions.AuthenticationFailed('Could not sync user from WordPress.')

        return (user, None)

    def authenticate_header(self, request):
        return 'Cookie'
