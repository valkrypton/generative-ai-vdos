# Django Storages — Persist Pipeline Media to S3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `django-storages` so that each pipeline stage task — starting with `run_image_stage` — uploads its generated artifact to durable file storage after writing it to disk. `FileSystemStorage` is used in dev/test (no AWS credentials needed); `S3Boto3Storage` is used in production. Users access private media via time-limited signed URLs returned by dedicated API endpoints.

**Architecture:** Add `django-storages[s3]` + `boto3` to deps. Configure `STORAGES` per environment (base → FileSystemStorage with `allow_overwrite=True`, production → S3Boto3Storage private + 3600s signed-URL expiry, test → InMemoryStorage). Convert `Scene.media_path` from `CharField` to `FileField`; add `Scene.audio_path` (FileField), `Scene.audio_words` (JSONField), and `Project.final_video` (FileField). Create a standalone `apps/storage/` Django app containing an abstract `BaseStorageProvider` (ABC in `base_storage.py`), `LocalStorageProvider`, `S3StorageProvider`, and a `storage_provider` lazy global (a `SimpleLazyObject`) exposed from `__init__.py`. Any Django app imports `storage_provider` directly and calls `.upload()` / `.url()` on it — no wrapper functions, no factory calls at the call site. The provider is chosen at runtime by `_get_provider()` in `__init__.py` which inspects `default_storage` — no environment branching in application code. Update `run_image_stage` to call `storage_provider.upload()` after the image backend writes the file to disk; add stub upload comments to `run_voice_stage` and `run_assemble_stage` for when those TODOs are filled. Add signed-URL `@action` endpoints to both viewsets. The pipeline itself is **not** modified.

**Tech Stack:** Django 5.2, `django-storages 1.14+`, `boto3 1.34+`, AWS S3, `InMemoryStorage` for tests, Celery tasks run eagerly in test (`CELERY_TASK_ALWAYS_EAGER=True`).

## Key Design Decisions

| Question | Decision | Reason |
|---|---|---|
| Which field type for out-of-band files? | `FileField` | Stores storage key in DB; delegates I/O to storage backend. |
| Which `<user_id>` in storage key? | `UserProfile.id` (internal integer PK) | `get_work_dir()` already uses `owner_id`; stay consistent. Stable, private, shorter than cognito_sub. |
| Storage key layout? | `{owner_id}/{project_id}/{type}/{filename}` | Matches `get_work_dir()` path structure exactly — in dev, FileSystemStorage writes to the same path the pipeline already uses. |
| Signed-URL expiry? | 3600 seconds | Set via `querystring_expire` in STORAGES OPTIONS; `S3StorageProvider` forwards it per-call to `storage.url(name, expire=...)`. |
| When does upload happen? | Inside the Celery task, after the stage writes the file to disk | Keeps persistence close to generation; no separate ingest step. |
| `FileSystemStorage` allow_overwrite? | `True` in base settings | In dev, pipeline writes to `MEDIA_ROOT/{owner_id}/{project_id}/…`; upload via FileField writes to same path. Without overwrite=True Django appends a suffix. |
| Storage abstraction? | `apps/storage/` — standalone Django app with `BaseStorageProvider` ABC in `base_storage.py` | Clean separation from `apps/projects/`. `LocalStorageProvider` for dev/test; `S3StorageProvider` for prod. |
| How is the provider exposed? | `storage_provider = SimpleLazyObject(_get_provider)` in `__init__.py` | Global — any app does `from apps.storage import storage_provider`. Safe to import at module level before Django boots. Mirrors how Django exposes `default_storage`. No wrapper functions needed. |
| Wrapper functions? | None — callers use `storage_provider.upload()` / `.url()` directly | Fewer indirection layers. The `SimpleLazyObject` global makes wrappers redundant. |

## Migration Dependency Note

`0003_rename_image_path_scene_media_path_scene_animate_and_more` already exists (unapplied) — it renames `image_path → media_path` and adds new Scene fields. Our storage migration will be `0004_storage_fields` and depends on `0003`.

## Global Constraints

- Django `>=5.2,<5.3`
- `STORAGES` dict (Django 4.2+) only — never `DEFAULT_FILE_STORAGE`
- `InMemoryStorage` in ALL tests — no real files written during `manage.py test`
- AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) from environment only — never in settings files
- S3 objects always private (`default_acl = "private"`) — signed URLs are the only external access path
- Only storage keys (relative paths) stored in DB — never file bytes
- Run all tests: `cd backend && python manage.py test apps --settings=config.settings.test`

