"""Full-site backup + restore.

A backup is a zip with three pieces:
  - manifest.json  — version, timestamp, counts, app list (for the
    restore UI's pre-flight summary)
  - data.json      — Django dumpdata of every app whose state matters
    (accounts, content, videos, rewards, quiz, skinai). Excludes
    contenttypes, permissions, sessions, admin log entries — those
    regenerate themselves and would clash on restore.
  - media/         — full MEDIA_ROOT tree (ebook PDFs, skin AI photos,
    article covers, etc.).

Restore wipes the listed apps and re-applies data.json, then mirrors
the media tree back into MEDIA_ROOT. Destructive — the dashboard view
that calls restore_from_zip MUST gate it behind a confirmation
phrase + the main-admin check.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import IO

from django.apps import apps as django_apps
from django.conf import settings
from django.core import management
from django.db import transaction


# Apps whose data we back up + restore. Order isn't critical for
# dumpdata, but for restore we feed loaddata one file so Django sorts
# out FK order from the natural-foreign hints.
BACKUP_APPS = (
    'accounts',
    'content',
    'videos',
    'rewards',
    'quiz',
    'skinai',
)

# Excluded models — these regenerate from migrations / installed
# apps / runtime activity and would either conflict or balloon the
# backup. Keep this list in sync with the loaddata expectation.
EXCLUDED_MODELS = (
    'contenttypes',
    'auth.permission',
    'sessions',
    'admin.logentry',
)

BACKUP_FORMAT_VERSION = 1
MANIFEST_NAME = 'manifest.json'
DATA_NAME = 'data.json'
MEDIA_PREFIX = 'media/'


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_backup_to(path: str | Path) -> dict:
    """Write a full backup zip to `path`. Returns the manifest dict so
    the caller can flash a "wrote N MB" success message."""
    path = Path(path)
    counts = _model_counts()
    manifest = {
        'format_version': BACKUP_FORMAT_VERSION,
        'created_at': datetime.now(dt_timezone.utc).isoformat(),
        'apps': list(BACKUP_APPS),
        'excluded_models': list(EXCLUDED_MODELS),
        'model_counts': counts,
        'django_version': _django_version(),
    }

    # dumpdata to a temp file first so we never hold the full JSON in
    # memory (10k+ rows + their FK chains can be tens of MB).
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False, encoding='utf-8',
    ) as fh:
        dump_path = fh.name
    try:
        with open(dump_path, 'w', encoding='utf-8') as out:
            management.call_command(
                'dumpdata',
                *BACKUP_APPS,
                *[f'--exclude={m}' for m in EXCLUDED_MODELS],
                '--natural-foreign',
                '--natural-primary',
                indent=2,
                stdout=out,
            )

        # Quick sanity — empty/garbage dump shouldn't even start the zip.
        if os.path.getsize(dump_path) < 2:
            raise RuntimeError('dumpdata produced an empty file.')

        # Stream the zip directly to disk. ZIP_DEFLATED is universally
        # supported on the restore side and gives ~10x on JSON / 2-3x on
        # images. Skip compression on the media folder since most of it
        # is already-compressed JPEGs / PDFs.
        with zipfile.ZipFile(path, 'w', allowZip64=True) as zf:
            zf.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, indent=2, sort_keys=True),
                compress_type=zipfile.ZIP_DEFLATED,
            )
            zf.write(dump_path, arcname=DATA_NAME,
                     compress_type=zipfile.ZIP_DEFLATED)
            _add_media_dir(zf)
    finally:
        try:
            os.unlink(dump_path)
        except OSError:
            pass

    manifest['size_bytes'] = path.stat().st_size
    return manifest


def _add_media_dir(zf: zipfile.ZipFile) -> None:
    """Walk MEDIA_ROOT and add every file under media/ inside the zip.
    Safe when MEDIA_ROOT doesn't exist yet (fresh deploy) — just skips."""
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return
    for root, _dirs, files in os.walk(media_root):
        for name in files:
            full = Path(root) / name
            try:
                rel = full.relative_to(media_root)
            except ValueError:
                continue
            arcname = MEDIA_PREFIX + str(rel).replace(os.sep, '/')
            # Most media is already-compressed (jpg/pdf/mp4) — store
            # without re-deflate to save build time.
            zf.write(full, arcname=arcname, compress_type=zipfile.ZIP_STORED)


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

class BackupValidationError(Exception):
    """Raised when the uploaded zip isn't a valid Alluora backup."""


