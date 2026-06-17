# Epic A6 — Celery + Redis Async Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Celery 5.4 + Redis as broker/result/pub-sub, create the progress publishing service, and fix the state-machine transitions — so Epic C tasks have infrastructure to run on.

**Architecture:** Celery app is configured in `backend/config/celery.py` using Django settings with the `CELERY_` namespace (DRF best practice). Settings are split by environment (`settings/base.py`, `development.py`, `production.py`, `test.py`). Dev and test use `CELERY_TASK_ALWAYS_EAGER` (no Redis required locally); production uses a real Redis broker. A utils module in `apps.projects` handles progress logging via `JobLog`. The orchestration module builds Celery chords for the approve flow, with an eager-mode fallback for local development.

**Tech Stack:** Django 5.2, Celery 5.4, Redis 5.0 (production only).

**Spec refs:** §3 (architecture), §6 (Celery tasks), §8 (progress/SSE).

---

## File Structure

```
backend/config/
  celery.py                    — NEW: Celery app initialization
  __init__.py                  — MODIFY: export celery_app
  settings/
    base.py                    — load_env() + shared config (MEDIA_ROOT)
    development.py             — CELERY_TASK_ALWAYS_EAGER (no Redis needed)
    production.py              — CELERY_BROKER_URL + CELERY_RESULT_BACKEND from env
    test.py                    — CELERY_TASK_ALWAYS_EAGER (no Redis needed)

backend/apps/projects/
  utils.py                     — log_event + get_work_dir helpers
  orchestration.py             — NEW: chord builder with eager-mode fallback
  constants.py                 — MODIFY: fix _TRANSITIONS (add REVIEW→PLANNING)
  tasks.py                     — NEW (Epic C): shared_task definitions

backend/apps/projects/tests/
  test_orchestration.py        — NEW: enqueue_pipeline tests (eager mode)
```

---

## Task 1: Celery app + Django settings

**Files:**
- Create: `backend/config/celery.py`
- Modify: `backend/config/__init__.py`
- Modify: `backend/config/settings/development.py`
- Modify: `backend/config/settings/production.py`
- Modify: `backend/config/settings/test.py`

### `backend/config/celery.py`

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

- Default `DJANGO_SETTINGS_MODULE` is `config.settings.production` — matches
  `wsgi.py` and `asgi.py`
- Uses `django.conf:settings` with `CELERY_` namespace — all Celery config lives
  in the split settings files, not scattered across files
- `autodiscover_tasks()` finds `tasks.py` in every `INSTALLED_APPS` app

### `backend/config/__init__.py`

```python
from config.celery import app as celery_app

__all__ = ["celery_app"]
```

### Settings: development.py additions

```python
# Celery: run tasks synchronously in-process (no Redis required locally)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

### Settings: production.py additions

```python
# Celery: real broker (Redis) in production
CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]
CELERY_RESULT_BACKEND = os.environ["CELERY_RESULT_BACKEND"]
```

### Settings: test.py additions

```python
# Celery: run tasks synchronously in-process (no Redis required)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

**Why split settings:** `load_env()` is already called in `base.py` via
`pipeline.env.load_env()` (wrapped in try/except for environments without the
pipeline package). Dev/test use eager mode so developers don't need Redis running.
Production requires explicit broker URLs — `os.environ[]` (not `.get()`) fails fast
if they're missing.

### Steps

- [x] Create `backend/config/celery.py` with Celery app (default: `config.settings.production`)
- [x] Update `backend/config/__init__.py` to export `celery_app`
- [x] Add `CELERY_TASK_ALWAYS_EAGER` to `development.py` and `test.py`
- [x] Add `CELERY_BROKER_URL` + `CELERY_RESULT_BACKEND` to `production.py`
- [x] `MEDIA_ROOT` already in `base.py`
- [ ] Verify: `cd backend && uv run celery -A config worker -l info` boots without errors (production only)

---

## Task 2: Utils module — progress logging + helpers

**Files:**
- Already exists: `backend/apps/projects/utils.py`

```python
from pathlib import Path

from django.conf import settings

from apps.projects.models import JobLog


def get_work_dir(project):
    return Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)


def log_event(project_id, stage, level, message):
    JobLog.objects.create(
        project_id=project_id, stage=stage, level=level, message=message,
    )
```

`log_event` creates a persistent `JobLog` row. Redis pub/sub for live SSE
streaming can be added later when the SSE endpoint is built — `log_event` is
the durable foundation that pub/sub will wrap.

### Steps

- [x] `get_work_dir` and `log_event` exist in `backend/apps/projects/utils.py`
- [x] Verify imports resolve: `from apps.projects.utils import log_event, get_work_dir`

