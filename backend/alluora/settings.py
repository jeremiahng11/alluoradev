"""
Django settings for the Alluora platform.

Reads all secrets from environment variables (Railway-managed).
Never check secrets into version control.
"""
import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = config('DJANGO_SECRET_KEY', default='dev-secret-change-me-in-production')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)

# Railway sets RAILWAY_PUBLIC_DOMAIN and RAILWAY_PRIVATE_DOMAIN.
ALLOWED_HOSTS = config(
    'DJANGO_ALLOWED_HOSTS',
    default='localhost,127.0.0.1,.railway.app',
    cast=Csv(),
)
# Auto-add Railway public domain if present.
RAILWAY_PUBLIC_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
if RAILWAY_PUBLIC_DOMAIN and RAILWAY_PUBLIC_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)

CSRF_TRUSTED_ORIGINS = config(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8000,https://*.railway.app',
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'django_htmx',

    # Project apps
    'apps.accounts',
    'apps.content',
    'apps.videos',
    'apps.rewards',
    'apps.quiz',
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'apps.accounts.middleware.WordPressAuthMiddleware',
]

ROOT_URLCONF = 'alluora.urls'
WSGI_APPLICATION = 'alluora.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.dashboard.context_processors.brand',
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database — Railway provides DATABASE_URL automatically when Postgres is added
# ---------------------------------------------------------------------------
DATABASE_URL = config('DATABASE_URL', default='')
if DATABASE_URL:
    # Parse Railway's postgres://... URL.
    import urllib.parse as urlparse
    urlparse.uses_netloc.append('postgres')
    urlparse.uses_netloc.append('postgresql')
    url = urlparse.urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': url.path[1:],
            'USER': url.username,
            'PASSWORD': url.password,
            'HOST': url.hostname,
            'PORT': url.port,
            'CONN_MAX_AGE': 60,
            'OPTIONS': {'sslmode': config('DB_SSLMODE', default='prefer')},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.AppUser'
LOGIN_URL = '/dashboard/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/dashboard/login/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Bootstrap admin user from env vars on first deploy.
# Used by apps.accounts.management.commands.create_admin
# ---------------------------------------------------------------------------
BOOTSTRAP_ADMIN_EMAIL = config('BOOTSTRAP_ADMIN_EMAIL', default='')
BOOTSTRAP_ADMIN_PASSWORD = config('BOOTSTRAP_ADMIN_PASSWORD', default='')
BOOTSTRAP_ADMIN_USERNAME = config('BOOTSTRAP_ADMIN_USERNAME', default='admin')

# ---------------------------------------------------------------------------
# WordPress integration
# ---------------------------------------------------------------------------
WORDPRESS_BASE_URL = config('WORDPRESS_BASE_URL', default='https://staging.alluora.com')
WORDPRESS_API_NAMESPACE = 'alluora/v1'

# HMAC shared secret for service-to-service /sync/* calls into the bridge
# plugin (read points, award points). Must match the "Bridge shared secret"
# field on the WP plugin admin page. Empty string = sync disabled.
ALLUORA_BRIDGE_SECRET = config('ALLUORA_BRIDGE_SECRET', default='')

# Cache TTL for the WP→Django points read mirror. Short enough that admin
# adjustments on WP show up quickly; long enough to avoid hammering WP on
# every API call from the app.
ALLUORA_POINTS_CACHE_TTL = int(config('ALLUORA_POINTS_CACHE_TTL', default=45))

# Points granted on a successful quiz submission (a submission that matched
# a result type). Set to 0 to disable quiz earning.
QUIZ_PASS_POINTS = int(config('QUIZ_PASS_POINTS', default=50))

# ---------------------------------------------------------------------------
# Bunny.net Stream
# ---------------------------------------------------------------------------
BUNNY_STREAM_LIBRARY_ID = config('BUNNY_STREAM_LIBRARY_ID', default='')
BUNNY_STREAM_API_KEY = config('BUNNY_STREAM_API_KEY', default='')
BUNNY_STREAM_CDN_HOSTNAME = config('BUNNY_STREAM_CDN_HOSTNAME', default='')
BUNNY_STREAM_TUS_ENDPOINT = 'https://video.bunnycdn.com/tusupload'

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.accounts.authentication.WordPressCookieAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.OrderingFilter',
        'rest_framework.filters.SearchFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ] + (['rest_framework.renderers.BrowsableAPIRenderer'] if DEBUG else []),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Alluora Platform API',
    'DESCRIPTION': 'Content, videos, rewards, and quizzes for the Alluora app.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:8000,http://localhost:19006',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Static + media
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Railway volume mount path. We persist user uploads and any local media here.
MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-sg'
TIME_ZONE = 'Asia/Singapore'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Security (production)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# Logging — Railway captures stdout
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'WARNING'},
        'apps': {'handlers': ['console'], 'level': 'INFO'},
    },
}