---

## File Structure

```
pyproject.toml
  → add django-storages[s3]>=1.14, boto3>=1.34 to [webapp]

backend/config/
  settings/
    base.py         → add "storages" + "apps.storage" to INSTALLED_APPS; MEDIA_URL; MEDIA_ROOT; STORAGES (FileSystemStorage, allow_overwrite=True)
    production.py   → AWS env vars; STORAGES override (S3Boto3Storage, private, 3600s expiry)
    test.py         → STORAGES override (InMemoryStorage)
  urls.py           → add static(MEDIA_URL, ...) for DEBUG=True

backend/apps/storage/           ← new standalone Django app
  __init__.py       → _get_provider() factory + storage_provider = SimpleLazyObject(_get_provider)
  apps.py           → StorageConfig(AppConfig)
  base_storage.py   → BaseStorageProvider (ABC with upload + url abstract methods)
  local_storage.py  → LocalStorageProvider (FileSystemStorage / InMemoryStorage)
  s3_storage.py     → S3StorageProvider (pre-signed URLs via storage.url(name, expire=...))

backend/apps/projects/
  models.py         → upload_to helpers; media_path CharField→FileField; add audio_path, audio_words, Project.final_video
  migrations/
    0004_storage_fields.py   → AlterField(media_path) + AddField ×3
  tasks.py          → from apps.storage import storage_provider; run_image_stage calls storage_provider.upload(); stub comments in voice + assemble
  serializers.py    → add audio_path, audio_words, final_video (read-only)
  views.py          → from apps.storage import storage_provider; media_urls calls storage_provider.url()
  urls.py           → register scene media-urls route

  tests/
    test_models_scenes.py    → fix media_path="" assertion for FileField
    test_models_projects.py  → add final_video default assertion
    test_storage_utils.py    → BaseStorageProvider hierarchy + storage_provider.upload() / .url() tests
    test_storage_paths.py    → upload_to path layout tests
    test_signed_urls.py      → S3StorageProvider signed URL behaviour + _get_provider() detection tests

.env.example  → add AWS_STORAGE_BUCKET_NAME, AWS_S3_REGION_NAME
```

---

## Task 1: Dependencies + Settings + Dev Media Serving

**Files:** `pyproject.toml`, `backend/config/settings/base.py`, `backend/config/settings/production.py`, `backend/config/settings/test.py`, `backend/config/urls.py`, `.env.example`

**Interfaces produced:** `STORAGES["default"]` wired per environment; `MEDIA_URL=/media/`, `MEDIA_ROOT=backend/media/`; dev server serves `/media/` from `MEDIA_ROOT`.

- [ ] **Step 1: Add deps to `pyproject.toml`**

```toml
webapp = [
    "Django>=5.2,<5.3",
    "djangorestframework>=3.17.1",
    "django-cors-headers>=4.4",
    "celery>=5.4",
    "redis>=5.0",
    "python-jose[cryptography]>=3.3",
    "requests>=2.28",
    "django-storages[s3]>=1.14",
    "boto3>=1.34",
]
```

- [ ] **Step 2: Sync deps**

```bash
uv sync --extra webapp
```

- [ ] **Step 3: Update `backend/config/settings/base.py`**

Add `"storages"` and `"apps.storage"` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "corsheaders",
    "storages",
    "apps.health",
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.storage",
]
```

Append at the end of `base.py`:

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"allow_overwrite": True},
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

`allow_overwrite=True` — in dev the pipeline writes the image to the same path FileField would target. Without it Django appends a suffix and the DB ends up with the wrong key.

- [ ] **Step 4: Update `backend/config/settings/production.py`**

```python
AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "default_acl": "private",
            "file_overwrite": False,
            "querystring_auth": True,
            "querystring_expire": 3600,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

boto3 reads `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from env automatically — never put them in settings.

- [ ] **Step 5: Update `backend/config/settings/test.py`**

```python
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

- [ ] **Step 6: Update `backend/config/urls.py`**

