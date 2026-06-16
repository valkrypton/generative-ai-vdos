# Epic A3 — Cognito Hosted-UI OAuth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement AWS Cognito OAuth2 endpoints (`/api/auth/login`, `/api/auth/callback`, `/api/auth/logout`) so users can sign in via the Cognito Hosted UI and receive a Django session cookie.

**Architecture:** A new `apps.auth_oidc` Django app holds three plain-function views that drive the OAuth2 authorization-code flow. A `cognito.py` helper module contains all Cognito-specific logic (URL building, token exchange) as pure functions — easy to unit-test by mocking `requests.post`. Sessions are stored in the DB via `django.contrib.sessions`. A3 only covers the session handshake; JWT signature verification lives in A4.

**Tech Stack:** Django 5.2 sessions, `requests` (stdlib-adjacent, already available), `secrets` (stdlib), plain Django views (not DRF — these are redirect flows, not JSON APIs).

---

## File Structure

```
backend/apps/auth_oidc/
  __init__.py         — empty
  apps.py             — AuthOidcConfig
  cognito.py          — get_config(), build_authorize_url(), exchange_code(), build_logout_url()
  views.py            — login(), callback(), logout() — plain Django function views
  urls.py             — 3 URL patterns

backend/config/settings.py   — add sessions app/middleware, session cookie settings
backend/config/urls.py       — include apps.auth_oidc.urls under api/auth/

backend/.env.example         — document COGNITO_* keys (no values)

backend/tests/
  test_cognito_helpers.py    — unit tests for cognito.py functions
  test_auth_views.py         — integration tests for all 3 views via TestClient
```

**Env vars consumed by `get_config()` (all required at runtime, stubbed in tests):**

| Variable | Example value |
|---|---|
| `COGNITO_DOMAIN` | `https://myapp.auth.us-east-1.amazoncognito.com` |
| `COGNITO_APP_CLIENT_ID` | `abc123` |
| `COGNITO_APP_CLIENT_SECRET` | `secret` |
| `COGNITO_REDIRECT_URI` | `http://localhost:8000/api/auth/callback` |
| `COGNITO_LOGOUT_REDIRECT_URI` | `http://localhost:3000` |

---

## Task 1: App scaffold + session support

**Files:**
- Create: `backend/apps/auth_oidc/__init__.py`
- Create: `backend/apps/auth_oidc/apps.py`
- Modify: `backend/config/settings.py`

- [ ] **Step 1: Write a failing smoke test**

Write `backend/tests/test_auth_smoke.py`:

```python
from django.test import TestCase


class SessionSmokeTest(TestCase):
    """Session middleware is present and the auth_oidc app loads."""

    def test_session_is_available(self):
        self.client.get("/api/health/")
        self.assertIn("sessionid", self.client.cookies or {})  # cookie may be absent for JSON endpoints

    def test_auth_oidc_app_registered(self):
        from django.apps import apps
        self.assertIn("auth_oidc", [a.label for a in apps.get_app_configs()])
```

- [ ] **Step 2: Run — expect failure**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests.test_auth_smoke --verbosity=2 2>&1
```

Expected: `LookupError: No installed app with label 'auth_oidc'`

- [ ] **Step 3: Create app files**

Create `backend/apps/auth_oidc/__init__.py` (empty).

Write `backend/apps/auth_oidc/apps.py`:

```python
from django.apps import AppConfig


class AuthOidcConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auth_oidc"
    label = "auth_oidc"
```

- [ ] **Step 4: Update settings**

Replace `backend/config/settings.py` with:

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

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
```

- [ ] **Step 5: Apply session migration**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py migrate 2>&1
```

Expected: `Applying sessions.0001_initial... OK` (plus others already applied)

- [ ] **Step 6: Run smoke test — expect pass**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests.test_auth_smoke --verbosity=2 2>&1
```

Expected:
```
test_auth_oidc_app_registered ... ok
test_session_is_available ... ok
Ran 2 tests in 0.XXXs
OK
```

---

## Task 2: `cognito.py` helper functions

**Files:**
- Create: `backend/apps/auth_oidc/cognito.py`
- Create: `backend/tests/test_cognito_helpers.py`

