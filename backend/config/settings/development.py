import os
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401, F403

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-in-prod")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
SESSION_COOKIE_SECURE = False

CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")

_cognito_missing = [k for k, v in COGNITO.items() if not v]
if _cognito_missing:
    raise ImproperlyConfigured(f"Missing COGNITO env vars: {', '.join(_cognito_missing)}")
