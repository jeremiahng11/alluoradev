"""Progressive Web App support for the dashboard.

Three pieces:
  - manifest_view  → /dashboard/manifest.webmanifest
  - icon_view      → /dashboard/pwa/icon-<size>.png  (dynamic, cached)
  - service_worker → /dashboard/sw.js (root scope = /dashboard/)

Browser install criteria satisfied: HTTPS (Railway/Render TLS), a
manifest with name + short_name + start_url + display: standalone +
192px AND 512px icons, plus a registered service worker that handles
the fetch event.

Icons are generated on demand from static/img/alluora_logo.png —
resized + padded to a square with the brand cream background, then
cached in-process for the life of the worker (so subsequent requests
within the same gunicorn worker don't re-render). Also sent with a
1-year Cache-Control so the browser caches across visits.
"""
from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse, JsonResponse, Http404
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET


# Supported PWA icon sizes. 192 + 512 are the minimum spec; the rest
# give Chrome / Safari / Edge sharper rendering at small tab-icon
# scales and on hi-DPI laptops.
ICON_SIZES = (48, 72, 96, 144, 192, 256, 384, 512)
BACKGROUND_COLOR = '#FAF3E8'    # matches dashboard cream
THEME_COLOR = '#DD5430'         # brand primary


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

@require_GET
@cache_control(public=True, max_age=3600)
def manifest_view(request):
    """Serve the web app manifest. Cached for an hour so a manifest
    change rolls out within that window without forcing a fresh
    download on every page navigation."""
    icons = [
        {
            'src': reverse('dashboard:pwa-icon', kwargs={'size': size}),
            'sizes': f'{size}x{size}',
            'type': 'image/png',
            'purpose': 'any',
        }
        for size in ICON_SIZES
    ]
    # Add a maskable variant so Android / Chrome OS use the safe zone
    # rendering when installed as an app. The maskable icon uses the
    # same source but tells the OS it's safe to crop into circles /
    # rounded squares.
    icons.append({
        'src': reverse('dashboard:pwa-icon', kwargs={'size': 512}),
        'sizes': '512x512',
        'type': 'image/png',
        'purpose': 'maskable',
    })

    manifest = {
        'name': 'Alluora Admin',
        'short_name': 'Alluora',
        'description': 'Manage the Alluora platform: content, '
                       'membership, Skin AI, rewards.',
        'start_url': '/dashboard/',
        'scope': '/dashboard/',
        'display': 'standalone',
        'display_override': ['standalone', 'minimal-ui'],
        'orientation': 'any',
        'background_color': BACKGROUND_COLOR,
        'theme_color': THEME_COLOR,
        'lang': 'en',
        'dir': 'ltr',
        'categories': ['productivity', 'business'],
        'icons': icons,
        'shortcuts': [
            {
                'name': 'Stats',
                'short_name': 'Stats',
                'url': '/dashboard/stats/',
                'description': 'Views, downloads, completion across '
                               'videos, reels, articles, ebooks.',
            },
            {
                'name': 'Library',
                'short_name': 'Library',
                'url': '/dashboard/ebooks/',
                'description': 'Manage downloadable ebooks.',
            },
            {
                'name': 'Skin AI scans',
                'short_name': 'Skin AI',
                'url': '/dashboard/skin-ai/users/',
                'description': 'Browse user scan results.',
            },
        ],
    }
    return JsonResponse(
        manifest,
        json_dumps_params={'indent': 2, 'sort_keys': False},
        content_type='application/manifest+json',
    )


# ---------------------------------------------------------------------------
# Icon (dynamic, cached)
# ---------------------------------------------------------------------------

@require_GET
@cache_control(public=True, max_age=31_536_000, immutable=True)
def icon_view(request, size: int):
    """Generate (or return cached) a square PWA icon at the requested
    size. Source: static/img/alluora_logo.png. Output: PNG with the
    cream background showing through the logo's transparent areas, so
    the install icon doesn't look like a logo floating on a checker
    pattern."""
    if size not in ICON_SIZES:
        raise Http404('Unsupported icon size.')
    png_bytes = _render_icon(size)
    return HttpResponse(png_bytes, content_type='image/png')


