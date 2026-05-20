#!/usr/bin/env bash
# Deploy entrypoint. Runs on every container start. Platform-agnostic —
# works on Railway, Render (Blueprint in render.yaml), Fly.io, or any
# generic container host that injects $PORT and mounts a persistent
# disk at /data.
set -euo pipefail

echo "==> Ensuring media dir exists (persistent disk mounts here)"
# /data is the persistent disk mount (Railway volume / Render disk /
# Fly volume). /data/media is MEDIA_ROOT in prod.  mkdir -p is a no-op
# if the disk already provides the directory.
mkdir -p /data/media || true

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Running migrations"
python manage.py migrate --noinput

echo "==> Bootstrapping admin user from env vars (idempotent)"
python manage.py create_admin || true

echo "==> Starting gunicorn on port ${PORT:-80}"
exec gunicorn alluora.wsgi:application \
  --bind "0.0.0.0:${PORT:-80}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
