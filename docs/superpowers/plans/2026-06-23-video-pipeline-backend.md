# Video Pipeline Backend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `pipeline/video` (Wan image-to-video) into the Django backend as a Celery task that animates all `animate=True` scenes in a single batch, mirroring the image stage pattern.

**Architecture:** Rename `image_status`/`image_provider`/`ImageStatus` → `media_status`/`media_provider`/`MediaStatus` across the backend (migration + code), then add `run_video_stage` as a batch Celery task that submits all animated scenes to `WanProvider`, polls them concurrently, and saves mp4 clips via `default_storage`. Wire the task into the existing `_dispatch_generate_stage` chain after images and before voice.

**Tech Stack:** Django, Celery, `pipeline.video.wan.WanProvider`, `django.core.files.storage.default_storage`, `tempfile` (to bridge storage bytes → local Path for WanProvider)

## Global Constraints

- Branch: `feature/video-pipeline-backend`
- Python 3.13+ — use `X | None` union syntax freely
- Run tests: `python manage.py test apps.projects` from `backend/`
- No changes to any file under `pipeline/video/`
- `WanProvider` requires local `Path` for `submit()`, not bytes — always use `tempfile.NamedTemporaryFile`
- Delete old `media_path` from storage before saving new one (mirrors image stage pattern)
- `CELERY_TASK_ALWAYS_EAGER = True` in test settings — tasks run synchronously in tests

---

## File Map

### Task 1 — Rename files
| File | Change |
|---|---|
| `backend/apps/projects/constants.py` | Rename class `ImageStatus` → `MediaStatus` |
| `backend/apps/projects/models.py` | Rename field `image_status` → `media_status`, `image_provider` → `media_provider`; update class alias |
| `backend/apps/projects/serializers.py` | Update field name strings in `SceneSerializer` |
| `backend/apps/projects/utils.py` | Replace all `ImageStatus`/`image_status`/`image_provider` refs |
| `backend/apps/projects/tasks.py` | Replace `ImageStatus` import + refs in `run_image_stage` |
| `backend/apps/projects/views.py` | Replace `ImageStatus` import + all refs |
| `backend/apps/projects/admin.py` | Update `readonly_fields` list |
| `backend/apps/projects/tests/test_models_scenes.py` | Update import + assertions |
| `backend/apps/projects/tests/test_orchestration.py` | Update import + mock helper |
| `backend/apps/projects/migrations/0002_rename_image_fields.py` | `RenameField` migration (created manually) |

### Task 2 — New task + wiring
| File | Change |
|---|---|
| `backend/apps/projects/tasks.py` | Add imports + `_VIDEO_TASK_OPTS` + `run_video_stage` |
| `backend/apps/projects/orchestration.py` | Import `run_video_stage` + add `run_video()` |
| `backend/apps/projects/views.py` | Import `run_video_stage` + add to `_dispatch_generate_stage` chain |
| `backend/apps/projects/tests/test_tasks_video.py` | New — full test coverage for `run_video_stage` |

---

## Task 1: Rename ImageStatus → MediaStatus + migration

**Files:**
- Modify: `backend/apps/projects/constants.py`
- Modify: `backend/apps/projects/models.py`
- Modify: `backend/apps/projects/serializers.py`
- Modify: `backend/apps/projects/utils.py`
- Modify: `backend/apps/projects/tasks.py` (rename only, no new task yet)
- Modify: `backend/apps/projects/views.py` (rename only, no new wiring yet)
- Modify: `backend/apps/projects/admin.py`
- Modify: `backend/apps/projects/tests/test_models_scenes.py`
- Modify: `backend/apps/projects/tests/test_orchestration.py`
- Create: `backend/apps/projects/migrations/0002_rename_image_fields.py`

**Interfaces:**
- Produces: `MediaStatus` in `constants.py`; `Scene.media_status` / `Scene.media_provider` fields; migration `0002_rename_image_fields`

- [ ] **Step 1: Rename `ImageStatus` → `MediaStatus` in `constants.py`**