@lru_cache(maxsize=len(ICON_SIZES))
def _render_icon(size: int) -> bytes:
    """Resize + pad the logo into a square at `size`px. Cached in-
    process via lru_cache for the worker's lifetime so repeated hits
    skip the Pillow work."""
    from PIL import Image  # imported lazily — Pillow is heavy

    src_path = finders.find('img/alluora_logo.png')
    if not src_path:
        # Last-resort: fall back to a solid brand-colored square so
        # the manifest still works on environments where the logo
        # asset somehow isn't collected.
        canvas = Image.new('RGBA', (size, size), THEME_COLOR)
    else:
        with Image.open(src_path) as logo:
            logo = logo.convert('RGBA')
            # Fit the logo into ~80% of the canvas, centered, on the
            # cream background. 80% gives the OS some safe-zone
            # padding for rounded / circular masks.
            inner = int(size * 0.8)
            scale = min(inner / logo.width, inner / logo.height)
            new_w = max(1, int(logo.width * scale))
            new_h = max(1, int(logo.height * scale))
            logo = logo.resize((new_w, new_h), Image.LANCZOS)
            canvas = Image.new('RGBA', (size, size), BACKGROUND_COLOR)
            offset_x = (size - new_w) // 2
            offset_y = (size - new_h) // 2
            canvas.paste(logo, (offset_x, offset_y), logo)
    buf = io.BytesIO()
    canvas.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Service Worker
# ---------------------------------------------------------------------------

# Bumped whenever the SW logic changes — clients with a different
# cache name will tear down old caches on next activate.
SW_CACHE_VERSION = 'alluora-dashboard-v1'

# Inline SW source as a Python string. Kept here rather than as a
# static file so it can interpolate the cache version + scope without
# a build step. Served with the Service-Worker-Allowed header so the
# scope can be /dashboard/ even though the SW URL itself sits inside
# /dashboard/ (which is the default scope already — header is belt-
# and-braces in case we move the SW URL later).
_SW_JS = """\
// Alluora Admin service worker. Generated server-side; do not edit
// the deployed file directly.
//
// Strategy:
//   - HTML / navigation requests → network-first, fall back to the
//     cached shell so the offline screen has the dashboard chrome
//     even when the server is unreachable.
//   - Static (icons, fonts, CSS, JS) → cache-first; lets the desktop
//     PWA cold-start instantly.
//   - API calls (/api/v1/*) → pass through to the network. We don't
//     want stale data shown to admins.
const CACHE = '%(cache_version)s';
const APP_SHELL = '/dashboard/';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.add(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  // Bypass non-GET (form posts, file uploads, etc).
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // Pass through everything outside the dashboard scope and all API
  // calls — these are dynamic / authenticated / sensitive and we
  // don't want them cached at the SW layer.
  if (!url.pathname.startsWith('/dashboard/')) return;
  if (url.pathname.startsWith('/dashboard/sw.js')) return;
  if (url.pathname.startsWith('/dashboard/manifest')) return;
  if (req.headers.get('accept') &&
      req.headers.get('accept').includes('text/event-stream')) return;

  if (req.mode === 'navigate' ||
      (req.headers.get('accept') || '').includes('text/html')) {
    // Network-first for HTML; fall back to cached shell offline.
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(APP_SHELL, copy));
        return res;
      }).catch(() => caches.match(APP_SHELL))
    );
    return;
  }

  // Cache-first for static assets within the dashboard scope.
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      // Only cache successful, same-origin responses to avoid
      // storing 500s or opaque cross-origin junk.
      if (res && res.ok && res.type === 'basic') {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }))
  );
});
"""


@require_GET
def service_worker_view(request):
    """Serve the dashboard service worker. Service-Worker-Allowed
    header explicit even though it's not strictly required at this
    URL (default scope is /dashboard/ anyway)."""
    body = _SW_JS % {'cache_version': SW_CACHE_VERSION}
    resp = HttpResponse(body, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/dashboard/'
    # Short TTL so SW updates roll out quickly. Browsers also check
    # for SW updates on every navigation anyway, but this avoids
    # CDNs/proxies caching the JS for hours.
    resp['Cache-Control'] = 'public, max-age=60'
    return resp