```python
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path("api/", include("apps.health.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.projects.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

- [ ] **Step 7: Update `.env.example`**

```bash
# File storage — S3 (required in production; omit in dev/test)
AWS_STORAGE_BUCKET_NAME=""
AWS_S3_REGION_NAME=""
# AWS_ACCESS_KEY_ID=""
# AWS_SECRET_ACCESS_KEY=""
```

- [ ] **Step 8: Verify Django system check**

```bash
cd backend && python manage.py check --settings=config.settings.development
```

Expected: `System check identified no issues (0 silenced).`

---

## Task 2: Model Fields + Migration

**Files:** `backend/apps/projects/models.py`, `backend/apps/projects/migrations/0004_storage_fields.py`

**Interfaces produced:**
- `scene_media_upload_path(instance, filename) -> str` — `"{owner_id}/{project_id}/images/{filename}"`
- `scene_audio_upload_path(instance, filename) -> str` — `"{owner_id}/{project_id}/audio/{filename}"`
- `project_video_upload_path(instance, filename) -> str` — `"{owner_id}/{project_id}/{filename}"`
- `Scene.media_path` — `FileField` (was `CharField`)
- `Scene.audio_path` — new `FileField`
- `Scene.audio_words` — new `JSONField`
- `Project.final_video` — new `FileField`

**Note on `select_related`:** upload_to callables access `instance.project.owner_id`. Always fetch scenes with `select_related("project")` before calling `storage_provider.upload()`.

- [ ] **Step 1: Add upload_to helpers and update fields in `models.py`**

```python
def scene_media_upload_path(instance, filename):
    return f"{instance.project.owner_id}/{instance.project_id}/images/{filename}"

def scene_audio_upload_path(instance, filename):
    return f"{instance.project.owner_id}/{instance.project_id}/audio/{filename}"

def project_video_upload_path(instance, filename):
    return f"{instance.owner_id}/{instance.id}/{filename}"
```

In `Project`, add after `stale`:
```python
final_video = models.FileField(upload_to=project_video_upload_path, blank=True, default="")
```

In `Scene`, replace `media_path` and add `audio_path` + `audio_words`:
```python
media_path  = models.FileField(upload_to=scene_media_upload_path, blank=True, default="")
audio_path  = models.FileField(upload_to=scene_audio_upload_path, blank=True, default="")
audio_words = models.JSONField(null=True, blank=True)
```

- [ ] **Step 2: Generate migration**

```bash
cd backend
python manage.py makemigrations projects --name storage_fields --settings=config.settings.test
```

Verify the generated file has:
- `dependencies = [("projects", "0003_rename_image_path_scene_media_path_scene_animate_and_more")]`
- `AlterField` for `scene.media_path` + `AddField` ×3

- [ ] **Step 3: Apply migrations**

```bash
python manage.py migrate --settings=config.settings.test
```

---

## Task 3: `apps/storage/` — Abstract Storage Provider App

**Files:** `backend/apps/storage/__init__.py`, `backend/apps/storage/apps.py`, `backend/apps/storage/base_storage.py`, `backend/apps/storage/local_storage.py`, `backend/apps/storage/s3_storage.py`, `backend/apps/projects/tasks.py`

**Interfaces produced:**
- `BaseStorageProvider` — ABC in `base_storage.py` with abstract `upload(field_file, local_path, *, save)` and `url(field_file) -> str | None`
- `LocalStorageProvider(BaseStorageProvider)` — delegates to `FileSystemStorage` / `InMemoryStorage`
- `S3StorageProvider(BaseStorageProvider)` — generates pre-signed URLs via `field_file.storage.url(name, expire=self._expire)`
- `_get_provider() -> BaseStorageProvider` — in `__init__.py`; inspects `default_storage` at runtime; returns `S3StorageProvider` or `LocalStorageProvider`
- `storage_provider` — `SimpleLazyObject(_get_provider)` in `__init__.py`; global usable from any app as `from apps.storage import storage_provider`
- `run_image_stage` calls `storage_provider.upload(scene.media_path, disk_path)` after image write

- [ ] **Step 1: Create `backend/apps/storage/apps.py`**

```python
from django.apps import AppConfig

class StorageConfig(AppConfig):
    name = "apps.storage"
```

- [ ] **Step 2: Create `backend/apps/storage/base_storage.py`**

```python
from abc import ABC, abstractmethod
from pathlib import Path

from django.db.models.fields.files import FieldFile