Replace the class name only — choices values are unchanged:

```python
# backend/apps/projects/constants.py
class MediaStatus(models.TextChoices):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
```

- [ ] **Step 2: Update `models.py` — rename fields and class alias**

```python
# backend/apps/projects/models.py
from apps.projects.constants import (
    TRANSITIONS,
    Capability,
    MediaStatus,          # was ImageStatus
    Level,
    MusicMood,
    NarratorVoice,
    Stage,
    Status,
    StylePreset,
)

class Project(TimestampMixin):
    Status = Status
    MediaStatus = MediaStatus   # was ImageStatus = ImageStatus

class Scene(TimestampMixin):
    MediaStatus = MediaStatus   # was ImageStatus = ImageStatus
    ...
    media_status = models.CharField(           # was image_status
        max_length=20, choices=MediaStatus.choices, default=MediaStatus.PENDING
    )
    media_provider = models.CharField(max_length=50, blank=True, default="")  # was image_provider
```

- [ ] **Step 3: Create migration `0002_rename_image_fields.py`**

Write the file directly (do not run `makemigrations` — Django can't auto-detect renames):

```python
# backend/apps/projects/migrations/0002_rename_image_fields.py
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="scene",
            old_name="image_status",
            new_name="media_status",
        ),
        migrations.RenameField(
            model_name="scene",
            old_name="image_provider",
            new_name="media_provider",
        ),
    ]
```

- [ ] **Step 4: Update `serializers.py`**

```python
# backend/apps/projects/serializers.py
class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = [
            "id", "index", "narration", "media_prompt", "animate",
            "on_screen_text", "negative_prompt",
            "media_path", "media_status", "media_provider",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "index", "media_path", "media_status",
            "media_provider", "created_at", "updated_at",
        ]
```

- [ ] **Step 5: Update `utils.py` — rename all refs**

Replace every occurrence (use `replace_all` / global find-replace):
- `ImageStatus` → `MediaStatus`
- `image_status` → `media_status`
- `image_provider` → `media_provider`

The import line becomes:
```python
from apps.projects.constants import Capability, MediaStatus, Level, Stage, Status
```

All `scene.image_status = ...` → `scene.media_status = ...`
All `scene.image_provider = ...` → `scene.media_provider = ...`
All `update_fields=[..., "image_status", ...]` → `update_fields=[..., "media_status", ...]`
All `update_fields=[..., "image_provider", ...]` → `update_fields=[..., "media_provider", ...]`

- [ ] **Step 6: Update `tasks.py` — rename refs in existing code (no new task yet)**

Change import:
```python
from apps.projects.constants import MediaStatus, Level, Stage, Status
```

In `run_image_stage`:
```python
scene.media_status = MediaStatus.FAILED
scene.save(update_fields=["media_status", "updated_at"])
```

- [ ] **Step 7: Update `views.py` — rename refs**

Change import:
```python
from .constants import MediaStatus, Status
```

All occurrences:
- `image_status=ImageStatus.PENDING` → `media_status=MediaStatus.PENDING`
- `update_fields = ["image_status", "updated_at"]` → `update_fields = ["media_status", "updated_at"]`
- `"image_status": None` in the SSE event dict (line ~115) → `"media_status": None`

- [ ] **Step 8: Update `admin.py`**

```python
class SceneInline(admin.TabularInline):
    model = Scene
    extra = 0
    readonly_fields = ["index", "narration", "media_prompt", "media_status", "media_provider", "media_path"]
    fields = readonly_fields
```

- [ ] **Step 9: Update `tests/test_models_scenes.py`**

```python
from apps.projects.constants import MediaStatus   # was ImageStatus

class SceneTest(TestCase):
    def test_create_scene(self):
        s = Scene.objects.create(project=self.project, index=0)
        self.assertEqual(s.media_status, MediaStatus.PENDING)   # was image_status
        self.assertFalse(s.media_path)
        self.assertEqual(s.media_provider, "")                  # was image_provider
```

- [ ] **Step 10: Update `tests/test_orchestration.py`**

```python
from apps.projects.constants import MediaStatus, Status   # was ImageStatus

def _mock_generate_scene(project, scene, scene_index):
    scene.media_status = MediaStatus.DONE          # was image_status
    scene.media_path = f"scenes/test/scene_{scene_index:02d}.png"
    scene.media_provider = "placeholder"           # was image_provider
    scene.save(update_fields=["media_path", "media_status", "media_provider", "updated_at"])
    return scene.media_path

# Inside RunImagesTest.test_images_marks_scenes_done:
    for scene in Scene.objects.filter(project=project):
        self.assertEqual(scene.media_status, MediaStatus.DONE)  # was image_status
```

- [ ] **Step 11: Run migrations and tests**

```bash
cd backend
python manage.py migrate
python manage.py test apps.projects
```

Expected: all existing tests pass, migration applies cleanly.

- [ ] **Step 12: Commit**

```bash
git add backend/apps/projects/constants.py \
        backend/apps/projects/models.py \
        backend/apps/projects/serializers.py \
        backend/apps/projects/utils.py \
        backend/apps/projects/tasks.py \
        backend/apps/projects/views.py \
        backend/apps/projects/admin.py \
        backend/apps/projects/migrations/0002_rename_image_fields.py \
        backend/apps/projects/tests/test_models_scenes.py \
        backend/apps/projects/tests/test_orchestration.py
git commit -m "refactor(projects): rename ImageStatus → MediaStatus, image_status → media_status"
```

---

## Task 2: Add `run_video_stage` + wire into pipeline chain + tests

**Files:**
- Modify: `backend/apps/projects/tasks.py`
- Modify: `backend/apps/projects/orchestration.py`
- Modify: `backend/apps/projects/views.py`
- Create: `backend/apps/projects/tests/test_tasks_video.py`

**Interfaces:**
- Consumes: `MediaStatus` from Task 1; `Scene.media_status`, `Scene.media_provider` from Task 1
- Produces: `run_video_stage(self, project_id)` — Celery task; `run_video(project_id)` in `orchestration.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/projects/tests/test_tasks_video.py
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import Provider
from apps.projects.constants import Capability, MediaStatus, Status
from apps.projects.models import LLMModel, Project, Scene
from apps.projects.tasks import run_video_stage
from apps.projects.tests.helpers import make_project, make_shot_plan


def _make_video_model():
    provider = Provider.objects.create(code="dashscope", name="DashScope")
    return LLMModel.objects.create(
        provider=provider, capability=Capability.VIDEO,
        model_id="wan2.2-i2v-flash", display_name="Wan Flash",
        is_free=True, is_default=True,
    )


def _make_animated_project(video_model=None):
    """Project in GENERATING state with one animated scene and one still scene."""
    project = make_project(
        shot_plan=make_shot_plan(2),
        video_model=video_model,
    )
    Project.objects.filter(pk=project.pk).update(status=Status.GENERATING)
    project.refresh_from_db()
    Scene.objects.create(
        project=project, index=0,
        narration="animated narration", media_prompt="flying dragon",
        animate=True, media_path="scenes/test/scene_00.png",
    )
    Scene.objects.create(
        project=project, index=1,
        narration="still narration", media_prompt="mountain valley",
        animate=False, media_path="scenes/test/scene_01.png",
    )
    return project


FAKE_PNG = b"\x89PNG\r\n\x1a\n"
FAKE_MP4 = b"fake-mp4-bytes"


class RunVideoStageSkipTest(TestCase):
    def test_no_animated_scenes_returns_early(self):
        """No animate=True scenes → task publishes skip event and returns without calling submit."""
        vm = _make_video_model()
        project = make_project(shot_plan=make_shot_plan(2), video_model=vm)
        Project.objects.filter(pk=project.pk).update(status=Status.GENERATING)
        Scene.objects.create(project=project, index=0, narration="n",
                             media_prompt="p", animate=False,
                             media_path="scenes/test/scene_00.png")

        with patch("pipeline.video.wan.WanProvider.submit") as mock_submit:
            run_video_stage(str(project.id))
            mock_submit.assert_not_called()


class RunVideoStageHappyPathTest(TestCase):
    @patch("apps.projects.tasks.default_storage")
    @patch("apps.projects.tasks._motion_prompt", return_value="gentle cinematic motion")
    @patch("pipeline.video.wan.WanProvider.download")
    @patch("pipeline.video.wan.WanProvider.poll", return_value="https://cdn.example.com/clip.mp4")
    @patch("pipeline.video.wan.WanProvider.submit", return_value="task_abc123")
    @patch("apps.projects.tasks.time")
    def test_animates_scene_and_marks_done(
        self, mock_time, mock_submit, mock_poll, mock_download,
        mock_motion, mock_storage,
    ):
        mock_time.time.return_value = 0          # deadline = 0 + 1800; never expires
        mock_time.sleep = MagicMock()

        storage_file = MagicMock()
        storage_file.__enter__ = MagicMock(return_value=storage_file)
        storage_file.__exit__ = MagicMock(return_value=False)
        storage_file.read.return_value = FAKE_PNG
        mock_storage.open.return_value = storage_file
        mock_storage.exists.return_value = True
        mock_storage.save.return_value = "scenes/uuid/scene_00.mp4"
        mock_download.side_effect = lambda url, path: path.write_bytes(FAKE_MP4)

        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)

        run_video_stage(str(project.id))

        mock_submit.assert_called_once()
        mock_poll.assert_called_with("task_abc123")

        animated = Scene.objects.get(project=project, index=0)
        self.assertEqual(animated.media_status, MediaStatus.DONE)
        self.assertEqual(animated.media_provider, "wan-i2v")
        self.assertEqual(animated.media_path, "scenes/uuid/scene_00.mp4")

        still = Scene.objects.get(project=project, index=1)
        self.assertEqual(still.media_status, MediaStatus.PENDING)  # unaffected


class RunVideoStageFailureTest(TestCase):
    @patch("apps.projects.tasks.default_storage")
    @patch("apps.projects.tasks._motion_prompt", return_value="prompt")
    @patch("pipeline.video.wan.WanProvider.submit", side_effect=RuntimeError("API down"))
    @patch("apps.projects.tasks.time")
    def test_submit_failure_marks_scene_and_project_failed(
        self, mock_time, mock_submit, mock_motion, mock_storage,
    ):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()

        storage_file = MagicMock()
        storage_file.__enter__ = MagicMock(return_value=storage_file)
        storage_file.__exit__ = MagicMock(return_value=False)
        storage_file.read.return_value = FAKE_PNG
        mock_storage.open.return_value = storage_file

        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)

        run_video_stage(str(project.id))

        scene = Scene.objects.get(project=project, index=0)
        self.assertEqual(scene.media_status, MediaStatus.FAILED)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
        self.assertIn("All animated scene submissions failed", project.error)

    def test_no_video_model_marks_project_failed(self):
        project = _make_animated_project(video_model=None)

        run_video_stage(str(project.id))

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
        self.assertIn("No video model", project.error)

    @patch("apps.projects.tasks.default_storage")
    @patch("apps.projects.tasks._motion_prompt", return_value="prompt")
    @patch("pipeline.video.wan.WanProvider.poll", side_effect=RuntimeError("poll failed"))
    @patch("pipeline.video.wan.WanProvider.submit", return_value="task_xyz")
    @patch("apps.projects.tasks.time")
    def test_poll_failure_marks_scene_and_project_failed(
        self, mock_time, mock_submit, mock_poll, mock_motion, mock_storage,
    ):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()

        storage_file = MagicMock()
        storage_file.__enter__ = MagicMock(return_value=storage_file)
        storage_file.__exit__ = MagicMock(return_value=False)
        storage_file.read.return_value = FAKE_PNG
        mock_storage.open.return_value = storage_file

        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)

        run_video_stage(str(project.id))

        scene = Scene.objects.get(project=project, index=0)
        self.assertEqual(scene.media_status, MediaStatus.FAILED)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
```

- [ ] **Step 2: Run tests — verify they all fail**

```bash
cd backend
python manage.py test apps.projects.tests.test_tasks_video -v 2
```

Expected: `ImportError` or `AttributeError: module 'apps.projects.tasks' has no attribute 'run_video_stage'`

- [ ] **Step 3: Add imports to `tasks.py`**

Add at the top of `backend/apps/projects/tasks.py` (after existing imports):

```python
import time
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from pipeline.video import _motion_prompt
from pipeline.video.wan import WanProvider
```

- [ ] **Step 4: Add `_VIDEO_TASK_OPTS` to `tasks.py`**

Add after `_IMAGE_TASK_OPTS`:

```python
_VIDEO_TASK_OPTS = dict(
    bind=True,
    max_retries=2,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=30 * 60,
    time_limit=33 * 60,
)
```

- [ ] **Step 5: Add `run_video_stage` to `tasks.py`**

Add after `run_image_stage`:

```python
@shared_task(**_VIDEO_TASK_OPTS)
def run_video_stage(self, project_id):
    project = Project.objects.select_related(
        "video_model", "video_model__provider", "owner",
    ).get(id=project_id)

    animated_scenes = list(
        Scene.objects.filter(project_id=project_id, animate=True)
        .exclude(media_status=MediaStatus.DONE)
    )

    if not animated_scenes:
        publish_event(project_id, Stage.VIDEO, Level.INFO,
                      "No animated scenes — video stage skipped")
        return {"project_id": str(project_id)}

    try:
        if not project.video_model:
            raise RuntimeError("No video model assigned to project.")

        plan = ShotPlan(**project.shot_plan)
        provider = WanProvider()

        publish_event(project_id, Stage.VIDEO, Level.INFO,
                      f"Animating {len(animated_scenes)} scene(s) via {provider.name}")

        # --- Submit phase ---
        pending = {}  # {scene.index: (scene, task_id)}
        for scene in animated_scenes:
            scene.media_status = MediaStatus.RUNNING
            scene.save(update_fields=["media_status", "updated_at"])
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                with default_storage.open(scene.media_path) as f:
                    tmp_path.write_bytes(f.read())
                prompt = _motion_prompt(plan, plan.scenes[scene.index])
                task_id = provider.submit(prompt, tmp_path)
                pending[scene.index] = (scene, task_id)
                publish_event(project_id, Stage.VIDEO, Level.INFO,
                              f"Scene {scene.index} submitted")
            except Exception as exc:
                scene.media_status = MediaStatus.FAILED
                scene.save(update_fields=["media_status", "updated_at"])
                publish_event(project_id, Stage.VIDEO, Level.ERROR,
                              f"Scene {scene.index} submit failed: {exc}")
            finally:
                if tmp_path:
                    tmp_path.unlink(missing_ok=True)

        if not pending:
            fail_project(project, project_id, Stage.VIDEO,
                         RuntimeError("All animated scene submissions failed"))
            return {"project_id": str(project_id)}

        # --- Poll phase ---
        deadline = time.time() + 30 * 60
        while pending and time.time() < deadline:
            time.sleep(15)
            for idx in list(pending):
                scene, task_id = pending[idx]
                try:
                    url = provider.poll(task_id)
                except Exception as exc:
                    scene.media_status = MediaStatus.FAILED
                    scene.save(update_fields=["media_status", "updated_at"])
                    publish_event(project_id, Stage.VIDEO, Level.ERROR,
                                  f"Scene {idx} poll failed: {exc}")
                    del pending[idx]
                    continue
                if url is None:
                    continue
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    provider.download(url, tmp_path)
                    storage_path = f"scenes/{project_id}/scene_{idx:02d}.mp4"
                    if scene.media_path and default_storage.exists(scene.media_path):
                        default_storage.delete(scene.media_path)
                    saved_name = default_storage.save(
                        storage_path, ContentFile(tmp_path.read_bytes())
                    )
                    scene.media_path = saved_name
                    scene.media_status = MediaStatus.DONE
                    scene.media_provider = provider.name
                    scene.save(update_fields=[
                        "media_path", "media_status", "media_provider", "updated_at"
                    ])
                    publish_event(project_id, Stage.VIDEO, Level.INFO,
                                  f"Scene {idx} clip saved via {provider.name}")
                except Exception as exc:
                    scene.media_status = MediaStatus.FAILED
                    scene.save(update_fields=["media_status", "updated_at"])
                    publish_event(project_id, Stage.VIDEO, Level.ERROR,
                                  f"Scene {idx} save failed: {exc}")
                finally:
                    if tmp_path:
                        tmp_path.unlink(missing_ok=True)
                del pending[idx]

        # Deadline exceeded — mark remaining as failed
        for idx, (scene, _) in list(pending.items()):
            scene.media_status = MediaStatus.FAILED
            scene.save(update_fields=["media_status", "updated_at"])
            publish_event(project_id, Stage.VIDEO, Level.ERROR,
                          f"Scene {idx} timed out after 30 min")

        done_count = Scene.objects.filter(
            project_id=project_id, animate=True, media_status=MediaStatus.DONE
        ).count()
        if done_count == 0:
            fail_project(project, project_id, Stage.VIDEO,
                         RuntimeError("All animated scenes failed"))
        else:
            publish_event(project_id, Stage.VIDEO, Level.INFO,
                          f"Video stage complete — {done_count} clip(s) done")

    except (ConnectionError, TimeoutError) as exc:
        handle_transient_error(self, project, project_id, Stage.VIDEO, exc)
    except Exception as exc:
        fail_project(project, project_id, Stage.VIDEO, exc)

    return {"project_id": str(project_id)}
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
cd backend
python manage.py test apps.projects.tests.test_tasks_video -v 2
```

Expected: all 5 tests pass.

- [ ] **Step 7: Add `run_video` to `orchestration.py`**

```python
# backend/apps/projects/orchestration.py
from apps.projects.tasks import (
    run_image_stage,
    mark_pipeline_failed,
    run_assemble_stage,
    run_voice_stage,
    run_video_stage,          # ADD
)

# ... existing _is_eager, _dispatch, run_images, run_voice, run_assembly ...

def run_video(project_id):
    """Dispatch video animation for animated scenes (batch, fail-soft per-scene)."""
    pid = str(project_id)
    return _dispatch(run_video_stage.s(pid), project_id)
```

- [ ] **Step 8: Wire `run_video_stage` into `_dispatch_generate_stage` in `views.py`**

Update import line:
```python
from .tasks import run_assemble_stage, run_image_stage, run_refine_stage, run_voice_stage, run_video_stage
```

Update `_dispatch_generate_stage`:
```python
def _dispatch_generate_stage(project_id: str) -> None:
    from .models import Scene

    scene_indices = list(
        Scene.objects.filter(project_id=project_id)
        .order_by("index")
        .values_list("index", flat=True)
    )

    if scene_indices:
        tasks = [run_image_stage.s(project_id, scene_indices[0])]
        tasks += [run_image_stage.si(project_id, idx) for idx in scene_indices[1:]]
        tasks += [run_video_stage.si(project_id)]    # batch video after all images
        tasks += [run_voice_stage.si(project_id), run_assemble_stage.si(project_id)]
    else:
        tasks = [run_voice_stage.s(project_id), run_assemble_stage.si(project_id)]

    _eager_thread(chain(*tasks).delay)
```

- [ ] **Step 9: Run full test suite**

```bash
cd backend
python manage.py test apps.projects -v 2
```

Expected: all tests pass with no errors.

- [ ] **Step 10: Commit**

```bash
git add backend/apps/projects/tasks.py \
        backend/apps/projects/orchestration.py \
        backend/apps/projects/views.py \
        backend/apps/projects/tests/test_tasks_video.py
git commit -m "feat(projects): add run_video_stage Celery task and wire into pipeline chain"
```
