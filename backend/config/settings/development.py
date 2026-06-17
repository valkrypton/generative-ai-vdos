import os
from .base import *  # noqa: F401, F403

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-in-prod")
ALLOWED_HOSTS = env_csv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
SESSION_COOKIE_SECURE = False

CORS_ALLOWED_ORIGINS = env_csv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

require_cognito()
