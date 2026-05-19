#!/usr/bin/env bash
# Railway entrypoint. Runs on every deploy.
set -euo pipefail

echo "==> Ensuring media dir exists (Railway volume mounts here)"
# /data is the Railway volume mount; /data/media is MEDIA_ROOT in prod.
# mkdir -p is a no-op if the volume already provides the directory.
mkdir -p /data/media || true

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Running migrations"
python manage.py migrate --noinput

echo "==> Bootstrapping admin user from env vars (idempotent)"
python manage.py create_admin || true

echo "==> Starting gunicorn on port 80"
exec gunicorn alluora.wsgi:application \
  --bind "0.0.0.0:80" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