- [ ] **Step 1: Write the failing unit tests**

Write `backend/tests/test_cognito_helpers.py`:

```python
import os
import urllib.parse
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings


FAKE_CONFIG = {
    "COGNITO_DOMAIN": "https://example.auth.us-east-1.amazoncognito.com",
    "COGNITO_APP_CLIENT_ID": "client-abc",
    "COGNITO_APP_CLIENT_SECRET": "secret-xyz",
    "COGNITO_REDIRECT_URI": "http://localhost:8000/api/auth/callback",
    "COGNITO_LOGOUT_REDIRECT_URI": "http://localhost:3000",
}


class GetConfigTest(TestCase):
    def test_returns_config_when_all_vars_set(self):
        with patch.dict(os.environ, FAKE_CONFIG):
            from apps.auth_oidc.cognito import get_config
            cfg = get_config()
        self.assertEqual(cfg["COGNITO_APP_CLIENT_ID"], "client-abc")

    def test_raises_when_var_missing(self):
        from django.core.exceptions import ImproperlyConfigured
        partial = {k: v for k, v in FAKE_CONFIG.items() if k != "COGNITO_DOMAIN"}
        env_without_domain = {k: "" if k == "COGNITO_DOMAIN" else v
                               for k, v in FAKE_CONFIG.items()}
        with patch.dict(os.environ, env_without_domain, clear=False):
            # Remove COGNITO_DOMAIN entirely
            env_copy = dict(os.environ)
            env_copy.pop("COGNITO_DOMAIN", None)
            with patch.dict(os.environ, env_copy, clear=True):
                from apps.auth_oidc.cognito import get_config
                with self.assertRaises(ImproperlyConfigured):
                    get_config()


class BuildAuthorizeUrlTest(TestCase):
    def test_contains_client_id_and_redirect(self):
        with patch.dict(os.environ, FAKE_CONFIG):
            from apps.auth_oidc.cognito import build_authorize_url
            url = build_authorize_url(FAKE_CONFIG, state="abc123")
        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        self.assertEqual(params["client_id"], "client-abc")
        self.assertEqual(params["state"], "abc123")
        self.assertEqual(params["response_type"], "code")
        self.assertIn("openid", params["scope"])
        self.assertTrue(url.startswith(FAKE_CONFIG["COGNITO_DOMAIN"]))

    def test_redirect_uri_in_params(self):
        from apps.auth_oidc.cognito import build_authorize_url
        url = build_authorize_url(FAKE_CONFIG, state="s")
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(params["redirect_uri"], FAKE_CONFIG["COGNITO_REDIRECT_URI"])


class ExchangeCodeTest(TestCase):
    def _mock_post(self, status_code, json_body):
        mock_resp = MagicMock()
        mock_resp.ok = (status_code < 400)
        mock_resp.json.return_value = json_body
        return mock_resp

    def test_returns_tokens_on_success(self):
        tokens = {
            "id_token": "id.jwt",
            "access_token": "access.jwt",
            "refresh_token": "refresh.jwt",
        }
        with patch("apps.auth_oidc.cognito.requests.post",
                   return_value=self._mock_post(200, tokens)):
            from apps.auth_oidc.cognito import exchange_code
            result = exchange_code(FAKE_CONFIG, "auth-code-123")
        self.assertEqual(result["id_token"], "id.jwt")
        self.assertEqual(result["access_token"], "access.jwt")

    def test_returns_none_on_error_response(self):
        with patch("apps.auth_oidc.cognito.requests.post",
                   return_value=self._mock_post(400, {"error": "invalid_grant"})):
            from apps.auth_oidc.cognito import exchange_code
            result = exchange_code(FAKE_CONFIG, "bad-code")
        self.assertIsNone(result)

    def test_posts_to_token_endpoint(self):
        with patch("apps.auth_oidc.cognito.requests.post",
                   return_value=self._mock_post(200, {})) as mock_post:
            from apps.auth_oidc.cognito import exchange_code
            exchange_code(FAKE_CONFIG, "code123")
        call_args = mock_post.call_args
        self.assertIn("/oauth2/token", call_args[0][0])
        self.assertEqual(call_args[1]["data"]["code"], "code123")


class BuildLogoutUrlTest(TestCase):
    def test_contains_client_id_and_logout_uri(self):
        from apps.auth_oidc.cognito import build_logout_url
        url = build_logout_url(FAKE_CONFIG)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(params["client_id"], "client-abc")
        self.assertEqual(params["logout_uri"], "http://localhost:3000")
        self.assertTrue(url.startswith(FAKE_CONFIG["COGNITO_DOMAIN"]))
```

