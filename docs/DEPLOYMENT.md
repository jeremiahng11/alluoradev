# Deployment Guide — Alluora Platform

This guide gets the Django backend + custom dashboard deployed on Railway, talking to staging.alluora.com.

## What you'll need before starting

- A Railway account ([railway.app](https://railway.app))
- Bunny.net account with a Stream library created
- The WordPress site at `staging.alluora.com` already has the `alluora-app-bridge` plugin active (the v2 cookie-auth one)
- A long random password ready for the bootstrap dashboard admin

## Step 1 — Create the Railway project

1. Sign in to Railway → **New Project** → **Empty Project**
2. Name it `alluora-platform`

### Add Postgres

3. **+ New** → **Database** → **Add PostgreSQL**
4. Railway auto-creates the service and a `DATABASE_URL` variable will be available to other services in the project

### Add the Django service

5. **+ New** → **GitHub Repo** → connect your repo
6. Set **Root Directory** to `backend/`
7. Railway will auto-detect the `nixpacks.toml` and use it

### Attach a volume for media

8. On the Django service → **Settings** → **Volumes** → **+ New Volume**
9. Mount path: `/data`
10. Size: 5 GB is plenty to start (cover image uploads, badge icons, etc.)

## Step 2 — Set environment variables

On the Django service → **Variables** → paste these. Replace `<placeholders>`:

```bash
# Django
DJANGO_SECRET_KEY=<generate with: openssl rand -base64 48>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.railway.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.railway.app

# Database — Railway injects this automatically when Postgres is in the project
# DATABASE_URL=  ← leave unset, Railway sets it

# Bootstrap admin (the dashboard owner)
BOOTSTRAP_ADMIN_EMAIL=jeremiah@rudratech.sg
BOOTSTRAP_ADMIN_USERNAME=jeremiah
BOOTSTRAP_ADMIN_PASSWORD=<set a strong 20+ char password>

# WordPress
WORDPRESS_BASE_URL=https://staging.alluora.com

# Bunny.net Stream — get from bunny.net → Stream → your library → API
BUNNY_STREAM_LIBRARY_ID=<numeric library id>
BUNNY_STREAM_API_KEY=<library-scoped API key>
BUNNY_STREAM_CDN_HOSTNAME=  # optional; pull-zone hostname

# CORS — only needed if a browser will hit /api/v1/* (mobile apps don't enforce CORS)
CORS_ALLOWED_ORIGINS=https://staging.alluora.com

# Media on the volume
MEDIA_ROOT=/data/media

# Gunicorn
GUNICORN_WORKERS=3
```

A note on `DJANGO_SECRET_KEY`: rotating it invalidates all dashboard sessions but doesn't affect mobile-app users (their auth lives in WordPress). Rotate freely if it ever leaks.

## Step 3 — Deploy

Push to your connected branch (or use Railway's manual **Deploy** button). The build runs `pip install -r requirements.txt` then `start.sh`, which:

1. `collectstatic --noinput` — gathers static files for whitenoise to serve
2. `migrate --noinput` — applies migrations
3. `create_admin` — creates or refreshes the dashboard admin from `BOOTSTRAP_ADMIN_*`
4. `gunicorn` boots on `$PORT`

Watch the deploy logs. You should see `Created dashboard admin: jeremiah@rudratech.sg` (first deploy) or `Updated dashboard admin: ...` (subsequent deploys).

## Step 4 — Generate a public domain

On the Django service → **Settings** → **Networking** → **Generate Domain**. You'll get something like `alluora-platform-production-abc1.up.railway.app`. Add it to `DJANGO_ALLOWED_HOSTS` if it's not already covered by `.railway.app`.

Visit `https://<your-domain>/dashboard/login/` and sign in with `BOOTSTRAP_ADMIN_EMAIL` + `BOOTSTRAP_ADMIN_PASSWORD`. You should land on the overview.

## Step 5 — Sanity check the API

```bash
BASE=https://<your-domain>

# Public articles list — should return empty list
curl -s $BASE/api/v1/content/articles/ | jq

# Auth required — should return 401
curl -s $BASE/api/v1/accounts/me/ | jq

# Swagger docs — should render
curl -s -o /dev/null -w "%{http_code}\n" $BASE/api/docs/
```

## Step 6 — Wire WordPress and Django together

The Django backend's `WordPressCookieAuthentication` calls `https://staging.alluora.com/wp-json/alluora/v1/auth/me` to identify users. For this to work:

1. Confirm the `alluora-app-bridge` plugin v2 is active on staging.alluora.com (you already did this)
2. Make sure WordPress's permalinks aren't on "Plain" (you confirmed this)
3. From the Django service, test the call works:
   ```bash
   curl -s https://staging.alluora.com/wp-json/alluora/v1
   ```
   You should see the route list.

That's it for backend. The mobile app will pass the cookie + nonce on its calls and Django will accept them.

## Step 7 — Custom domain (optional, recommended for prod)

In Railway → service → **Settings** → **Networking** → **Custom Domain**:
- Add `staging-api.alluora.com` (matches the default in `flutter_app/lib/services/app_config.dart`)
- Railway gives you a CNAME to add at your DNS provider
- Once propagated, add it to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`

## Step 8 — Building the Flutter app

From the `flutter_app/` directory:

```bash
flutter pub get

# Run against staging
flutter run \
  --dart-define=WORDPRESS_BASE=https://staging.alluora.com \
  --dart-define=DJANGO_BASE=https://staging-api.alluora.com

# Build a debug Android APK to test on a device
flutter build apk --debug \
  --dart-define=WORDPRESS_BASE=https://staging.alluora.com \
  --dart-define=DJANGO_BASE=https://staging-api.alluora.com

# iOS (requires Mac + Xcode)
flutter build ios --debug \
  --dart-define=WORDPRESS_BASE=https://staging.alluora.com \
  --dart-define=DJANGO_BASE=https://staging-api.alluora.com
```

For production, swap the staging URLs for production and create a separate Railway environment.

## Common issues

**"Bunny Stream is not configured" on the dashboard.** You forgot to set `BUNNY_STREAM_LIBRARY_ID` or `BUNNY_STREAM_API_KEY`. Add them and redeploy.

**Dashboard login says "Invalid credentials".** The bootstrap admin command silently skipped because `BOOTSTRAP_ADMIN_EMAIL` or `BOOTSTRAP_ADMIN_PASSWORD` was missing. Set them in Variables and redeploy — the command will create the user.

**API returns 502/504 from Railway.** Gunicorn timeout — for slow Bunny calls, bump `--timeout` in `start.sh` from 60 to 120.

**Migrations fail with "relation already exists".** Likely you tried two services pointing at the same Postgres. Drop the schema or use `python manage.py migrate --fake-initial` once.

**Volume isn't accessible.** Make sure the mount path in Settings → Volumes is `/data` (matches `MEDIA_ROOT=/data/media`).

**App says "Could not connect" on login.** Check the Flutter `--dart-define` values match your actual deployed URLs. Print `AppConfig.wordpressBase` and `AppConfig.djangoBase` early in `main()` to verify.

## Promoting from staging to production

When you're ready:

1. Duplicate the Railway project (or add a new environment)
2. Use a separate Postgres
3. Set `WORDPRESS_BASE_URL=https://alluora.com` (or wherever prod WP lives)
4. Set a different `DJANGO_SECRET_KEY` and `BOOTSTRAP_ADMIN_PASSWORD`
5. Use a different Bunny library so staging videos don't bleed into prod
6. Tighten `CORS_ALLOWED_ORIGINS` to only the prod app domain (drop `localhost` and any wildcards)