---

## Task 3: Fix `_TRANSITIONS` in constants

**Files:**
- Modify: `backend/apps/projects/constants.py`

The refine stage (Epic C2) needs REVIEW→PLANNING:

```python
"REVIEW": {"PLANNING", "GENERATING"},
```

### Steps

- [x] `_TRANSITIONS` already includes `REVIEW → PLANNING`
- [x] Existing tests in `test_state_machine.py` validate REVIEW transitions

---

## Task 4: Orchestration — chord builder with eager-mode fallback

**Files:**
- Create: `backend/apps/projects/orchestration.py`

```python
from django.conf import settings
from celery import chord, group

from apps.projects.tasks import (
    mark_pipeline_failed,
    run_assemble_stage,
    run_image_stage,
    run_voice_stage,
)


def enqueue_pipeline(project_id, scene_count):
    """Dispatch the assets pipeline: images (parallel) | voice | assemble.

    Called by the approve API endpoint after creating Scene rows.
    """
    pid = str(project_id)
    image_tasks = group(run_image_stage.s(pid, i) for i in range(scene_count))
    post_images = run_voice_stage.si(pid) | run_assemble_stage.si(pid)

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        try:
            image_tasks.apply()
            post_images.apply()
        except Exception:
            mark_pipeline_failed("eager-mode", project_id=pid)
        return None

    pipeline = chord(image_tasks)(
        post_images,
        link_error=mark_pipeline_failed.s(project_id=pid),
    )
    return pipeline
```

**Why eager-mode fallback:** `chord` + `link_error` callbacks don't fire in
eager mode (`CELERY_TASK_ALWAYS_EAGER`). The fallback runs tasks sequentially
with a try/except that calls `mark_pipeline_failed` on error, so projects
correctly transition to `FAILED` in dev/test.

### Steps

- [x] Create `backend/apps/projects/orchestration.py` with eager-mode fallback
- [x] Verify chord dispatches correctly with real broker (production)
- [x] Verify eager-mode fallback handles failures (dev/test)

---

## Task 5: Tests

**Files:**
- Create: `backend/apps/projects/tests/test_orchestration.py`

Tests are co-located with the app (in `apps/projects/tests/`), following the
project convention.

### Test cases

- [x] `test_happy_path_marks_done` — pipeline runs all stages, project → DONE, scenes → DONE
- [x] `test_failure_marks_project_failed` — task raises, `mark_pipeline_failed` fires, project → FAILED
- [x] `test_returns_none_in_eager_mode` — eager mode returns None (no Celery result object)
- [x] `test_single_scene` — edge case with 1 scene

### Steps

- [x] Create `backend/apps/projects/tests/test_orchestration.py`
- [x] Verify: `cd backend && uv run python manage.py test apps`

---

## Key Decisions

1. **Split settings** — `base.py` for shared config, `development.py`/`test.py` for eager mode, `production.py` for real Redis broker
2. **`CELERY_TASK_ALWAYS_EAGER` for local dev** — no Redis required; tasks run synchronously in-process
3. **Eager-mode fallback in orchestration** — `chord`/`link_error` don't work in eager mode, so `enqueue_pipeline` uses try/except with direct `mark_pipeline_failed` call
4. **`load_env()` in `base.py`** — already present, wrapped in try/except ImportError
5. **All imports absolute** — `from apps.projects.models import Project`
6. **Celery config in split settings** with `CELERY_` namespace — standard convention
7. **`log_event` in utils** — durable JobLog writes; Redis pub/sub deferred to SSE endpoint work

---

## Dependencies

- **Redis** required in **production only**: `brew install redis && redis-server` (for local production testing)
- `celery>=5.4` and `redis>=5.0` in `pyproject.toml` webapp group
- Install: `uv sync --extra webapp`
- **Local dev needs no Redis** — eager mode runs tasks in-process

---

## Verification

1. **Tests pass (dev/test — no Redis needed):**
   ```bash
   cd backend && uv run python manage.py test apps
   ```
   All 70 tests pass including orchestration tests

2. **Celery boots (production — requires Redis):**
   ```bash
   DJANGO_SETTINGS_MODULE=config.settings.production celery -A config worker -l info
   ```
   Worker starts with no errors

3. **Settings loaded:**
   ```python
   # development.py
   from django.conf import settings
   print(settings.CELERY_TASK_ALWAYS_EAGER)   # True
   print(settings.MEDIA_ROOT)                 # /path/to/output

   # production.py
   print(settings.CELERY_BROKER_URL)          # redis://...
   print(settings.CELERY_RESULT_BACKEND)      # redis://...
   ```
