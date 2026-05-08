#!/usr/bin/env bash
# Railway entrypoint. Runs on every deploy.
set -euo pipefail

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Running migrations"
python manage.py migrate --noinput

echo "==> Bootstrapping admin user from env vars (idempotent)"
python manage.py create_admin || true

echo "==> Starting gunicorn on port ${PORT:-8000}"
exec gunicorn alluora.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