class BaseStorageProvider(ABC):
    """
    Abstract interface for file-storage operations on Django FileFields.

    Concrete subclasses encapsulate backend-specific behaviour (signed URL
    expiry, overwrite rules, etc.) while the application code stays the same
    regardless of the configured storage backend.
    """

    @abstractmethod
    def upload(self, field_file: FieldFile, local_path: Path, *, save: bool = True) -> None:
        """
        Open local_path and write its contents to field_file via the storage
        backend. When save=True (default) the model row is updated immediately.
        Pass save=False to batch multiple field writes before a single .save().
        """

    @abstractmethod
    def url(self, field_file: FieldFile) -> str | None:
        """
        Return an access URL for field_file, or None if the field is empty.
        Implementations must handle empty fields gracefully.
        """
```

- [ ] **Step 3: Create `backend/apps/storage/local_storage.py`**

```python
from pathlib import Path

from django.core.files import File
from django.db.models.fields.files import FieldFile

from apps.storage.base_storage import BaseStorageProvider


class LocalStorageProvider(BaseStorageProvider):
    """
    Wraps Django's FileSystemStorage (and InMemoryStorage in tests).
    URL generation returns a plain /media/… path served by Django in dev.
    """

    def upload(self, field_file: FieldFile, local_path: Path, *, save: bool = True) -> None:
        with local_path.open("rb") as fh:
            field_file.save(local_path.name, File(fh), save=save)

    def url(self, field_file: FieldFile) -> str | None:
        return field_file.url if field_file else None
```

- [ ] **Step 4: Create `backend/apps/storage/s3_storage.py`**

```python
from pathlib import Path

from django.core.files import File
from django.db.models.fields.files import FieldFile

from apps.storage.base_storage import BaseStorageProvider


class S3StorageProvider(BaseStorageProvider):
    """
    Wraps django-storages S3Boto3Storage.
    Generates pre-signed URLs with a configurable expiry window so that
    private S3 objects can be accessed temporarily by authenticated users.
    """

    def __init__(self, expire: int = 3600):
        self._expire = expire

    def upload(self, field_file: FieldFile, local_path: Path, *, save: bool = True) -> None:
        with local_path.open("rb") as fh:
            field_file.save(local_path.name, File(fh), save=save)

    def url(self, field_file: FieldFile) -> str | None:
        if not field_file:
            return None
        # Bypass FieldFile.url to pass per-call expiry to S3Boto3Storage.url().
        return field_file.storage.url(field_file.name, expire=self._expire)
```

- [ ] **Step 5: Create `backend/apps/storage/__init__.py`**

```python
from django.utils.functional import SimpleLazyObject

from apps.storage.local_storage import LocalStorageProvider
from apps.storage.s3_storage import S3StorageProvider


def _get_provider():
    """
    Factory that returns the provider matching the current default storage
    backend. Detects S3Boto3Storage at runtime; falls back to LocalStorageProvider
    for FileSystemStorage and InMemoryStorage (dev + test).
    """
    from django.core.files.storage import default_storage
    try:
        from storages.backends.s3boto3 import S3Boto3Storage
        if isinstance(default_storage, S3Boto3Storage):
            expire = getattr(default_storage, "querystring_expire", 3600)
            return S3StorageProvider(expire=expire)
    except ImportError:
        pass
    return LocalStorageProvider()


# Global storage provider — lazily instantiated on first access so it is safe
# to import at module level before Django's app registry is fully loaded.
# Mirrors how Django exposes django.core.files.storage.default_storage.
#
# Usage from any Django app:
#   from apps.storage import storage_provider
#   storage_provider.upload(scene.media_path, disk_path)
#   storage_provider.url(scene.media_path)
storage_provider = SimpleLazyObject(_get_provider)
```

- [ ] **Step 6: Update `run_image_stage` in `tasks.py`**

Import `storage_provider` at the top of the file alongside other imports:

```python
from apps.storage import storage_provider
```

Inside the task, add `select_related("project")` and the conditional upload:

```python
def run_image_stage(self, project_id, scene_index):
    project = Project.objects.get(id=project_id)
    scene = Scene.objects.select_related("project").get(
        project_id=project_id, index=scene_index
    )
    ...
    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)

        # TODO: replace with actual image backend call that returns disk_path
        disk_path = None

        if disk_path is not None and disk_path.exists():
            storage_provider.upload(scene.media_path, disk_path)
        ...
