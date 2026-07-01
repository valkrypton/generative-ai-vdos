# Image Preview URL — Design Spec

**Date:** 2026-06-30  
**Status:** Approved

## Problem

Images are shown on the frontend only after: DashScope API call → download image from CDN → convert to PNG → upload to S3 → DB update → 3s poll. The download + S3 upload adds ~2–5s of delay after the provider already has the image URL. Users see a spinner for longer than necessary.

## Goal

Show the image on the frontend as soon as the provider returns a CDN URL — before download, convert, or S3 upload — while still uploading to S3 for permanent storage.

## Approach: Preview URL via DB + SSE

After the DashScope API call returns, save the CDN URL to a new `Scene.preview_url` field and broadcast it via SSE. The frontend subscribes to the SSE stream and updates the scene image immediately — no poll delay. S3 upload continues in the background; once done, `media_path` becomes authoritative and `preview_url` is cleared.

This approach was chosen over:
- **Poll-only** (save URL to DB, wait for 3s poll): saves the poll delay on top of download+upload savings.
- **Skip S3 entirely**: DashScope CDN URLs expire; video assembly reads from S3 — would break.

## Data Model

**Implemented.** `Scene.preview_url` (`models.CharField(max_length=2048, blank=True, default="")`) is live at `apps/projects/models.py:150`, via migration `0004_add_scene_preview_url.py`. Field is temporary — cleared after S3 upload completes.

`SceneSerializer` exposes `preview_url` (`serializers.py:45,50`). `project-types.ts` declares `preview_url: string` (`project-types.ts:40`).

## Provider Interface

`generate_scene_image` in `pipeline/images/__init__.py` gains an optional param:

```python
def generate_scene_image(..., on_preview_url: Callable[[str], None] | None = None)
```

It threads down to `QwenImageProvider.generate()` → `_post()` → `_post_inner()`. In `_post_inner`, after extracting `image_url` from the DashScope response, call `on_preview_url(image_url)` **before** the download. Other providers (`FluxProvider`, `PlaceholderProvider`, etc.) accept the param and ignore it.

The `on_preview_url` callback runs inside the `_concurrency_slot` context (still holding the semaphore slot) since it's called from `_post_inner`. The callback is fast (DB write + Redis publish), so this is acceptable.

## Backend: `generate_scene` (utils.py)

Before calling `generate_scene_image`, define:

```python
def _on_preview(url: str) -> None:
    scene.preview_url = url
    scene.save(update_fields=["preview_url", "updated_at"])
    publish_event(
        project_id, Stage.IMAGES, Level.INFO,
        f"Scene {scene_index} preview ready",
        scene_index=scene_index,
        preview_url=url,
        media_status=MediaStatus.RUNNING,
    )
```

Pass `on_preview_url=_on_preview` into `generate_scene_image`.

After S3 upload and saving `media_path`, clear the preview:

```python
scene.preview_url = ""
scene.save(update_fields=["preview_url", "media_path", "media_status", "media_provider", "updated_at"])
```

## Frontend

### `lib/project-types.ts`

Add to `Scene` type:
```typescript
preview_url: string
```

### `components/project/generating-view.tsx`

Subscribe to `/api/projects/{id}/events/` with `EventSource` after mount. On each message:
- Parse JSON payload
- If `scene_index` and `preview_url` are present, update that scene in local state: `setScenes(prev => prev.map(s => s.index === data.scene_index ? { ...s, preview_url: data.preview_url } : s))`
- If `project_status` is `DONE` or `FAILED`, close the SSE connection

Keep existing 3s scene poll as fallback (handles the case where Redis/SSE is unavailable). SSE and poll coexist safely — whichever arrives first updates state.

Close SSE in cleanup (`return () => { es.close() }`).

### `components/project/scene-grid.tsx`

In the image slot, when `media_status === 'RUNNING'`:
- Show `preview_url` image if `preview_url` is set (CDN image loads fast)
- Continue showing spinner overlay (status is still RUNNING)

When `media_status === 'DONE'`: show `media_path` image as today.

```tsx
const displaySrc = scene.media_status === 'DONE'
  ? scene.media_path
  : scene.preview_url || null
```

## Error Handling

- If `_on_preview` callback throws (Redis down, DB error), it must not crash `generate_scene_image`. Wrap callback call in `try/except` inside `_post_inner`; log warning and continue.
- If SSE connection drops, the 3s poll catches up.
- `preview_url` is always cleared on success or failure of the image task — no stale CDN URLs left in DB.
  - On failure: `scene.preview_url = ""` in the `except` branch of `generate_scene`.

## Sequence

```text
Celery task → generate_scene()
  → generate_scene_image(on_preview_url=_on_preview)
    → QwenImageProvider._post()
      → _post_inner()
        → DashScope API call  ← ~10-30s
        → on_preview_url(cdn_url)
          → scene.preview_url = cdn_url  (DB write)
          → publish_event(..., preview_url=cdn_url)  (Redis pub)
            → SSE stream → frontend EventSource
              → setScenes([..., { preview_url: cdn_url }])
                → SceneGrid shows image  ← INSTANT
        → download image from CDN  ← ~1s
        → convert to PNG
    → returns bytes
  → upload to S3  ← ~1s
  → scene.media_path = S3 url, preview_url = ""
  → publish_event(..., media_status=DONE)
    → SSE → frontend switches to media_path
```

## Files Changed

| File | Change |
|------|--------|
| `backend/apps/projects/models.py` | Add `preview_url` to `Scene` |
| `backend/apps/projects/migrations/` | New migration |
| `backend/apps/projects/serializers.py` | Expose `preview_url` |
| `backend/apps/projects/utils.py` | `_on_preview` callback, pass to `generate_scene_image`, clear on done/fail |
| `pipeline/images/__init__.py` | Add `on_preview_url` param to `generate_scene_image` |
| `pipeline/images/qwen_image.py` | Thread param to `_post` → `_post_inner`; call callback |
| `pipeline/images/base.py` | Add `on_preview_url=None` to `generate` and `edit` signatures |
| `pipeline/images/flux.py` | Accept + ignore `on_preview_url` |
| `pipeline/images/gpt_image.py` | Accept + ignore `on_preview_url` |
| `pipeline/images/pexels.py` | Accept + ignore `on_preview_url` |
| `pipeline/images/placeholder.py` | Accept + ignore `on_preview_url` |
| `webapp/lib/project-types.ts` | Add `preview_url: string` to `Scene` |
| `webapp/components/project/generating-view.tsx` | Subscribe to SSE; update scene preview on event |
| `webapp/components/project/scene-grid.tsx` | Show `preview_url` during RUNNING state |

## Out of Scope

- CLI pipeline: no change (no SSE, no DB, preview URL irrelevant)
- Video (`media_path` → `.mp4`) stage: no preview URL needed
- Voiceover, assemble stages: unchanged
