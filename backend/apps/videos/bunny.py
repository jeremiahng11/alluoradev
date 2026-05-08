"""Thin Bunny Stream API wrapper.

Used by:
  - Server-side video creation (POST to /library/{id}/videos to get a video GUID)
  - Presigned upload signature generation (so the dashboard / app can upload
    directly to Bunny via TUS without proxying through us)
  - Status polling and metadata reads
"""
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


def hls_url(video_guid: str) -> str:
    """The HLS playlist URL for streaming."""
    host = settings.BUNNY_STREAM_CDN_HOSTNAME
    if not host:
        # Fall back to default Bunny iframe pattern.
        return f'https://iframe.mediadelivery.net/play/{settings.BUNNY_STREAM_LIBRARY_ID}/{video_guid}'
    return f'https://{host}/{video_guid}/playlist.m3u8'


def thumbnail_url(video_guid: str) -> str:
    host = settings.BUNNY_STREAM_CDN_HOSTNAME
    if not host:
        return f'https://vz-{settings.BUNNY_STREAM_LIBRARY_ID}.b-cdn.net/{video_guid}/thumbnail.jpg'
    return f'https://{host}/{video_guid}/thumbnail.jpg'
