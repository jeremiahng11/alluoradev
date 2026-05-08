# Alluora Platform

Mobile-first skincare brand platform. Three pieces:

- **Flutter app** (iOS + Android) — `flutter_app/`
- **Django backend + custom admin dashboard** — `backend/`
- **WordPress plugin** for auth + commerce — shipped separately as `alluora-app-bridge.zip`

The Flutter app talks to **WordPress** for auth/products/orders and to **Django** for content/videos/rewards/quiz. Customers log in with their WordPress account and earn rewards through Django.

## Quick start

### Backend (Django)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in BUNNY_*, BOOTSTRAP_ADMIN_*
python manage.py migrate
python manage.py create_admin
python manage.py runserver
```

Visit http://localhost:8000/dashboard/login/

### Flutter app

```bash
cd flutter_app
flutter pub get
flutter run \
  --dart-define=WORDPRESS_BASE=https://staging.alluora.com \
  --dart-define=DJANGO_BASE=http://localhost:8000
```

### Deploying

See `docs/DEPLOYMENT.md` for Railway-specific setup (Postgres, volume mount, Bunny keys, custom domain).

## Documentation

- `docs/ARCHITECTURE.md` — how the three systems fit together, what owns what data, why no JWT
- `docs/DEPLOYMENT.md` — Railway setup, env vars, troubleshooting
- `docs/API.md` — full request/response contract for both WordPress and Django

## What's in the repo

```
alluora-platform/
├── backend/                          Django + DRF + custom dashboard
│   ├── alluora/                      project settings, URL routing
│   ├── apps/
│   │   ├── accounts/                 custom user, WP auth bridge, bootstrap admin
│   │   ├── content/                  articles + categories
│   │   ├── videos/                   Bunny.net Stream integration (TUS presign)
│   │   ├── rewards/                  event-sourced points ledger + badges
│   │   ├── quiz/                     skin quiz with weighted scoring
│   │   └── dashboard/                Tailwind + Alpine admin (NOT django-admin)
│   ├── templates/dashboard/          server-rendered admin UI
│   ├── requirements.txt
│   ├── nixpacks.toml + railway.json + Procfile + start.sh
│   └── .env.example
│
├── flutter_app/                      Flutter mobile app
│   ├── lib/
│   │   ├── main.dart
│   │   ├── router/                   go_router with auth guards
│   │   ├── services/
│   │   │   ├── app_config.dart       WORDPRESS_BASE, DJANGO_BASE from --dart-define
│   │   │   ├── wordpress_api.dart    cookie-auth client for WP plugin
│   │   │   ├── django_api.dart       borrows WP cookies for Django auth
│   │   │   └── auth_service.dart     ChangeNotifier for app-wide auth state
│   │   ├── theme/                    AlluoraColors + AlluoraTypography
│   │   ├── widgets/alluora_logo.dart pure-Flutter brand mark
│   │   └── screens/
│   │       ├── splash/, onboarding/
│   │       ├── auth/                 login, register, forgot password
│   │       ├── home/                 home + main bottom-nav shell
│   │       ├── orders/card_screen    points + badges + activity
│   │       ├── shop/                 webview into WP storefront
│   │       ├── profile/
│   │       └── content/              article detail
│   └── pubspec.yaml
│
└── docs/
    ├── ARCHITECTURE.md
    ├── DEPLOYMENT.md
    └── API.md
```

## Status

This is a **scaffolded v0.1** — the architecture is real and runnable, but several screens are placeholders (the profile menu items navigate but don't all have detail screens; the quiz UI isn't built yet). The Django backend is fully functional and tested; migrations apply cleanly, all routes return correct status codes, the admin dashboard loads.

To take this to v1, you'd want to build:
- Quiz UI (questions list → submit → result screen)
- Order history + order detail screens (the API endpoints exist, just need UI)
- Address edit screens
- Product browse screen (currently only the webview shop tab; add a native browse view)
- Push notification registration
- Real device testing on iOS + Android
