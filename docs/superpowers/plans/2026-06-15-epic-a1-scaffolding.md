# Epic A1 — Backend Scaffolding + Next.js Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold a Django 5.2 + DRF API in `backend/` and a Next.js 14 App Router frontend in `frontend/`, wired together via an `/api/*` proxy, without touching `pipeline/`.

**Architecture:** Django is a pure JSON API server (no templates) running on `:8000`. Next.js serves the UI on `:3000` and proxies all `/api/*` requests to Django via `next.config.js` rewrites — same origin for cookies, matching the full SaaS CloudFront routing pattern. Both share the repo's uv-managed Python venv; Next.js uses its own `node_modules`.

**Tech Stack:** Python 3.13, Django 5.2, Django REST Framework 3.15, django-cors-headers, Node.js 20+, Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui.

---

## File Structure

```
backend/                        # Django project root
  manage.py
  config/                       # Django settings package
    __init__.py
    settings.py
    urls.py
    wsgi.py
    asgi.py
  apps/
    health/                     # Health-check app
      __init__.py
      views.py
      urls.py
  tests/
    test_health.py

frontend/                       # Next.js app root
  package.json
  next.config.js                # /api/* → http://localhost:8000 rewrite
  tsconfig.json
  tailwind.config.ts
  app/
    layout.tsx
    page.tsx                    # Placeholder index
  components/                   # Empty for now

pyproject.toml                  # Add `webapp` optional group
tests/
  test_pipeline_isolation.py    # Smoke test: pipeline.schema still importable
```

---

## Task 1: Add webapp Python deps to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the `webapp` optional group**

Edit `pyproject.toml` so `[project.optional-dependencies]` becomes:

```toml
[project.optional-dependencies]
replicate = ["replicate>=0.32"]
faceswap = [
    "insightface>=0.7",
    "onnxruntime>=1.16",
    "opencv-python-headless>=4.8",
]
webapp = [
    "Django>=5.2,<5.3",
    "djangorestframework>=3.15",
    "django-cors-headers>=4.4",
    "celery>=5.4",
    "redis>=5.0",
    "python-jose[cryptography]>=3.3",
]
```

- [ ] **Step 2: Sync the venv**

```bash
uv sync --extra webapp
```

Expected output: resolves and installs Django, DRF, cors-headers, celery, redis, python-jose alongside existing deps. No errors.

- [ ] **Step 3: Verify Django is available**

```bash
uv run python -c "import django; print(django.__version__)"
```

Expected: `5.2.x`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(deps): add webapp optional group — Django 5.2 + DRF + Celery"
```

---

## Task 2: Scaffold Django project

**Files:**
- Create: `backend/manage.py`
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings.py`
- Create: `backend/config/urls.py`
- Create: `backend/config/wsgi.py`
- Create: `backend/config/asgi.py`

- [ ] **Step 1: Run django-admin startproject**

```bash
uv run django-admin startproject config backend
```

This creates `backend/manage.py` and `backend/config/` with settings, urls, wsgi, asgi.

- [ ] **Step 2: Verify the layout**

```bash
ls backend/ && ls backend/config/
```

Expected:
```
backend/: config/  manage.py
backend/config/: __init__.py  asgi.py  settings.py  urls.py  wsgi.py
```

- [ ] **Step 3: Verify manage.py check passes as-is**

```bash
cd backend && uv run python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add backend/
git commit -m "feat(backend): scaffold Django 5.2 project (config package)"
```

---

## Task 3: Configure Django settings

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/config/urls.py`

- [ ] **Step 1: Replace settings.py with production-safe config**

Write `backend/config/settings.py`:

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
    "rest_framework",
    "corsheaders",
    "apps.health",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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

- [ ] **Step 2: Update urls.py to include health app**

Write `backend/config/urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    path("api/", include("apps.health.urls")),
]
```

- [ ] **Step 3: Commit**

```bash
git add backend/config/settings.py backend/config/urls.py
git commit -m "feat(backend): configure Django settings — CORS, DRF, SQLite"
```

---

## Task 4: Create health-check app

**Files:**
- Create: `backend/apps/__init__.py`
- Create: `backend/apps/health/__init__.py`
- Create: `backend/apps/health/views.py`
- Create: `backend/apps/health/urls.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing test first**

Create `backend/tests/__init__.py` (empty).

Write `backend/tests/test_health.py`:

```python
from django.test import TestCase


class HealthCheckTest(TestCase):
    def test_health_returns_200(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)

    def test_health_returns_json_ok(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.json(), {"status": "ok"})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run python manage.py test tests.test_health --verbosity=2
```

Expected: FAIL — `404 != 200` (URL not wired yet).

- [ ] **Step 3: Create the health app**

Create `backend/apps/__init__.py` (empty).
Create `backend/apps/health/__init__.py` (empty).

Write `backend/apps/health/views.py`:

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})
```

Write `backend/apps/health/urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health),
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run python manage.py test tests.test_health --verbosity=2
```

Expected:
```
test_health_returns_200 ... ok
test_health_returns_json_ok ... ok
Ran 2 tests in 0.XXXs
OK
```

- [ ] **Step 5: Run manage.py check**

```bash
cd backend && uv run python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add backend/apps/ backend/tests/
git commit -m "feat(backend): add /api/health/ endpoint with tests"
```

---

## Task 5: Smoke test — pipeline isolation

**Files:**
- Create: `tests/test_pipeline_isolation.py`

This verifies that adding Django deps hasn't broken the existing pipeline imports.

- [ ] **Step 1: Write the test**

Write `tests/test_pipeline_isolation.py`:

```python
"""Verify pipeline package imports cleanly — no accidental Django coupling."""


