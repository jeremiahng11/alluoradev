"""Thin Bunny Stream API wrapper.

Used by:
  - Server-side video creation (POST to /library/{id}/videos to get a video GUID)
  - Presigned upload signature generation (so the dashboard / app can upload
    directly to Bunny via TUS without proxying through us)
  - Status polling and metadata reads
  - HLS / thumbnail URL signing (Bunny CDN Token Authentication)
"""
import base64
import hashlib
import logging
import time
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = 'https://video.bunnycdn.com'


class BunnyStreamError(Exception):
    """Raised when Bunny returns a non-2xx response."""


def _headers() -> dict:
    return {
        'AccessKey': settings.BUNNY_STREAM_API_KEY,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }


def is_configured() -> bool:
    return bool(settings.BUNNY_STREAM_API_KEY and settings.BUNNY_STREAM_LIBRARY_ID)


def create_video(title: str, collection_id: Optional[str] = None) -> dict:
    """Create a video object in the Bunny library. Returns the JSON response
    which includes the `guid` we'll use for the upload."""
    if not is_configured():
        raise BunnyStreamError('Bunny Stream is not configured.')

    url = f'{API_BASE}/library/{settings.BUNNY_STREAM_LIBRARY_ID}/videos'
    payload = {'title': title}
    if collection_id:
        payload['collectionId'] = collection_id

    resp = requests.post(url, json=payload, headers=_headers(), timeout=10)
    if not resp.ok:
        logger.error('Bunny create_video failed: %s %s', resp.status_code, resp.text)
        raise BunnyStreamError(f'Bunny create_video failed ({resp.status_code}).')
    return resp.json()


# Process-local cache of Bunny collection GUIDs keyed by name. Cleared
# on dyno restart, refilled on first lookup. Keeps every upload from
# fanning out a list+create round trip just to find the collection ID.
_collection_id_cache: dict = {}


