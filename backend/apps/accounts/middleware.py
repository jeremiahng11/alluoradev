"""Optional middleware that exposes the WordPress-authenticated user as
request.app_user for non-DRF views (rare, mostly used inside the dashboard
when we want to display info about the current end user).

Most flows go through DRF and use WordPressCookieAuthentication directly.
"""
from .authentication import _verify_with_wordpress, _sync_user


class WordPressAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.app_user = None  # default

        cookie = request.META.get('HTTP_COOKIE', '')
        nonce = request.META.get('HTTP_X_WP_NONCE', '')

        if cookie and 'wordpress_logged_in' in cookie and nonce:
            wp_user = _verify_with_wordpress(cookie, nonce)
            if wp_user:
                try:
                    request.app_user = _sync_user(wp_user)
                except Exception:
                    request.app_user = None

        return self.get_response(request)