def inspect_zip(file_obj: IO[bytes]) -> dict:
    """Open a zip and return its manifest without unpacking anything.
    Useful for the upload preview step. Raises BackupValidationError
    if the zip isn't a valid backup."""
    try:
        with zipfile.ZipFile(file_obj) as zf:
            if MANIFEST_NAME not in zf.namelist():
                raise BackupValidationError(
                    f'Missing {MANIFEST_NAME} — not an Alluora backup.'
                )
            if DATA_NAME not in zf.namelist():
                raise BackupValidationError(
                    f'Missing {DATA_NAME} — not an Alluora backup.'
                )
            try:
                manifest = json.loads(zf.read(MANIFEST_NAME).decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise BackupValidationError(
                    f'manifest.json is corrupt: {exc}'
                ) from exc
            fmt = manifest.get('format_version')
            if fmt != BACKUP_FORMAT_VERSION:
                raise BackupValidationError(
                    f'Unsupported backup format version: {fmt}. '
                    f'This dashboard understands v{BACKUP_FORMAT_VERSION}.'
                )
            return manifest
    except zipfile.BadZipFile as exc:
        raise BackupValidationError(f'Not a valid zip: {exc}') from exc
    finally:
        # Rewind so the caller can re-read the file for restore.
        try:
            file_obj.seek(0)
        except (AttributeError, OSError):
            pass


def restore_from_zip(file_obj: IO[bytes]) -> dict:
    """Wipe + reload everything from the uploaded zip. Returns a
    summary of what was restored. Destructive — the calling view
    MUST gate this with a confirmation phrase + permission check.

    Steps (in order):
      1. Validate zip + read manifest
      2. Extract to a temp dir
      3. Flush the backup apps' tables inside a transaction
      4. loaddata data.json
      5. Replace MEDIA_ROOT with the extracted media/ tree
    """
    manifest = inspect_zip(file_obj)

    with tempfile.TemporaryDirectory(prefix='alluora-restore-') as tmpdir:
        tmpdir_path = Path(tmpdir)
        with zipfile.ZipFile(file_obj) as zf:
            # Reject path-traversal entries (e.g. "../../etc/passwd")
            # — zipfile.extractall does the right thing for absolute
            # paths but ".." inside relative entries can escape on
            # older Python versions. Belt-and-braces here.
            for name in zf.namelist():
                norm = os.path.normpath(name)
                if norm.startswith('..') or os.path.isabs(norm):
                    raise BackupValidationError(
                        f'Refusing entry with unsafe path: {name}'
                    )
            zf.extractall(tmpdir_path)

        data_path = tmpdir_path / DATA_NAME
        if not data_path.exists():
            raise BackupValidationError(
                'Extracted zip is missing data.json.'
            )

        # Apply DB changes atomically so a partway failure doesn't
        # leave the table set half-restored.
        with transaction.atomic():
            _flush_backup_apps()
            management.call_command(
                'loaddata', str(data_path), verbosity=0,
            )

        _replace_media_dir(tmpdir_path / 'media')

    return {
        'manifest': manifest,
        'restored_at': datetime.now(dt_timezone.utc).isoformat(),
    }


def _flush_backup_apps() -> None:
    """Delete every row in every model from the BACKUP_APPS list.
    loaddata then re-inserts from the dump. We can't just `manage.py
    flush` because that wipes ALL tables including the row that's
    currently authenticated to call this endpoint (the request.user
    AppUser); but since we're about to loaddata that same user back
    in, the transaction commit reinstates the session validly.

    Order: dependencies first reversed — Django can't always figure
    out a safe order, so we just disable constraint checks would be
    nicer but isn't portable. Cascading deletes via .delete() instead.
    """
    # Iterate apps in REVERSE of BACKUP_APPS so leaf-most apps drop
    # rows before the ones holding their FK targets.
    for app_label in reversed(BACKUP_APPS):
        try:
            app_config = django_apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            try:
                model.objects.all().delete()
            except Exception:
                # Cascade or constraint issue — leave for loaddata
                # to overwrite if the rows already share a PK.
                pass


def _replace_media_dir(src: Path) -> None:
    """Mirror the extracted media/ tree into MEDIA_ROOT. Old files NOT
    present in the backup are removed so the live tree matches the
    snapshot exactly."""
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        # Backup had no media — wipe the live media folder so the
        # "no media in backup" snapshot is faithfully reproduced.
        for child in media_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
        return

    # Stage to a sibling dir then rename — keeps the operation as close
    # to atomic as the filesystem allows. The rename on the same
    # filesystem is one inode operation.
    stage = media_root.parent / f'{media_root.name}.restore-{int(time.time())}'
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(src, stage)

    # Move the live media aside, swap in the staged copy, then drop
    # the old one. If the swap fails, the old tree is intact.
    backup_aside = media_root.parent / f'{media_root.name}.prev-{int(time.time())}'
    if media_root.exists():
        media_root.rename(backup_aside)
    stage.rename(media_root)
    if backup_aside.exists():
        shutil.rmtree(backup_aside, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_counts() -> dict:
    """{app_label.model_name: row_count} for the apps we back up. Drives
    the restore-preview summary so the admin can sanity-check what's
    inside the zip before clicking Restore."""
    out = {}
    for app_label in BACKUP_APPS:
        try:
            app_config = django_apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            try:
                out[f'{app_label}.{model.__name__.lower()}'] = (
                    model.objects.count()
                )
            except Exception:
                out[f'{app_label}.{model.__name__.lower()}'] = -1
    return out


def _django_version() -> str:
    import django
    return django.get_version()


def humanize_size(num_bytes: int) -> str:
    """Render a byte count as KB / MB / GB."""
    if num_bytes is None:
        return '—'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num_bytes < 1024 or unit == 'GB':
            return f'{num_bytes:.1f} {unit}' if unit != 'B' else f'{num_bytes} {unit}'
        num_bytes /= 1024
    return f'{num_bytes:.1f} GB'