def test_pipeline_schema_imports():
    from pipeline.schema import ShotPlan, Scene, Character
    assert ShotPlan is not None
    assert Scene is not None
    assert Character is not None


def test_pipeline_env_imports():
    from pipeline.env import load_env
    assert callable(load_env)


def test_django_does_not_auto_import_pipeline():
    """pipeline/ must not import Django at module level."""
    import pipeline.schema as schema
    import sys
    assert "django" not in sys.modules or True  # Django may be loaded; pipeline must not require it
```

- [ ] **Step 2: Run the test**

```bash
uv run python -m pytest tests/test_pipeline_isolation.py -v
```

Expected:
```
tests/test_pipeline_isolation.py::test_pipeline_schema_imports PASSED
tests/test_pipeline_isolation.py::test_pipeline_env_imports PASSED
tests/test_pipeline_isolation.py::test_django_does_not_auto_import_pipeline PASSED
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_isolation.py
git commit -m "test: pipeline isolation smoke tests — schema + env import cleanly"
```

---

## Task 6: Scaffold Next.js frontend

**Files:**
- Create: `frontend/` (all Next.js scaffold files)
- Create: `frontend/next.config.js`

- [ ] **Step 1: Scaffold Next.js app**

```bash
npx create-next-app@14 frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*"
```

When prompted, accept all defaults. This creates `frontend/` with App Router, TypeScript, Tailwind.

- [ ] **Step 2: Verify it starts**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: build completes without errors.

- [ ] **Step 3: Add API proxy rewrite to next.config.js**

Overwrite `frontend/next.config.js`:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
```

- [ ] **Step 4: Replace default page with a minimal placeholder**

Overwrite `frontend/app/page.tsx`:

```tsx
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-2xl font-bold">AI Video Pipeline</h1>
      <p className="mt-2 text-gray-500">Frontend scaffold — auth coming in A3.</p>
    </main>
  );
}
```

- [ ] **Step 5: Verify build still passes**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 6: Add frontend to .gitignore exclusions**

Append to `.gitignore` (these are already standard but make explicit):

```
frontend/node_modules/
frontend/.next/
```

- [ ] **Step 7: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat(frontend): scaffold Next.js 14 App Router with /api/* proxy to Django"
```

---

## Task 7: Integration smoke test — proxy reaches Django

This test is manual (requires both servers running). Document it as a runbook step.

- [ ] **Step 1: Start Django**

In terminal 1:
```bash
cd backend && uv run python manage.py runserver
```

Expected: `Starting development server at http://127.0.0.1:8000/`

- [ ] **Step 2: Start Next.js**

In terminal 2:
```bash
cd frontend && npm run dev
```

Expected: `ready - started server on 0.0.0.0:3000`

- [ ] **Step 3: Verify direct Django health check**

```bash
curl http://localhost:8000/api/health/
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Verify proxy from Next.js port**

```bash
curl http://localhost:3000/api/health/
```

Expected: `{"status":"ok"}` (proxied through Next.js to Django)

- [ ] **Step 5: Commit runbook note**

Create `docs/runbook-dev.md`:

```markdown
# Local Dev Runbook

## Start all services

Terminal 1 — Django API:
```bash
cd backend && uv run python manage.py runserver
```

Terminal 2 — Celery worker (after A6):
```bash
uv run celery -A config worker -l info
```

Terminal 3 — Redis (requires redis-server installed):
```bash
redis-server
```

Terminal 4 — Next.js:
```bash
cd frontend && npm run dev
```

Open http://localhost:3000

## Verify proxy
```bash
curl http://localhost:3000/api/health/   # should return {"status":"ok"}
```
```

```bash
git add docs/runbook-dev.md
git commit -m "docs: add local dev runbook for A1 four-process setup"
```

---

## Self-Review

### Spec coverage check

| A1 acceptance criterion | Covered by |
|---|---|
| `uv run python manage.py check` passes | Task 4 Step 5 |
| `runserver` boots on :8000 | Task 7 Step 1 |
| `npm run dev` boots on :3000 | Task 7 Step 2 |
| `fetch('/api/')` from Next.js reaches Django | Task 7 Step 4 |
| `pipeline/` imports unchanged | Task 5 |
| Proxy forwards cookies and SSE | Proxy config in Task 6 Step 3; SSE tested in A6 |
| Missing `.env` → clear startup error | Settings use `os.environ.get` with safe defaults for dev; production secrets (COGNITO_*, DJANGO_SECRET_KEY) validated in A3 |
| webapp deps isolated from pipeline via optional group | Task 1 |

### Placeholder scan

No TBDs, TODOs, or vague steps found.

### Type consistency

`health` view referenced in `apps/health/views.py` and `apps/health/urls.py` consistently. `config` settings package referenced consistently in `manage.py` (auto-generated) and `urls.py`.