- [ ] **Step 2: Run — expect failure**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests.test_cognito_helpers --verbosity=2 2>&1
```

Expected: `ModuleNotFoundError: No module named 'apps.auth_oidc.cognito'`

- [ ] **Step 3: Write `cognito.py`**

Write `backend/apps/auth_oidc/cognito.py`:

```python
import os
import urllib.parse
import requests
from django.core.exceptions import ImproperlyConfigured

_REQUIRED_VARS = (
    "COGNITO_DOMAIN",
    "COGNITO_APP_CLIENT_ID",
    "COGNITO_APP_CLIENT_SECRET",
    "COGNITO_REDIRECT_URI",
    "COGNITO_LOGOUT_REDIRECT_URI",
)


def get_config():
    config = {k: os.environ.get(k, "") for k in _REQUIRED_VARS}
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise ImproperlyConfigured(f"Missing COGNITO env vars: {', '.join(missing)}")
    return config


def build_authorize_url(config, state):
    params = {
        "response_type": "code",
        "client_id": config["COGNITO_APP_CLIENT_ID"],
        "redirect_uri": config["COGNITO_REDIRECT_URI"],
        "scope": "openid email profile",
        "state": state,
    }
    return f"{config['COGNITO_DOMAIN']}/oauth2/authorize?{urllib.parse.urlencode(params)}"


