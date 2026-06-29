# Video Pipeline Backend Integration — Design Spec

**Date:** 2026-06-23
**Status:** Approved

## Summary

Integrate `pipeline/video` (Wan image-to-video) into the Django backend as a Celery task, mirroring how the image stage is integrated via `run_image_stage`. Animated scenes (`animate=True`) are submitted in a single batch, polled concurrently, and stored via `default_storage`. Still scenes (`animate=False`) are unaffected.

---

## Model Changes

### `Scene` — rename two fields (migration required)

| Old name | New name | Reason |
|---|---|---|
| `image_status` | `media_status` | Field tracks status for both images and video clips |
| `image_provider` | `media_provider` | Consistent naming |

`media_path` is unchanged — already routes correctly:
- `animate=False` → `{owner_id}/{project_id}/images/{filename}`
- `animate=True` → `{owner_id}/{project_id}/clip/{filename}`

### `ImageStatus` constant

Rename class to `MediaStatus` in `constants.py`. Choices unchanged: `PENDING / RUNNING / DONE / FAILED`.

### All references updated

`tasks.py`, `utils.py`, `serializers.py`, `constants.py`, `models.py` — all `image_status` / `image_provider` / `ImageStatus` references renamed to `media_status` / `media_provider` / `MediaStatus`.

---

## Celery Task

### `run_video_stage(self, project_id)` in `tasks.py`

Single batch task. Time limits: `soft_time_limit=30 min`, `time_limit=33 min`. Up to 2 retries on `ConnectionError`/`TimeoutError`.

**Flow:**

1. Load project with `select_related("video_model", "video_model__provider", "owner")`.
2. Load animated scenes: `Scene.objects.filter(project_id=project_id, animate=True).exclude(media_status=MediaStatus.DONE)`.
3. If no scenes, publish info event and return early.
4. Resolve `video_model` (raises if none assigned). Resolve provider API key via `resolve_secure_key`.
5. Reconstruct `ShotPlan(**project.shot_plan)` once before the loop.
6. For each scene:
   - Set `media_status=RUNNING`, save.
   - Read image bytes from `default_storage.open(scene.media_path)` → write to a `tempfile.NamedTemporaryFile` (suffix `.png`) to get a local `Path` — `WanProvider.submit` requires a `Path` object, not bytes.
   - Build motion prompt: `_motion_prompt(plan, plan.scenes[scene.index])` where `_motion_prompt` is imported from `pipeline.video`.
   - Call `provider.submit(motion_prompt, tmp_path)` → `task_id`.
   - Store `{scene.index: (scene, task_id)}` in `pending` dict.
   - Publish `Stage.VIDEO` event: "Scene N submitted".
   - On submit failure: set `media_status=FAILED`, publish error, skip scene.
6. Poll loop (`deadline = now + 30 min`, `sleep 15s`):
   - For each `(scene, task_id)` in `pending`:
     - Call `WanProvider.poll(task_id)`.
     - `None` → still running, skip.
     - URL returned → call `WanProvider.download(url, tmp_path)`, read bytes from tmp_path, save to `default_storage` at `scenes/{project_id}/scene_{NN:02d}.mp4`, update `scene.media_path`, set `media_status=DONE`, publish event, remove from `pending`.
     - Exception → set `media_status=FAILED`, publish error, remove from `pending`.
   - If `pending` empty → break early.
7. Any remaining in `pending` after deadline → `media_status=FAILED`, publish timeout event.
8. If all scenes failed → `fail_project(...)`.
9. Return `{"project_id": str(project_id)}`.

### Task options (`_VIDEO_TASK_OPTS`)

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

---

## Utility Function

The submit logic is thin enough to live inline in `run_video_stage` — no separate utility function needed. The task itself handles: provider resolution, tempfile management, submit, poll loop, and save. This keeps the batch polling loop self-contained (unlike images, there is no per-scene dispatch to separate concerns across).

`resolve_secure_key` and `fail_project` from `utils.py` are reused as-is.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| No `video_model` on project | Raise → `fail_project`, status → FAILED |
| Scene submit fails | `media_status=FAILED`, event published, other scenes continue |
| Scene poll raises | `media_status=FAILED`, event published, other scenes continue |
| Scene times out (30 min) | `media_status=FAILED`, timeout event published |
| All scenes failed | `fail_project`, project status → FAILED |
| `ConnectionError`/`TimeoutError` in task body | Celery auto-retry (up to 2×, backoff) |

---

## What Is NOT in Scope

- No new API endpoint to trigger `run_video_stage` (triggering mechanism follows however `run_image_stage` is triggered)
- No `wan_task_id` field on Scene (task_ids are in-memory only)
- No changes to `pipeline/video/` code
- No changes to `run_voice_stage` or `run_assemble_stage` (stubs remain as-is)
- No frontend changes
