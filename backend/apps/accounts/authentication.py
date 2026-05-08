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
CACHE_TTL = 60  # seconds


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

    return user


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
