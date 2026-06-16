# Epic A6 — Celery + Redis Async Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Celery 5.4 + Redis as broker/result/pub-sub, create the progress publishing service, and fix the state-machine transitions — so Epic C tasks have infrastructure to run on.

**Architecture:** Celery app is configured in `backend/config/celery.py` using Django settings with the `CELERY_` namespace (DRF best practice). A services module in `apps.projects` handles dual-write progress (JobLog + Redis pub/sub). The orchestration module builds Celery chords for the approve flow.

**Tech Stack:** Django 5.2, Celery 5.4, Redis 5.0.

**Spec refs:** §3 (architecture), §6 (Celery tasks), §8 (progress/SSE).

---

## File Structure

```
backend/config/
  celery.py              — NEW: Celery app initialization
  __init__.py            — MODIFY: export celery_app
  settings.py            — MODIFY: add CELERY_* config + load_env()

backend/apps/projects/
  services.py            — NEW: progress publishing + work_dir helper
  orchestration.py       — NEW: chord builder for approve flow
  constants.py           — MODIFY: fix _TRANSITIONS (add REVIEW→PLANNING)

backend/tests/
  test_services.py       — NEW: publish_event + work_dir tests
```

---

## Task 1: Celery app + Django settings

**Files:**
- Create: `backend/config/celery.py`
- Modify: `backend/config/__init__.py`
- Modify: `backend/config/settings.py`

### `backend/config/celery.py`

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

- Uses `django.conf:settings` with `CELERY_` namespace — all Celery config lives
  in `settings.py`, not scattered across files
- `autodiscover_tasks()` finds `tasks.py` in every `INSTALLED_APPS` app

### `backend/config/__init__.py`

```python
from config.celery import app as celery_app

__all__ = ["celery_app"]
```

### `backend/config/settings.py` additions

```python
# At the top, after existing imports:
from pipeline.env import load_env
load_env()

# After existing settings, add:

# Celery (CELERY_ namespace — standard django-celery convention)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True

# Pipeline output directory
MEDIA_ROOT = os.environ.get(
    "MEDIA_ROOT",
    str(Path(__file__).resolve().parent.parent.parent / "output"),
)
```

**Why `load_env()` in settings:** Django settings is the single entry point for all
config (DRF best practice). Pipeline functions read `os.environ` for API keys —
loading `.env` once here means they're available everywhere.

### Steps

- [ ] Create `backend/config/celery.py` with Celery app
- [ ] Update `backend/config/__init__.py` to export `celery_app`
- [ ] Add `CELERY_*` settings and `load_env()` to `backend/config/settings.py`
- [ ] Add `MEDIA_ROOT` setting
- [ ] Verify: `cd backend && uv run celery -A config worker -l info` boots without errors

---

## Task 2: Services module — progress publishing + helpers

**Files:**
- Create: `backend/apps/projects/services.py`

```python
import json
import logging
from pathlib import Path

import redis
from django.conf import settings

from apps.projects.models import JobLog

logger = logging.getLogger(__name__)


def get_redis_client():
    """Shared Redis connection from Celery broker URL."""
    return redis.Redis.from_url(settings.CELERY_BROKER_URL)


def get_work_dir(project):
    """On-disk work directory: output/<owner_id>/<project_id>/"""
    return Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)


def publish_event(project_id, stage, level, message, scene_index=None):
    """Write JobLog row (persistent) + publish to Redis channel (live SSE).

    Redis publish is best-effort — failure is logged, not raised.
    JobLog is the durable record; Redis is just live streaming.
    """
    JobLog.objects.create(
        project_id=project_id,
        stage=stage,
        level=level,
        message=message,
    )
    event = {"stage": stage, "level": level, "message": message}
    if scene_index is not None:
        event["scene_index"] = scene_index
    try:
        client = get_redis_client()
        client.publish(f"project:{project_id}:events", json.dumps(event))
    except Exception:
        logger.warning("Failed to publish event to Redis", exc_info=True)
```

### Steps

- [ ] Create `backend/apps/projects/services.py`
- [ ] Verify imports resolve: `from apps.projects.services import publish_event, get_work_dir`

---

## Task 3: Fix `_TRANSITIONS` in constants

**Files:**
- Modify: `backend/apps/projects/constants.py`

The refine stage (Epic C2) needs REVIEW→PLANNING. Current:

```python
"REVIEW": {"GENERATING"},
```

Change to:

```python
"REVIEW": {"PLANNING", "GENERATING"},
```

### Steps

- [ ] Update `_TRANSITIONS` in `backend/apps/projects/constants.py`
- [ ] Update any existing tests that validate REVIEW transitions

---

## Task 4: Orchestration — chord builder

**Files:**
- Create: `backend/apps/projects/orchestration.py`

```python
from celery import chord, group

from apps.projects.tasks import (
    run_assemble_stage,
    run_image_stage,
    run_voice_stage,
)


def enqueue_pipeline(project_id, scene_count):
    """Dispatch the assets pipeline: images (parallel) | voice | assemble.

    Called by the approve API endpoint after creating Scene rows.
    """
    image_tasks = group(
        run_image_stage.s(str(project_id), i) for i in range(scene_count)
    )
    pipeline = chord(image_tasks)(
        run_voice_stage.si(str(project_id))
        | run_assemble_stage.si(str(project_id))
    )
    return pipeline
```

Note: This imports from `apps.projects.tasks` which is created in Epic C.
Create as a stub first; wire fully once C3–C5 land.

### Steps

- [ ] Create `backend/apps/projects/orchestration.py`
- [ ] Verify chord dispatches correctly once Epic C tasks exist

---

## Task 5: Tests

**Files:**
- Create: `backend/tests/test_services.py`

### Test cases

- [ ] `test_publish_event_creates_joblog` — JobLog row created with correct stage/level/message
- [ ] `test_publish_event_redis_failure` — Redis down → JobLog still created; no exception raised
- [ ] `test_get_work_dir` — returns correct path: `MEDIA_ROOT/<owner_id>/<project_id>/`

### Steps

- [ ] Create `backend/tests/test_services.py`
- [ ] Verify: `cd backend && uv run python manage.py test`

---

## Key Decisions

1. **`load_env()` in `settings.py`** — single entry point for all config (DRF best practice)
2. **All imports absolute** — `from apps.projects.models import Project`
3. **Celery config in `settings.py`** with `CELERY_` namespace — standard convention
4. **Progress dual-write** — JobLog (persistent, SSE replay) + Redis pub/sub (live SSE)
5. **Redis publish best-effort** — failure logged, not raised; JobLog is the durable record

---

## Dependencies

- **Redis** running locally: `brew install redis && redis-server`
- `celery>=5.4` and `redis>=5.0` already in `pyproject.toml` webapp group
- Install: `uv sync --extra webapp`

---

## Verification

1. **Celery boots:**
   ```bash
   cd backend && uv run celery -A config worker -l info
   ```
   Worker starts with no errors

2. **publish_event works:**
   ```python
   # Django shell
   from apps.projects.services import publish_event
   publish_event(project.id, "plan", "info", "test message")
   ```
   JobLog row created; event visible via `redis-cli SUBSCRIBE "project:<id>:events"`

3. **Settings loaded:**
   ```python
   from django.conf import settings
   print(settings.CELERY_BROKER_URL)   # redis://localhost:6379/0
   print(settings.MEDIA_ROOT)          # /path/to/output
   ```