```

- [ ] **Step 7: Add stub comments to `run_voice_stage` and `run_assemble_stage`**

In `run_voice_stage`:
```python
        # TODO: call actual TTS backend, then for each scene:
        #   scene = Scene.objects.select_related("project").get(project_id=project_id, index=i)
        #   storage_provider.upload(scene.audio_path, work_dir / "audio" / f"scene_{i:02d}.mp3", save=False)
        #   scene.audio_words = json.loads((work_dir / "audio" / f"scene_{i:02d}.words.json").read_text())
        #   scene.save(update_fields=["audio_path", "audio_words", "updated_at"])
```

In `run_assemble_stage`:
```python
        # TODO: call actual FFmpeg assembly that writes work_dir / "final.mp4", then:
        #   storage_provider.upload(project.final_video, work_dir / "final.mp4")
```

---

## Task 4: Serializers

**Files:** `backend/apps/projects/serializers.py`

- [ ] **Step 1: Update `SceneSerializer`**

```python
class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = [
            "id", "index",
            "media_path", "image_status", "image_provider",
            "audio_path", "audio_words",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "index",
            "media_path", "image_status", "image_provider",
            "audio_path", "audio_words",
            "created_at", "updated_at",
        ]
```

- [ ] **Step 2: Update `ProjectSerializer`**

```python
class ProjectSerializer(serializers.ModelSerializer):
    scenes = SceneSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "title", "prompt", "status", "shot_plan",
            "image_backend", "animate", "narrator_voice", "music",
            "error", "stale", "final_video", "scenes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "error", "stale", "final_video", "created_at", "updated_at",
        ]
```

---

## Task 5: Signed URL Endpoints

**Files:** `backend/apps/projects/views.py`, `backend/apps/projects/urls.py`

**Interfaces produced:**
- `GET /api/projects/{pk}/final-video-url/` → `{"url": str|null}`
- `GET /api/projects/{project_pk}/scenes/{pk}/media-urls/` → `{"media_url": str|null}`
- Both scoped to the authenticated user's own projects

- [ ] **Step 1: Update `views.py`**

Import `storage_provider` at the top and call `.url()` directly:

```python
from apps.storage import storage_provider

class ProjectViewSet(viewsets.ModelViewSet):
    ...
    @action(detail=True, methods=["get"], url_path="final-video-url")
    def final_video_url(self, request, pk=None):
        project = self.get_object()
        return Response({"url": storage_provider.url(project.final_video)})


class SceneViewSet(viewsets.ReadOnlyModelViewSet):
    ...
    @action(detail=True, methods=["get"], url_path="media-urls")
    def media_urls(self, request, project_pk=None, pk=None):
        scene = self.get_object()
        return Response({"media_url": storage_provider.url(scene.media_path)})
```

- [ ] **Step 2: Register `media-urls` route in `urls.py`**

```python
path(
    "projects/<uuid:project_pk>/scenes/<int:pk>/media-urls/",
    SceneViewSet.as_view({"get": "media_urls"}),
    name="project-scenes-media-urls",
),
```

---

## Task 6: Tests

- [ ] **Step 1: Fix `test_models_scenes.py`**

```python
# Before:
self.assertEqual(s.media_path, "")

# After:
self.assertFalse(s.media_path)   # empty FileField is falsy
self.assertFalse(s.audio_path)
self.assertIsNone(s.audio_words)
```

- [ ] **Step 2: Fix `test_models_projects.py`**

```python
self.assertFalse(p.final_video)
```

- [ ] **Step 3: Write `test_storage_utils.py`**

```python
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage import _get_provider, storage_provider
from apps.storage.base_storage import BaseStorageProvider
from apps.storage.local_storage import LocalStorageProvider
from apps.storage.s3_storage import S3StorageProvider