def get_or_create_collection(name: str) -> Optional[str]:
    """Look up a Bunny Stream collection by name, creating it if absent.
    Returns the GUID, or None on any Bunny-side error (caller should
    just fall back to the library's root collection).

    Lets us route uploads cleanly: videos → 'Alluora', reels → 'Reels',
    without the admin needing to manage Bunny collection IDs by hand.
    """
    if not is_configured():
        return None
    cached = _collection_id_cache.get(name)
    if cached:
        return cached

    try:
        # 1. List existing collections — try to find one by name.
        list_url = (
            f'{API_BASE}/library/{settings.BUNNY_STREAM_LIBRARY_ID}/collections'
        )
        resp = requests.get(
            list_url,
            headers=_headers(),
            params={'search': name, 'itemsPerPage': 100},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            items = data.get('items') if isinstance(data, dict) else data
            if isinstance(items, list):
                for c in items:
                    if (c.get('name') or '').strip().lower() == name.lower():
                        guid = c.get('guid')
                        if guid:
                            _collection_id_cache[name] = guid
                            return guid

        # 2. Not found — create it.
        create_resp = requests.post(
            list_url,
            json={'name': name},
            headers=_headers(),
            timeout=10,
        )
        if create_resp.ok:
            guid = (create_resp.json() or {}).get('guid')
            if guid:
                _collection_id_cache[name] = guid
                return guid
        logger.warning(
            'Bunny create_collection(%s) failed: %s %s',
            name, create_resp.status_code, create_resp.text,
        )
    except requests.RequestException as exc:
        logger.warning('Bunny collection lookup failed for %s: %s', name, exc)
    return None


def get_video(video_guid: str) -> dict:
    """Fetch video metadata + processing status."""
    if not is_configured():
        raise BunnyStreamError('Bunny Stream is not configured.')

    url = f'{API_BASE}/library/{settings.BUNNY_STREAM_LIBRARY_ID}/videos/{video_guid}'
    resp = requests.get(url, headers=_headers(), timeout=10)
    if not resp.ok:
        raise BunnyStreamError(f'Bunny get_video failed ({resp.status_code}).')
    return resp.json()


def delete_video(video_guid: str) -> bool:
    if not is_configured():
        raise BunnyStreamError('Bunny Stream is not configured.')

    url = f'{API_BASE}/library/{settings.BUNNY_STREAM_LIBRARY_ID}/videos/{video_guid}'
    resp = requests.delete(url, headers=_headers(), timeout=10)
    return resp.ok


def make_presigned_upload(video_guid: str, ttl_seconds: int = 3600) -> dict:
    """Generate the SHA256 signature Bunny's TUS endpoint expects.

    Signature formula (from Bunny docs):
        SHA256(library_id + api_key + expiration_time + video_id)

    Returns a dict with all headers the client needs for a tus upload.
    """
    if not is_configured():
        raise BunnyStreamError('Bunny Stream is not configured.')

    expiration = int(time.time()) + ttl_seconds
    raw = (
        str(settings.BUNNY_STREAM_LIBRARY_ID)
        + settings.BUNNY_STREAM_API_KEY
        + str(expiration)
        + video_guid
    )
    signature = hashlib.sha256(raw.encode()).hexdigest()

    return {
        'tus_endpoint': 'https://video.bunnycdn.com/tusupload',
        'video_id': video_guid,
        'library_id': str(settings.BUNNY_STREAM_LIBRARY_ID),
        'authorization_signature': signature,
        'authorization_expire': expiration,
        'expires_at': expiration,
    }


def _sign_query(path: str, ttl: Optional[int] = None) -> str:
    """Build `?token=...&expires=...` for Bunny CDN Token Authentication.

    Format follows Bunny's "advanced" CDN Token Auth (the standard one
    enabled via Pull Zone → Security → Token Authentication, also used
    by Stream library security):

        token = base64url( sha256_raw( security_key + path + expires ) )

    where `path` is the URL path including the leading '/' (e.g.
    `/{guid}/playlist.m3u8`). For HLS, Bunny Stream auto-tokenises
    segment URLs in the served playlist response so the player picks
    up valid sub-URLs without any client work.

    Returns '' when no signing key is configured (Token Auth off).

    NOTE: The signing key must be the **Token Authentication Key**
    from Bunny library → Security tab — NOT the library API key.
    They look similar (both UUIDs) but are different values.
    """
    key = getattr(settings, 'BUNNY_STREAM_TOKEN_AUTH_KEY', '') or ''
    if not key:
        return ''
    if ttl is None:
        ttl = getattr(settings, 'BUNNY_STREAM_URL_TTL', 6 * 3600)
    expires = int(time.time()) + ttl
    raw = f'{key}{path}{expires}'.encode()
    digest = hashlib.sha256(raw).digest()
    token = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return f'?token={token}&expires={expires}'


def hls_url(video_guid: str) -> str:
    """The HLS playlist URL for streaming, optionally Token-signed."""
    host = settings.BUNNY_STREAM_CDN_HOSTNAME
    if not host:
        # Fall back to default Bunny iframe pattern (admin only — not signed).
        return f'https://iframe.mediadelivery.net/play/{settings.BUNNY_STREAM_LIBRARY_ID}/{video_guid}'
    path = f'/{video_guid}/playlist.m3u8'
    return f'https://{host}{path}{_sign_query(path)}'


def thumbnail_url(video_guid: str) -> str:
    host = settings.BUNNY_STREAM_CDN_HOSTNAME
    if not host:
        return f'https://vz-{settings.BUNNY_STREAM_LIBRARY_ID}.b-cdn.net/{video_guid}/thumbnail.jpg'
    path = f'/{video_guid}/thumbnail.jpg'
    return f'https://{host}{path}{_sign_query(path)}'


def mp4_url(video_guid: str) -> str:
    """Direct MP4 download URL for the encoded video. Used by the
    Flutter app's disk cache so the first reel can be persisted to
    local storage and played back instantly on next launch (no HLS
    handshake, no segment streaming).

    Bunny Stream produces `play_{height}p.mp4` renditions for each
    encoding output. 480p is the lowest mobile-friendly default and
    is almost always present for processed reel-length clips.
    Override with `BUNNY_STREAM_MP4_RESOLUTION` in settings if you
    need a different ladder rung.
    """
    host = settings.BUNNY_STREAM_CDN_HOSTNAME
    res = getattr(settings, 'BUNNY_STREAM_MP4_RESOLUTION', '480p')
    if not host:
        return f'https://vz-{settings.BUNNY_STREAM_LIBRARY_ID}.b-cdn.net/{video_guid}/play_{res}.mp4'
    path = f'/{video_guid}/play_{res}.mp4'
    return f'https://{host}{path}{_sign_query(path)}'
