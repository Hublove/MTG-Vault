"""
Django settings for the single-user MTG manager.

Configuration is intentionally minimal: SQLite, no auth, dark-mode Tailwind
front end served from templates. Secrets/config come from the environment
(see .env.example).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# The data dir is volume-mounted in Docker so the SQLite DB + Scryfall bulk
# downloads survive container rebuilds.
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DEBUG", "True").lower() in ("1", "true", "yes")

# Single-user/local tool: allow everything (it's not internet-facing by default).
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
# Add your phone-access origin(s) here when serving over a tunnel/LAN so POSTs
# pass CSRF, e.g. EXTRA_TRUSTED_ORIGINS=https://abc.trycloudflare.com,http://192.168.1.50:8000
CSRF_TRUSTED_ORIGINS += [
    o.strip() for o in os.environ.get("EXTRA_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cards",
    "decks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mtg.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mtg.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Toronto"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# --- App-specific config ---------------------------------------------------

# Scryfall provides no CAD price; we convert from USD with this rate.
FX_RATE_USD_CAD = float(os.environ.get("FX_RATE_USD_CAD", "1.38"))

# Scryfall asks for a descriptive User-Agent and an explicit Accept header.
SCRYFALL_USER_AGENT = os.environ.get(
    "SCRYFALL_USER_AGENT", "MTGManager/1.0 (set-a-contact@example.com)"
)

# Where the downloaded Scryfall bulk JSON is cached.
SCRYFALL_BULK_PATH = DATA_DIR / "oracle_cards.json"