def exchange_code(config, code):
    resp = requests.post(
        f"{config['COGNITO_DOMAIN']}/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": config["COGNITO_APP_CLIENT_ID"],
            "client_secret": config["COGNITO_APP_CLIENT_SECRET"],
            "redirect_uri": config["COGNITO_REDIRECT_URI"],
            "code": code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if not resp.ok:
        return None
    return resp.json()


def build_logout_url(config):
    params = {
        "client_id": config["COGNITO_APP_CLIENT_ID"],
        "logout_uri": config["COGNITO_LOGOUT_REDIRECT_URI"],
    }
    return f"{config['COGNITO_DOMAIN']}/logout?{urllib.parse.urlencode(params)}"
```

- [ ] **Step 4: Run helpers tests — expect pass**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests.test_cognito_helpers --verbosity=2 2>&1
```

Expected:
```
test_contains_client_id_and_logout_uri ... ok
test_contains_client_id_and_redirect ... ok
test_posts_to_token_endpoint ... ok
test_raises_when_var_missing ... ok
test_redirect_uri_in_params ... ok
test_returns_none_on_error_response ... ok
test_returns_tokens_on_success ... ok
test_returns_config_when_all_vars_set ... ok
Ran 8 tests in 0.XXXs
OK
```

---

## Task 3: Views, URLs, and integration tests

**Files:**
- Create: `backend/apps/auth_oidc/views.py`
- Create: `backend/apps/auth_oidc/urls.py`
- Modify: `backend/config/urls.py`
- Create: `backend/tests/test_auth_views.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Write the failing integration tests**

Write `backend/tests/test_auth_views.py`:

```python
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase


FAKE_ENV = {
    "COGNITO_DOMAIN": "https://example.auth.us-east-1.amazoncognito.com",
    "COGNITO_APP_CLIENT_ID": "client-abc",
    "COGNITO_APP_CLIENT_SECRET": "secret-xyz",
    "COGNITO_REDIRECT_URI": "http://localhost:8000/api/auth/callback",
    "COGNITO_LOGOUT_REDIRECT_URI": "http://localhost:3000",
}

FAKE_TOKENS = {
    "id_token": "id.jwt.token",
    "access_token": "access.jwt.token",
    "refresh_token": "refresh.token",
}


class LoginViewTest(TestCase):
    def test_redirects_to_cognito(self):
        with patch.dict(os.environ, FAKE_ENV):
            resp = self.client.get("/api/auth/login")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(FAKE_ENV["COGNITO_DOMAIN"], resp["Location"])
        self.assertIn("/oauth2/authorize", resp["Location"])

    def test_state_stored_in_session(self):
        with patch.dict(os.environ, FAKE_ENV):
            self.client.get("/api/auth/login")
        self.assertIn("cognito_state", self.client.session)
        self.assertTrue(len(self.client.session["cognito_state"]) > 10)

    def test_redirect_contains_client_id(self):
        with patch.dict(os.environ, FAKE_ENV):
            resp = self.client.get("/api/auth/login")
        self.assertIn("client_id=client-abc", resp["Location"])


class CallbackViewTest(TestCase):
    def _set_state(self, state="good-state"):
        session = self.client.session
        session["cognito_state"] = state
        session.save()

    def _mock_exchange(self, return_value=FAKE_TOKENS):
        mock_resp = MagicMock()
        mock_resp.ok = (return_value is not None)
        if return_value:
            mock_resp.json.return_value = return_value
        else:
            mock_resp.ok = False
        return patch("apps.auth_oidc.cognito.requests.post", return_value=mock_resp)

    def test_valid_code_sets_session_and_redirects(self):
        self._set_state("my-state")
        with self._mock_exchange():
            resp = self.client.get(
                "/api/auth/callback", {"code": "auth-code", "state": "my-state"}
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session.get("id_token"), "id.jwt.token")
        self.assertEqual(self.client.session.get("access_token"), "access.jwt.token")

    def test_state_mismatch_returns_400(self):
        self._set_state("expected-state")
        resp = self.client.get(
            "/api/auth/callback", {"code": "code", "state": "wrong-state"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_code_returns_400(self):
        self._set_state("my-state")
        resp = self.client.get("/api/auth/callback", {"state": "my-state"})
        self.assertEqual(resp.status_code, 400)

    def test_failed_exchange_returns_401(self):
        self._set_state("my-state")
        with self._mock_exchange(return_value=None):
            resp = self.client.get(
                "/api/auth/callback", {"code": "bad-code", "state": "my-state"}
            )
        self.assertEqual(resp.status_code, 401)

    def test_state_consumed_after_callback(self):
        """State must be removed from session after callback (replay prevention)."""
        self._set_state("my-state")
        with self._mock_exchange():
            self.client.get(
                "/api/auth/callback", {"code": "code", "state": "my-state"}
            )
        self.assertNotIn("cognito_state", self.client.session)


class LogoutViewTest(TestCase):
    def setUp(self):
        session = self.client.session
        session["id_token"] = "some.token"
        session["access_token"] = "some.access"
        session.save()

    def test_logout_clears_session(self):
        with patch.dict(os.environ, FAKE_ENV):
            self.client.post("/api/auth/logout")
        self.assertNotIn("id_token", self.client.session)
        self.assertNotIn("access_token", self.client.session)

    def test_logout_redirects_to_cognito(self):
        with patch.dict(os.environ, FAKE_ENV):
            resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(FAKE_ENV["COGNITO_DOMAIN"], resp["Location"])
        self.assertIn("/logout", resp["Location"])

    def test_logout_contains_client_id(self):
        with patch.dict(os.environ, FAKE_ENV):
            resp = self.client.post("/api/auth/logout")
        self.assertIn("client_id=client-abc", resp["Location"])
```

- [ ] **Step 2: Run — expect failure**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests.test_auth_views --verbosity=2 2>&1
```

Expected: `404` errors — endpoints don't exist yet.

- [ ] **Step 3: Write `views.py`**

Write `backend/apps/auth_oidc/views.py`:

```python
import secrets
from django.http import JsonResponse
from django.shortcuts import redirect
from .cognito import get_config, build_authorize_url, exchange_code, build_logout_url


def login(request):
    config = get_config()
    state = secrets.token_urlsafe(32)
    request.session["cognito_state"] = state
    return redirect(build_authorize_url(config, state))


def callback(request):
    config = get_config()
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    expected_state = request.session.pop("cognito_state", None)

    if not expected_state or state != expected_state:
        return JsonResponse({"error": "Invalid state parameter"}, status=400)

    if not code:
        return JsonResponse({"error": "Missing authorization code"}, status=400)

    tokens = exchange_code(config, code)
    if tokens is None:
        return JsonResponse({"error": "Token exchange failed"}, status=401)

    request.session["id_token"] = tokens.get("id_token", "")
    request.session["access_token"] = tokens.get("access_token", "")
    request.session["refresh_token"] = tokens.get("refresh_token", "")
    return redirect("/")


def logout(request):
    config = get_config()
    request.session.flush()
    return redirect(build_logout_url(config))
```

- [ ] **Step 4: Write `urls.py`**

Write `backend/apps/auth_oidc/urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("login", views.login),
    path("callback", views.callback),
    path("logout", views.logout),
]
```

- [ ] **Step 5: Register URLs in `config/urls.py`**

Replace `backend/config/urls.py` with:

```python
from django.urls import path, include

urlpatterns = [
    path("api/", include("apps.health.urls")),
    path("api/auth/", include("apps.auth_oidc.urls")),
]
```

- [ ] **Step 6: Update `.env.example`**

Append to `backend/.env.example` (or the root `.env.example`):

Actually — the `.env.example` lives at the repo root: `/Users/ali.tariq/PycharmProjects/generative-ai-vdos/.env.example`. Append these lines:

```
# Web app — AWS Cognito OAuth2 (required for the Django web app)
COGNITO_DOMAIN=""                 # e.g. https://yourpool.auth.us-east-1.amazoncognito.com
COGNITO_APP_CLIENT_ID=""
COGNITO_APP_CLIENT_SECRET=""
COGNITO_REDIRECT_URI=""           # e.g. http://localhost:8000/api/auth/callback
COGNITO_LOGOUT_REDIRECT_URI=""    # e.g. http://localhost:3000
```

Also add Django web-app vars to `.env.example`:

```
DJANGO_SECRET_KEY=""              # generate with: python -c "import secrets; print(secrets.token_hex(50))"
DJANGO_DEBUG=""                   # false in production
CORS_ALLOWED_ORIGINS=""           # comma-separated, e.g. http://localhost:3000
```

- [ ] **Step 7: Run auth views tests — expect pass**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests.test_auth_views --verbosity=2 2>&1
```

Expected:
```
test_failed_exchange_returns_401 ... ok
test_logout_clears_session ... ok
test_logout_contains_client_id ... ok
test_logout_redirects_to_cognito ... ok
test_missing_code_returns_400 ... ok
test_redirect_contains_client_id ... ok
test_redirects_to_cognito ... ok
test_state_consumed_after_callback ... ok
test_state_mismatch_returns_400 ... ok
test_state_stored_in_session ... ok
test_valid_code_sets_session_and_redirects ... ok
Ran 11 tests in 0.XXXs
OK
```

- [ ] **Step 8: Run full test suite**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/backend && uv run python manage.py test tests --verbosity=2 2>&1
```

Expected: all tests pass (health + users + projects + scenes + joblogs + state machine + smoke + cognito helpers + auth views = ~44 tests).

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| `GET /auth/login` → redirect to Hosted UI | Task 3 |
| `GET /auth/callback?code=…` exchanges code for tokens | Task 3 |
| `POST /auth/logout` clears session + Cognito logout | Task 3 |
| Config from `COGNITO_*` env only | Tasks 2+3 (get_config) |
| Invalid/expired `code` → 401 | Task 3 (test_failed_exchange_returns_401) |
| State/CSRF param verified | Task 3 (test_state_mismatch_returns_400) |
| Missing `COGNITO_*` → explicit config error | Task 2 (test_raises_when_var_missing) |
| Django stores no passwords | Architecture (no password field, no Django User) |
| Session cookie (not JWT cookie) | Task 1 (session settings), Task 3 (views.py session storage) |

### Placeholder scan

None found.

### Type consistency

- `get_config()` returns a plain dict — used directly as `config` in `build_authorize_url(config, state)`, `exchange_code(config, code)`, `build_logout_url(config)` throughout.
- `exchange_code` returns `dict | None` — `None` check in `callback` view matches.
- Session keys `"id_token"`, `"access_token"`, `"refresh_token"` consistent across views.py and test_auth_views.py.
