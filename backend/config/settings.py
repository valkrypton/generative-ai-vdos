import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Auto-load .env from repo root (same loader the CLI pipeline uses).
# Real env vars always win; empty placeholder values are ignored.
_repo_root = BASE_DIR.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
try:
    from pipeline.env import load_env
    load_env()
except ImportError:
    pass  # pipeline package not installed — rely on real env vars

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-in-prod")

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "corsheaders",
    "apps.health",
    "apps.core",
    "apps.users",
    "apps.projects",
    "apps.auth_oidc",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Sessions — DB-backed, HttpOnly, SameSite=Lax
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG  # True in prod (HTTPS)

# CORS — allow Next.js dev server
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
