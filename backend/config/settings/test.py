from .base import *  # noqa: F401, F403

DEBUG = True
SESSION_COOKIE_SECURE = False
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]

# Dummy values so startup passes without real Cognito credentials.
# Individual tests override with self.settings(COGNITO=FAKE_COGNITO).
COGNITO = {
    "COGNITO_DOMAIN": "https://test.auth.example.com",
    "COGNITO_APP_CLIENT_ID": "test-client-id",
    "COGNITO_APP_CLIENT_SECRET": "test-client-secret",
    "COGNITO_REDIRECT_URI": "http://localhost:8000/api/auth/callback",
    "COGNITO_LOGOUT_REDIRECT_URI": "http://localhost:3000",
}
