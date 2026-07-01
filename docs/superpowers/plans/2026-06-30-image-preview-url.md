# Image Preview URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show DashScope CDN image on the frontend instantly after the provider API call, before download/convert/S3 upload.

**Architecture:** Add `preview_url` (temporary CDN URL) to the `Scene` model. Thread an `on_preview_url` callback from `generate_scene` down through `generate_scene_image` into `QwenImageProvider._post_inner`, where it fires as soon as the API returns a URL. The backend publishes the URL via SSE; the frontend subscribes and updates scene state immediately.

**Tech Stack:** Django 5.2, Django REST Framework, Celery, Redis pub/sub, Next.js 14, React, TypeScript, EventSource API.

## Global Constraints

- Python 3.13+ — use `X | None` union syntax
- `preview_url` is a temporary field — always cleared after S3 upload completes (success) or on failure
- Callback errors in `_post_inner` must not crash image generation — wrap in try/except
- No changes to CLI pipeline (`pipeline/images/__init__.py`'s `generate_images` function)
- Keep SSE + 3s poll coexisting — SSE is real-time update, poll is fallback

---

### Task 1: Add `preview_url` to Scene model and migration

**Status: already implemented** — `Scene.preview_url` (CharField, max_length=2048, blank=True, default="") exists at `backend/apps/projects/models.py:150`, and the migration shipped as `backend/apps/projects/migrations/0004_add_scene_preview_url.py`. No remaining work for this task.

- [x] Field added to `Scene` model
- [x] Migration generated and applied

---

### Task 2: Expose `preview_url` in serializer and TypeScript types

**Status: already implemented** — `preview_url` is present in `SceneSerializer.Meta.fields` and `read_only_fields` (`backend/apps/projects/serializers.py:45,50`), and `Scene.preview_url: string` is declared in `webapp/lib/project-types.ts:40`. No remaining work for this task.

- [x] `preview_url` added to `SceneSerializer` fields/read_only_fields
- [x] `preview_url: string` added to TypeScript `Scene` interface

---

### Task 3: Thread `on_preview_url` callback through provider chain

**Files:**
- Modify: `pipeline/images/base.py` — add `on_preview_url=None` to `generate()` signature
- Modify: `pipeline/images/flux.py` — accept + ignore param in `generate()`
- Modify: `pipeline/images/placeholder.py` — accept + ignore param in `generate()`
- Modify: `pipeline/images/pexels.py` — accept + ignore param in `generate()`
- Modify: `pipeline/images/gpt_image.py` — accept + ignore param in `generate()` and `edit()`
- Modify: `pipeline/images/qwen_image.py` — thread param to `_post()` → `_post_inner()`; call callback

**Interfaces:**
- Produces: `provider.generate(..., on_preview_url=None)` accepted by all providers; `QwenImageProvider` calls callback with CDN URL string before downloading

- [ ] **Step 1: Update base class signature**

In `pipeline/images/base.py`, replace the abstract `generate` signature:

```python
@abstractmethod
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None,
             api_key: "SecureString | None" = None,
             model: str | None = None) -> bytes:
    """Return a 1920x1080 PNG as bytes, or raise to let the fallback
    chain try the next provider."""
```

With:

```python
@abstractmethod
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None,
             api_key: "SecureString | None" = None,
             model: str | None = None,
             on_preview_url=None) -> bytes:
    """Return a 1920x1080 PNG as bytes, or raise to let the fallback
    chain try the next provider. on_preview_url, if provided, is called
    with the provider's raw CDN URL before any download/conversion."""
```

- [ ] **Step 2: Update non-qwen providers to accept + ignore the param**

`pipeline/images/flux.py` — change `generate` signature:
```python
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None, api_key=None,
             model: str | None = None, on_preview_url=None) -> bytes:
```

`pipeline/images/placeholder.py` — change `generate` signature:
```python
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None, api_key=None,
             model: str | None = None, on_preview_url=None) -> bytes:
```

`pipeline/images/pexels.py` — change `generate` signature:
```python
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None, api_key=None,
             model: str | None = None, on_preview_url=None) -> bytes:
```

`pipeline/images/gpt_image.py` — change both `generate` and `edit` signatures:
```python
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None, api_key=None,
             model: str | None = None, on_preview_url=None) -> bytes:
```
```python
def edit(self, prompt: str, reference,
         negative: str | None = None, api_key=None,
         model: str | None = None, on_preview_url=None) -> bytes:
```

- [ ] **Step 3: Thread `on_preview_url` through QwenImageProvider**

In `pipeline/images/qwen_image.py`:

**`_post` method** (line 94–97): add `on_preview_url=None` param and pass through:
```python
def _post(self, model: str, content: list,
          parameters: dict, api_key=None, on_preview_url=None) -> bytes:
    with _concurrency_slot():
        return self._post_inner(model, content, parameters, api_key,
                                on_preview_url=on_preview_url)
```

**`_post_inner` method** (line 99–114): add `on_preview_url=None` param and call it after extracting `image_url`:
```python
def _post_inner(self, model: str, content: list,
                parameters: dict, api_key=None, on_preview_url=None) -> bytes:
    configure_dashscope_sdk()
    key = api_key.decrypt() if api_key else os.environ.get("DASHSCOPE_API_KEY")
    t0_api = time.perf_counter()
    rsp = MultiModalConversation.call(
        model=model,
        messages=[{"role": "user", "content": content}],
        api_key=key,
        **parameters,
    )
    logger.info("qwen _post: api call (%s): %.2fs", model, time.perf_counter()-t0_api)
    if rsp.status_code != 200:
        raise RuntimeError(f"qwen image failed [{rsp.code}]: {rsp.message}")
    image_url = rsp.output.choices[0].message.content[0]["image"]
    if on_preview_url is not None:
        try:
            on_preview_url(image_url)
        except Exception as e:
            logger.warning("on_preview_url callback failed (ignored): %s", e)
    t0_dl = time.perf_counter()
    with urllib.request.urlopen(image_url, timeout=60) as resp:
        img = Image.open(io.BytesIO(resp.read())).convert("RGB")
    logger.info("qwen _post: image download: %.2fs", time.perf_counter()-t0_dl)
    return to_png_bytes(img)
```

**`generate` method** (line 116–128): add `on_preview_url=None` and pass to `_post`:
```python
def generate(self, prompt: str, query: str | None = None,
             negative: str | None = None, api_key=None,
             model: str | None = None, on_preview_url=None) -> bytes:
    if len(prompt) > MAX_PROMPT:
        print(f"  images: WARNING prompt is {len(prompt)} chars, cutting to "
              f"{MAX_PROMPT} — some detail at the end will be lost")
    return self._post(model or _gen_model(), [{"text": prompt[:MAX_PROMPT]}], {
        "size": SIZE,
        "n": 1,
        "prompt_extend": False,
        "watermark": False,
        "negative_prompt": _negative_prompt(negative),
    }, api_key=api_key, on_preview_url=on_preview_url)
```

**`edit` method** (line 130–143): add `on_preview_url=None` and pass to `_post`:
```python
def edit(self, prompt: str, reference,
         negative: str | None = None, api_key=None,
         model: str | None = None, on_preview_url=None) -> bytes:
    refs = list(reference) if isinstance(reference, (list, tuple)) else [reference]
    content = [{"image": "data:image/png;base64,"
                + base64.b64encode(Path(r).read_bytes()).decode()}
               for r in refs[:MAX_REFS]]
    content.append({"text": prompt[:MAX_PROMPT]})
    return self._post(model or _edit_model(), content, {
        "n": 1,
        "prompt_extend": False,
        "watermark": False,
        "negative_prompt": _negative_prompt(negative),
    }, api_key=api_key, on_preview_url=on_preview_url)
```

- [ ] **Step 4: Verify no import errors**

```bash
python -c "from pipeline.images import PROVIDERS; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add pipeline/images/base.py pipeline/images/flux.py pipeline/images/placeholder.py \
        pipeline/images/pexels.py pipeline/images/gpt_image.py pipeline/images/qwen_image.py
git commit -m "feat: thread on_preview_url callback through image provider chain"
```

---

### Task 4: Wire callback in `generate_scene_image` and `generate_scene`

**Files:**
- Modify: `pipeline/images/__init__.py:95-189` — add `on_preview_url` param to `generate_scene_image`, pass to provider calls
- Modify: `backend/apps/projects/utils.py:130-185` — define callback in `generate_scene`, pass to `generate_scene_image`, clear `preview_url` on done/fail

**Interfaces:**
- Consumes: `on_preview_url=None` param accepted by all providers (Task 3); `Scene.preview_url` CharField (Task 1); `publish_event` existing function
- Produces: `generate_scene_image(..., on_preview_url=None)` — passes callback through to provider

- [ ] **Step 1: Add `on_preview_url` param to `generate_scene_image`**

In `pipeline/images/__init__.py`, change the `generate_scene_image` signature (line 95):

```python
def generate_scene_image(
    plan: ShotPlan, index: int, primary: ImageProvider,
    fallback: bool = True, char_refs: dict | None = None,
    api_key=None, model: str | None = None,
    on_preview_url=None,
) -> tuple[bytes, ImageProvider]:
```

Then thread `on_preview_url` into the three call sites within the function:

1. The reference-image edit call (around line 161):
```python
return primary.edit(edit_prompt, refs, negative=merged_negative, api_key=api_key,
                    model=model, on_preview_url=on_preview_url), primary
```

2. The `scene.reference_image` edit call (around line 175):
```python
return editor.edit(prompt, ref, negative=merged_negative, api_key=api_key,
                   model=model, on_preview_url=on_preview_url), editor
```

3. The generate call in the fallback chain (around line 183):
```python
data = provider.generate(prompt, query=scene_prompt, negative=merged_negative,
                         api_key=api_key, model=model,
                         on_preview_url=on_preview_url if provider is primary else None)
```
Note: only pass the callback for the primary provider — if it falls back, the CDN URL callback no longer makes sense (different provider).

- [ ] **Step 2: Wire callback and preview_url in `generate_scene`**

In `backend/apps/projects/utils.py`, replace the `generate_scene` function with:

```python
def generate_scene(project, scene, scene_index):
    project_id = project.id
    plan = build_shot_plan(project)

    llm = project.image_model

    secure_key = resolve_secure_key(project.owner, llm.provider)
    provider = get_provider(llm.provider.code, api_key=secure_key)

    scene.media_status = MediaStatus.RUNNING
    scene.save(update_fields=["media_status", "updated_at"])
    publish_event(
        project_id, Stage.IMAGES, Level.INFO,
        f"Generating image for scene {scene_index} via {provider.name} ({llm.model_id})",
        scene_index=scene_index,
        media_status=MediaStatus.RUNNING,
    )

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

    t0_gen = time.perf_counter()
    data, used = generate_scene_image(
        plan, scene_index, provider,
        fallback=False,
        api_key=secure_key,
        model=llm.model_id,
        on_preview_url=_on_preview,
    )
    logger.info("image: scene %d generation via %s: %.2fs",
                scene_index, used.name, time.perf_counter() - t0_gen)

    if scene.media_path:
        scene.media_path.delete(save=False)

    filename = f"scene_{scene_index:02d}.png"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / filename
            tmp_path.write_bytes(data)
            t0_upload = time.perf_counter()
            storage_provider.upload(scene.media_path, tmp_path, save=False)
            logger.info("image: scene %d upload: %.2fs",
                        scene_index, time.perf_counter() - t0_upload)
    except Exception as e:
        logger.error("Failed to upload image to storage: %s", e)
        scene.preview_url = ""
        scene.media_status = MediaStatus.FAILED
        scene.save(update_fields=["preview_url", "media_status", "updated_at"])
        publish_event(
            project_id, Stage.IMAGES, Level.ERROR,
            f"Failed to upload image for scene {scene_index}: {e}",
            scene_index=scene_index,
            media_status=MediaStatus.FAILED,
        )
        raise

    scene.preview_url = ""
    scene.media_status = MediaStatus.DONE
    scene.media_provider = used.name
    scene.save(update_fields=[
        "preview_url", "media_path", "media_status", "media_provider", "updated_at"
    ])
    publish_event(
        project_id, Stage.IMAGES, Level.INFO,
        f"Scene {scene_index} image done via {used.name}",
        scene_index=scene_index,
        media_status=MediaStatus.DONE,
    )
    return scene.media_path.name
```

- [ ] **Step 3: Verify imports are fine**

```bash
python -c "from apps.projects.utils import generate_scene; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pipeline/images/__init__.py backend/apps/projects/utils.py
git commit -m "feat: fire preview_url callback in generate_scene before S3 upload"
```

---

### Task 5: Subscribe to SSE in generating-view and update scene preview

**Files:**
- Modify: `webapp/components/project/generating-view.tsx` — add `EventSource` subscription that updates `preview_url` on scenes in local state

**Interfaces:**
- Consumes: SSE events from `/api/projects/{id}/events/` with payload `{ scene_index: number, preview_url: string, media_status: string }` (from Task 4); existing `scenes` state `Scene[]`
- Produces: `scenes` state updated with `preview_url` immediately when SSE fires; existing 3s poll continues as fallback

- [ ] **Step 1: Add EventSource subscription to `generating-view.tsx`**

In `webapp/components/project/generating-view.tsx`, add a second `useEffect` for SSE after the existing polling `useEffect`. The complete addition (insert after the existing `useEffect` for polling, before the log-scroll `useEffect`):

```tsx
useEffect(() => {
  const es = new EventSource(`/api/projects/${project.id}/events/`)

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.scene_index != null && data.preview_url) {
        setScenes(prev =>
          prev.map(s =>
            s.index === data.scene_index
              ? { ...s, preview_url: data.preview_url }
              : s
          )
        )
      }
      if (data.project_status === 'DONE' || data.project_status === 'FAILED') {
        es.close()
      }
    } catch {
      // ignore malformed events
    }
  }

  es.onerror = () => {
    es.close()
  }

  return () => {
    es.close()
  }
}, [project.id])
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/webapp
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add webapp/components/project/generating-view.tsx
git commit -m "feat: subscribe to SSE in generating-view to update scene preview_url in real time"
```

---

### Task 6: Show preview image in SceneGrid during RUNNING state

**Files:**
- Modify: `webapp/components/project/scene-grid.tsx` — use `preview_url` when `media_status === 'RUNNING'` and `media_path` is empty

**Interfaces:**
- Consumes: `Scene.preview_url: string` (Task 2, Task 5); existing `Scene.media_path`, `Scene.media_status`
- Produces: image shown as soon as `preview_url` arrives (RUNNING), replaced by `media_path` when DONE

- [ ] **Step 1: Update image display logic in `scene-grid.tsx`**

In `webapp/components/project/scene-grid.tsx`, find the image block (around line 26–35):

```tsx
{scene.media_path && (scene.media_status === 'DONE' || scene.media_status === 'RUNNING') ? (
  scene.media_path.split('?')[0].endsWith('.mp4') ? (
    <video ... />
  ) : (
    <img src={scene.media_path} ... />
  )
) : null}
```

Replace with:

```tsx
{(() => {
  const displaySrc =
    scene.media_status === 'DONE'
      ? scene.media_path || null
      : scene.preview_url || null

  if (!displaySrc) return null

  return displaySrc.split('?')[0].endsWith('.mp4') ? (
    <video
      src={displaySrc}
      playsInline
      className="w-full h-full object-cover absolute inset-0"
    />
  ) : (
    <img
      src={displaySrc}
      alt={`Scene ${scene.index + 1}`}
      className="w-full h-full object-cover absolute inset-0"
    />
  )
})()}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos/webapp
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Run Django tests to catch any backend regressions**

```bash
cd /Users/ali.tariq/PycharmProjects/generative-ai-vdos
source .venv/bin/activate
python backend/manage.py test apps
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add webapp/components/project/scene-grid.tsx
git commit -m "feat: show preview_url image in scene grid during RUNNING state"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `preview_url` CharField on Scene | Task 1 |
| Migration | Task 1 |
| `SceneSerializer` exposes `preview_url` | Task 2 |
| `project-types.ts` adds `preview_url: string` | Task 2 |
| `on_preview_url` callback param in `generate_scene_image` | Task 4 |
| Callback threads to `QwenImageProvider._post_inner` | Task 3 |
| Callback called before download in `_post_inner` | Task 3 |
| Callback errors don't crash generation | Task 3 (try/except) |
| Other providers accept + ignore param | Task 3 |
| `generate_scene` defines `_on_preview` callback | Task 4 |
| `preview_url` cleared on S3 upload success | Task 4 |
| `preview_url` cleared on upload failure | Task 4 |
| Frontend SSE subscription | Task 5 |
| Scene state updated on `preview_url` event | Task 5 |
| SSE closed on DONE/FAILED | Task 5 |
| Poll continues as fallback | Task 5 (unchanged poll) |
| `SceneGrid` shows `preview_url` during RUNNING | Task 6 |
| DONE state shows `media_path` | Task 6 |
| CLI pipeline unchanged | Not touched — `generate_images` in `__init__.py` not modified |

All spec requirements covered.

**Placeholder scan:** No TBDs, no vague steps, all code blocks complete.

**Type consistency:**
- `preview_url` — string in all layers: CharField (Django), serializer field, TypeScript `string`, SSE payload key `"preview_url"`
- `on_preview_url` — `Callable[[str], None] | None` in Python; keyword-only with `None` default throughout
- `scene_index` — `int` in Python, `number` in TypeScript SSE handler