def _owner(sub="sub-utils"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@test.com")

def _project(owner=None):
    return Project.objects.create(owner=owner or _owner(), prompt="utils test")

def _tmp_file(content: bytes = b"\x89PNG\r\n", suffix: str = ".png") -> Path:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(content)
    f.flush()
    return Path(f.name)


class StorageProviderAbstractionTest(TestCase):
    def test_base_is_abstract(self):
        self.assertTrue(hasattr(BaseStorageProvider, "__abstractmethods__"))

    def test_local_is_concrete_subclass(self):
        self.assertTrue(issubclass(LocalStorageProvider, BaseStorageProvider))
        self.assertIsInstance(LocalStorageProvider(), BaseStorageProvider)

    def test_s3_is_concrete_subclass(self):
        self.assertTrue(issubclass(S3StorageProvider, BaseStorageProvider))
        self.assertIsInstance(S3StorageProvider(expire=1800), BaseStorageProvider)

    def test_get_provider_returns_local_in_tests(self):
        self.assertIsInstance(_get_provider(), LocalStorageProvider)


class StorageProviderUploadTest(TestCase):
    def setUp(self):
        self.owner = _owner()
        self.project = _project(owner=self.owner)
        self.scene = Scene.objects.create(project=self.project, index=0)

    def test_upload_sets_field_truthy(self):
        storage_provider.upload(self.scene.media_path, _tmp_file())
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.media_path)

    def test_upload_key_contains_owner_and_project_ids(self):
        storage_provider.upload(self.scene.media_path, _tmp_file())
        self.scene.refresh_from_db()
        self.assertIn(str(self.owner.id), self.scene.media_path.name)
        self.assertIn(str(self.project.id), self.scene.media_path.name)

    def test_upload_with_save_false_does_not_persist(self):
        storage_provider.upload(self.scene.media_path, _tmp_file(), save=False)
        self.assertFalse(Scene.objects.get(pk=self.scene.pk).media_path)


class StorageProviderUrlTest(TestCase):
    def setUp(self):
        self.owner = _owner("sub-url-utils")
        self.project = _project(owner=self.owner)
        self.scene = Scene.objects.create(project=self.project, index=0)

    def test_returns_none_for_empty_field(self):
        self.assertIsNone(storage_provider.url(self.scene.media_path))

    def test_returns_string_after_upload(self):
        self.scene.media_path.save("scene_00.png", ContentFile(b"\x89PNG"), save=True)
        self.scene.refresh_from_db()
        result = storage_provider.url(self.scene.media_path)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
```

- [ ] **Step 4: Write `test_storage_paths.py`**

```python
import tempfile
from pathlib import Path

from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage import storage_provider


def _owner(sub="sub-paths"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@test.com")

def _project(owner):
    return Project.objects.create(owner=owner, prompt="paths test")

def _tmp(suffix=".png") -> Path:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(b"data")
    f.flush()
    return Path(f.name)


class UploadToPathStructureTest(TestCase):
    def setUp(self):
        self.owner = _owner()
        self.project = _project(self.owner)
        self.scene = Scene.objects.create(project=self.project, index=0)

    def test_scene_media_path_structure(self):
        storage_provider.upload(self.scene.media_path, _tmp(".png"))
        self.scene.refresh_from_db()
        key = self.scene.media_path.name
        self.assertTrue(key.startswith(f"{self.owner.id}/{self.project.id}/images/"), key)

    def test_different_users_have_different_prefixes(self):
        owner2 = UserProfile.objects.create(cognito_sub="sub-paths-2", email="sub-paths-2@test.com")
        scene2 = Scene.objects.create(project=_project(owner2), index=0)
        storage_provider.upload(self.scene.media_path, _tmp())
        storage_provider.upload(scene2.media_path, _tmp())
        self.scene.refresh_from_db()
        scene2.refresh_from_db()
        self.assertNotEqual(
            self.scene.media_path.name.split("/")[0],
            scene2.media_path.name.split("/")[0],
        )

    def test_different_projects_have_different_prefixes(self):
        scene2 = Scene.objects.create(project=_project(self.owner), index=0)
        storage_provider.upload(self.scene.media_path, _tmp())
        storage_provider.upload(scene2.media_path, _tmp())
        self.scene.refresh_from_db()
        scene2.refresh_from_db()
        self.assertEqual(
            self.scene.media_path.name.split("/")[0],
            scene2.media_path.name.split("/")[0],
        )
        self.assertNotEqual(
            self.scene.media_path.name.split("/")[1],
            scene2.media_path.name.split("/")[1],
        )
```

- [ ] **Step 5: Write `test_signed_urls.py`**

```python
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage import _get_provider, storage_provider
from apps.storage.local_storage import LocalStorageProvider
from apps.storage.s3_storage import S3StorageProvider


def _setup():
    owner = UserProfile.objects.create(cognito_sub="sub-signed", email="signed@test.com")
    project = Project.objects.create(owner=owner, prompt="signed url test")
    scene = Scene.objects.create(project=project, index=0)
    scene.media_path.save("scene_00.png", ContentFile(b"\x89PNG"), save=True)
    scene.refresh_from_db()
    return scene


class S3StorageProviderUrlTest(TestCase):
    def test_url_calls_storage_url_with_expire(self):
        scene = _setup()
        mock_storage = MagicMock()
        mock_storage.url.return_value = "https://bucket.s3.amazonaws.com/path?X-Amz-Expires=3600&sig=abc"
        provider = S3StorageProvider(expire=3600)
        with patch.object(scene.media_path, "storage", mock_storage):
            url = provider.url(scene.media_path)
        mock_storage.url.assert_called_once_with(scene.media_path.name, expire=3600)
        self.assertIn("X-Amz-Expires=3600", url)

    def test_url_returns_none_for_empty_field(self):
        owner = UserProfile.objects.create(cognito_sub="sub-signed-empty", email="se@test.com")
        project = Project.objects.create(owner=owner, prompt="empty field")
        scene = Scene.objects.create(project=project, index=0)
        self.assertIsNone(S3StorageProvider(expire=3600).url(scene.media_path))

    def test_custom_expire_forwarded_to_storage(self):
        scene = _setup()
        mock_storage = MagicMock()
        mock_storage.url.return_value = "https://bucket.s3.amazonaws.com/path?X-Amz-Expires=1800"
        provider = S3StorageProvider(expire=1800)
        with patch.object(scene.media_path, "storage", mock_storage):
            provider.url(scene.media_path)
        _, kwargs = mock_storage.url.call_args
        self.assertEqual(kwargs["expire"], 1800)


class GetProviderDetectionTest(TestCase):
    def test_returns_local_in_test_settings(self):
        self.assertIsInstance(_get_provider(), LocalStorageProvider)

    def test_returns_s3_when_default_storage_is_s3(self):
        from storages.backends.s3boto3 import S3Boto3Storage
        mock_s3 = MagicMock(spec=S3Boto3Storage)
        mock_s3.querystring_expire = 1800
        with patch("django.core.files.storage.default_storage", mock_s3):
            provider = _get_provider()
        self.assertIsInstance(provider, S3StorageProvider)
        self.assertEqual(provider._expire, 1800)


class StorageProviderUrlApiTest(TestCase):
    def test_returns_local_url_in_test_settings(self):
        scene = _setup()
        url = storage_provider.url(scene.media_path)
        self.assertIsNotNone(url)
        self.assertIsInstance(url, str)

    def test_returns_none_for_empty_field(self):
        owner = UserProfile.objects.create(cognito_sub="sub-fu-empty", email="fue@test.com")
        project = Project.objects.create(owner=owner, prompt="empty")
        scene = Scene.objects.create(project=project, index=0)
        self.assertIsNone(storage_provider.url(scene.media_path))
```

- [ ] **Step 6: Run full test suite**

```bash
cd backend && python manage.py test apps --settings=config.settings.test -v 1
```

Expected: all tests pass.

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Media to storage; DB holds references only | Task 2 (FileField), Task 3 (`storage_provider.upload()` writes key to field) |
| Scene images → storage | Task 3 `run_image_stage` calls `storage_provider.upload()` |
| Scene audio → storage | Task 3 stub comment in `run_voice_stage` |
| Final video → storage | Task 3 stub comment in `run_assemble_stage` |
| Environment-swappable backend, no code branching | `_get_provider()` detects `default_storage` at runtime; `storage_provider` global is the only call site |
| Dev/CI offline (no AWS) | `test.py` → InMemoryStorage; `base.py` → FileSystemStorage |
| Private media + signed URLs (~1 hour) | `querystring_auth=True, querystring_expire=3600`; `S3StorageProvider.url()` forwards `expire` per-call; Task 5 endpoints |
| User-scoped key `{user_id}/{project_id}/…` | Task 2 upload_to helpers; mirrors `get_work_dir()` |
| Abstract storage provider base class | `BaseStorageProvider` ABC in `apps/storage/base_storage.py` |
| Global provider — no wrapper functions | `storage_provider = SimpleLazyObject(_get_provider)` in `__init__.py` |
| Secrets only in `.env` | production reads `os.environ["AWS_STORAGE_BUCKET_NAME"]` |
| Migration applies cleanly | Task 2 (0003 + 0004 both applied) |

### Known Non-Scope Items

1. `run_voice_stage` and `run_assemble_stage` get stub comments only — wired when those TODO backends are filled.
2. Old `Scene.media_path` DB values (absolute paths) won't resolve through storage — affected rows need re-generation; no data migration.
