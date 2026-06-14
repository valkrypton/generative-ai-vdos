# Web App — Lean Local MVP Spec

A thin web UI over the existing CLI pipeline. **Single-user, local-only.** No auth,
no billing, no cloud. The goal is to drive the same prompt → plan → review → generate
flow from a browser instead of the terminal, with live progress.

This supersedes `webapp-spec.md` (the full multi-tenant SaaS vision) **for what we
build first**. That doc stays as the north star / upgrade path; everything deferred
here is captured in §10.

---

## 1. Scope

**In:**
- Submit an idea → get a shot plan (auto-polish + consistency review run automatically, same as the CLI).
- Review the plan in the browser and revise it **two ways**: (a) edit the plan fields
  directly, or (b) type a natural-language **refine instruction** ("make the mom
  younger", "add a scene at the harbor") that re-runs the LLM — the CLI's
  `refine --change`. Then approve.
- Generate assets (images → voiceover → FFmpeg assembly) with live progress.
- See **all scene images** in a gallery; **regenerate any single image, or all of
  them**, without redoing the rest of the pipeline.
- Watch/download the finished `final.mp4`.
- List past projects; open any to review or re-download.

**Out (for the MVP):**
- No users, login, accounts, or permissions — one local operator.
- No billing/Stripe/quotas.
- No cloud (AWS/S3/CloudFront/RDS). Files live on local disk.
- No Next.js/React build step — server-rendered Django templates + vanilla JS.
- Animation stays **off by default** (spends DashScope credit; opt-in only — see §7).

**Success criteria:** from a clean checkout, a developer can run three processes
(Redis, Celery worker, Django) and produce the same `output/<id>/final.mp4` the CLI
produces — driven entirely from the browser, with progress streamed live.

---

## 2. Stack

| Layer        | Choice                                  | Notes |
|--------------|-----------------------------------------|-------|
| Language     | **Python 3.10+** (3.12 available locally) | Django 5.2 needs ≥3.10. The `pipeline/` package itself stays 3.9-compatible. |
| Web          | **Django 5.2** + **Django REST Framework** | Server-rendered templates for pages; DRF for the JSON API the JS calls. |
| Async jobs   | **Celery 5.4** + **Redis**              | Redis is broker + result backend + SSE pub/sub. |
| DB           | **SQLite**                              | Single file, zero setup. Fine for one operator. |
| Frontend     | Django templates + vanilla JS (`fetch` + `EventSource`) | No npm, no bundler. |
| Media        | Local filesystem, served by Django (dev) | Reuses the pipeline's `output/<id>/` layout. |
| System dep   | `ffmpeg-full` (libass), edge-tts        | Same as the CLI today. |

**Dependencies** (a `requirements-web.txt`, created when we build — not now):
`Django>=5.2,<5.3`, `djangorestframework>=3.15`, `celery>=5.4`, `redis>=5.0`,
plus the existing `pipeline/` requirements.

Runs in a separate **Python 3.12 venv** (`.venv-web`) so the repo's 3.9 `.venv`
(used by the CLI) is untouched.

---

## 3. Architecture

```
Browser ──fetch──▶ Django (DRF views) ──enqueue──▶ Redis ──▶ Celery worker
   ▲                     │                                        │
   │                     │ reads/writes                           │ calls pipeline/ functions
   └──EventSource(SSE)───┤                                        ▼
        progress         └── SQLite (Project/Scene/JobLog) ◀── output/<id>/ on disk
                                                                  (images, audio, final.mp4)
```

- Django process is thin: validate input, read/write the DB, enqueue Celery tasks,
  stream SSE, serve media.
- The **Celery worker** does all the heavy lifting by calling the existing
  `pipeline/` modules as a **library** — no shelling out to `python -m pipeline.*`.
- Progress flows worker → Redis pub/sub channel → Django SSE endpoint → browser, and
  is also persisted to `JobLog` so a late-joining client can replay state.

**Reuse, don't rewrite:** the worker imports `pipeline.script_agent`, `pipeline.images`,
`pipeline.voiceover`, `pipeline.assemble`, `pipeline.schema`. The web layer adds
orchestration + persistence around them; the generation logic is unchanged. Provider
selection uses the **existing `.env` flags** we just built (`LLM_PROVIDER`,
`IMAGE_BACKEND`, etc.) — explicit, no auto-detect.

---

## 4. Data models

No `User`. Three tables.

### Project
| Field          | Type                        | Notes |
|----------------|-----------------------------|-------|
| `id`           | UUID (pk)                   | Also the `output/<id>/` folder name. |
| `prompt`       | text                        | The raw idea the operator typed. |
| `title`        | char, blank                 | Filled from the plan once generated. |
| `status`       | char (enum, see below)      | |
| `shot_plan`    | JSON, null                  | The full `ShotPlan` dict; editable during REVIEW. |
| `image_backend`| char                        | Snapshot of the chosen backend (default from `.env`). |
| `animate`      | bool, default False         | Opt-in; capped by `MAX_ANIMATED_SCENES`. |
| `narrator_voice`| char, blank                | edge-tts voice; default from `.env`. |
| `music`        | char, blank                 | Optional music file/mood. |
| `error`        | text, blank                 | Last failure message if `status=FAILED`. |
| `stale`        | bool, default False         | An image/voiceover changed since the last assemble — `final.mp4` is out of date until `reassemble/`. |
| `created_at` / `updated_at` | datetime       | |

### Scene
**Generation state only.** The plan content (narration, image_prompt, characters,
negatives) lives in `Project.shot_plan` — the single editable source of truth. A
Scene row exists per scene purely to track its image artifact, keyed by `index` into
the plan. This avoids a dual source of truth between the JSON and the rows.
| Field | Type | Notes |
|-------|------|-------|
| `project` | FK → Project | |
| `index` | int | Index into `shot_plan["scenes"]`; the scene's order. |
| `image_path` | char, blank | Relative to `output/<id>/` (e.g. `images/scene_03.png`). |
| `image_status` | char (enum: PENDING/RUNNING/DONE/FAILED) | |
| `image_provider` | char, blank | Backend that actually produced it (the fallback chain may differ from the request). |

> Rows are (re)created from `shot_plan` on **approve**, once the plan is final. Editing
> the plan during REVIEW touches only the JSON; no Scene rows exist yet (D1, §11).

### JobLog
| Field | Type | Notes |
|-------|------|-------|
| `project` | FK → Project | |
| `stage` | char | plan / images / voice / assemble. |
| `level` | char | info / warn / error. |
| `message` | text | Human-readable progress line. |
| `created_at` | datetime | |

**Project status enum:** `DRAFT → PLANNING → REVIEW → GENERATING → DONE`, with
`FAILED` reachable from `PLANNING` or `GENERATING`.

### ERD

```
┌────────────────────────────┐
│ Project                    │
│  id            uuid  (pk)  │
│  prompt        text        │
│  title         char        │
│  status        enum        │──── DRAFT→PLANNING→REVIEW→GENERATING→DONE  (·→FAILED)
│  shot_plan     json  (null)│         ← single source of truth for plan content
│  image_backend char        │
│  animate       bool        │
│  narrator_voice char       │
│  music         char        │
│  error         text        │
│  stale         bool        │         ← final.mp4 out of date vs current assets
│  created_at    datetime    │
│  updated_at    datetime    │
└────────────┬───────────────┘
             │ 1
       ┌─────┴───────┐
       │ N           │ N
┌──────┴──────────┐ ┌┴───────────────────┐
│ Scene           │ │ JobLog             │
│  project  fk    │ │  project  fk       │
│  index    int   │ │  stage    char     │
│  image_path     │ │  level    char     │
│  image_status   │ │  message  text     │
│  image_provider │ │  created_at        │
└─────────────────┘ └────────────────────┘
  image state only,    append-only progress
  index → shot_plan      (also replayed on
  ["scenes"][index]       SSE reconnect)
```

State transitions (who triggers them):

| From | Event | To |
|------|-------|----|
| — | `POST /projects/` | `PLANNING` |
| `PLANNING` | `run_plan_stage` succeeds | `REVIEW` |
| `PLANNING` | `run_plan_stage` raises | `FAILED` |
| `REVIEW` | `PATCH` (edit plan) | `REVIEW` (no transition) |
| `REVIEW` | `POST /approve/` | `GENERATING` |
| `GENERATING` | assemble chord completes | `DONE` |
| `GENERATING` | any stage raises | `FAILED` |
| `FAILED` | `POST /approve/` (retry) | `GENERATING` |

---

## 5. API

DRF, JSON, no auth. Base path `/api/`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/projects/` | Create a project from `{prompt, image_backend?, animate?, voice?}`; enqueues the plan task → `PLANNING`. |
| `GET`  | `/api/projects/` | List projects (id, title, status, created_at). |
| `GET`  | `/api/projects/{id}/` | Detail: project + scenes + recent JobLog. |
| `PATCH`| `/api/projects/{id}/` | Manually edit `shot_plan` (allowed only while `REVIEW`). |
| `POST` | `/api/projects/{id}/refine/` | Revise the plan via a natural-language instruction (LLM re-run); `REVIEW` only. |
| `DELETE`| `/api/projects/{id}/` | Delete row + `output/<id>/` folder. |
| `POST` | `/api/projects/{id}/approve/` | Approve the plan; enqueues the assets pipeline → `GENERATING`. |
| `POST` | `/api/projects/{id}/scenes/{index}/regenerate/` | Re-run one scene's image. |
| `POST` | `/api/projects/{id}/regenerate-images/` | Re-run **all** scene images. |
| `POST` | `/api/projects/{id}/scenes/{index}/revoice/` | Edit one scene's narration/voice and re-run its TTS. |
| `POST` | `/api/projects/{id}/regenerate-voiceovers/` | Re-run **all** scene voiceovers. |
| `POST` | `/api/projects/{id}/reassemble/` | Re-stitch `final.mp4` from current assets (clears `stale`). |
| `GET`  | `/api/projects/{id}/events/` | **SSE** stream of progress events. |
| `GET`  | `/api/projects/{id}/download/` | Serve `output/<id>/final.mp4`. |

The review gate (`approve`) is the web equivalent of the CLI's plan→images review
gate. Generation never starts until the operator approves, matching the
review-first preference. (gpt-image-1 is never selected unless explicitly chosen;
Qwen free default — same money rules as the CLI.)

### Request / response shapes

**`POST /api/projects/`** — create + queue planning. Only `prompt` is required; the
rest fall back to the `.env` flags (D3).
```jsonc
// request
{ "prompt": "a lonely lighthouse keeper befriends a storm petrel",
  "image_backend": "qwen",      // optional override; else IMAGE_BACKEND
  "animate": false,              // optional; spends credit if true
  "narrator_voice": "en-US-AndrewNeural", // optional
  "music": "calm" }             // optional mood
// 201 response
{ "id": "9f1c…", "status": "PLANNING", "title": "",
  "created_at": "2026-06-14T10:00:00Z" }
```

**`GET /api/projects/{id}/`** — detail (poll-free; SSE drives live updates).
```jsonc
{ "id": "9f1c…", "status": "REVIEW", "title": "The Keeper and the Petrel",
  "image_backend": "qwen", "animate": false,
  "shot_plan": { /* full ShotPlan dict — schema.py contract */ },
  "scenes": [
    { "index": 0, "image_status": "DONE",
      "image_path": "images/scene_00.png", "image_provider": "qwen-image" },
    { "index": 1, "image_status": "PENDING",
      "image_path": "", "image_provider": "" }
  ],
  "log": [ { "stage": "plan", "level": "info",
             "message": "consistency review passed",
             "created_at": "2026-06-14T10:00:42Z" } ],
  "error": "" }
```
Before approve, `scenes` is `[]` (no rows yet — D1); the plan is read from `shot_plan`.

**`PATCH /api/projects/{id}/`** — edit the plan while `REVIEW`. Body is a partial:
`{ "shot_plan": { … }, "image_backend": "openai", "animate": true }`. Editing in any
other status → `409 Conflict`. Returns the updated detail object.

**`POST /api/projects/{id}/refine/`** — revise the plan with a natural-language
instruction. Wraps `script_agent.revise_shot_plan(plan, feedback)`. `REVIEW` only
(else `409`); enqueues `run_refine_stage` → status briefly `PLANNING`, back to
`REVIEW` with the updated `shot_plan`. Auto-polish + consistency review re-run, same
as a fresh plan.
```jsonc
// request
{ "instruction": "make the lighthouse keeper older and add a scene at the harbor" }
// 202
{ "status": "PLANNING" }
```
This is the LLM path; `PATCH` is the manual path. Both edit the same `shot_plan` and
are available throughout `REVIEW`.

**`POST /api/projects/{id}/approve/`** — no body. Builds `Scene` rows from the final
plan, enqueues the assets chord, → `GENERATING`. `202` with `{ "status": "GENERATING" }`.
Calling it from `REVIEW` or `FAILED` is valid (the latter is retry); any other
status → `409`.

**`POST /api/projects/{id}/scenes/{index}/regenerate/`** — re-run one image. Optional
`{ "image_backend": "gpt-image-1" }` to force a backend for this scene only (explicit
opt-in to the paid backend). `202`; the scene's `image_status` returns to `RUNNING`
and progress streams over SSE. Allowed in `REVIEW` and `DONE`.

**`POST /api/projects/{id}/regenerate-images/`** — re-run **all** scene images at once.
Optional `{ "image_backend": "…" }` applies to every scene. Resets each scene's
`image_status` to `PENDING` and enqueues the image `group` only — voiceover is
untouched. `202`. Allowed in `DONE`/`FAILED`. Regenerating an image changes a source
asset, so it sets `stale=true`; `final.mp4` is unchanged until **`reassemble/`**.

**`POST /api/projects/{id}/scenes/{index}/revoice/`** — edit one scene's narration
and/or voice, then re-run its TTS. Updates `shot_plan["scenes"][index]` and re-runs
edge-tts for that scene only (regenerating the mp3 + word-timing json).
```jsonc
// request (both optional; omit narration to just change the voice)
{ "narration": "The keeper had not spoken to a soul in years.",
  "voice": "en-GB-RyanNeural" }
// 202
{ "status": "DONE", "stale": true }
```
Allowed in `DONE`/`FAILED`. Sets `stale=true` (scene durations come from the new
audio, so the video must be re-stitched). Editing narration *before* generation is
just a `PATCH` to the plan in `REVIEW` — no audio exists yet.

**`POST /api/projects/{id}/regenerate-voiceovers/`** — re-run **all** voiceovers.
Optional `{ "voice": "…" }` sets the narrator voice for every scene. `202`; sets
`stale=true`. Allowed in `DONE`/`FAILED`.

**`POST /api/projects/{id}/reassemble/`** — re-run only the FFmpeg assembly from the
current images + audio; refreshes `final.mp4` and clears `stale`. No body. `202`.
Allowed in `DONE`/`FAILED`.

**`GET /api/projects/{id}/events/`** — `text/event-stream`. Each event:
```
data: {"stage":"images","level":"info","message":"scene 3/12 done",
       "status":"GENERATING","scene_index":3}
```
On connect: replay current `status` + recent `JobLog`, then tail live. Client closes
on terminal `status` (`DONE`/`FAILED`).

**Errors** use DRF defaults: `400` (validation), `404` (no such project/scene),
`409` (action not allowed in current status). Body: `{ "detail": "…" }`.

---

## 6. Celery tasks

Each task wraps an existing pipeline function and publishes progress.

| Task | Wraps | Emits |
|------|-------|-------|
| `run_plan_stage(project_id)` | `script_agent` (plan + auto-polish + consistency review) | `PLANNING` log lines; saves `shot_plan`; → `REVIEW`. |
| `run_refine_stage(project_id, instruction)` | `script_agent.revise_shot_plan(plan, instruction)` (+ re-run polish/review) | saves the revised `shot_plan`; → `REVIEW`. |
| `run_image_stage(project_id, scene_index)` | `pipeline.images.get_provider(...).generate(...)` | per-scene status; honors character refs / negatives via `ShotPlan.expand()`. |
| `run_voice_stage(project_id, scene_index=None)` | `pipeline.voiceover` | edge-tts + word timings; one scene when `scene_index` is set, else all. |
| `run_assemble_stage(project_id)` | `pipeline.assemble` | FFmpeg assembly → `final.mp4`; clears `stale`; → `DONE`. |

**Assets pipeline** (on approve): a Celery **chord** —
`group(run_image_stage for each scene) | run_voice_stage | run_assemble_stage`.
Images fan out in parallel; voice and assembly run once all images land.
(Animation, if enabled, inserts a capped video stage between images and voice — §7.)

**Regenerate / revoice / reassemble** reuse these same tasks with no chord tail:
one image → a single `run_image_stage`; all images → `group(run_image_stage …)`;
one/all voiceovers → `run_voice_stage(scene_index=…)` / `run_voice_stage()`;
re-stitch → `run_assemble_stage`. Each asset-changing task sets `stale=true`;
`run_assemble_stage` clears it. Iterating on visuals or audio never re-runs the LLM,
so it's cheap; the operator rebuilds the video once when satisfied.

All tasks wrap the body in try/except: on failure set `status=FAILED`, write an
error `JobLog`, publish a terminal SSE event. Scene durations come from measuring
the voiceover mp3s in `assemble`, **never** from the plan (existing invariant).

---

## 7. Animation (opt-in, money-gated)

- `animate` defaults to **False**. Mirrors the CLI: never animate without an
  explicit choice.
- When on, a `run_video_stage` runs between images and voice, capped at
  `MAX_ANIMATED_SCENES` (2) by the existing `ShotPlan` validator — the web layer does
  **not** raise that cap.
- Wan constants (model/resolution/duration) stay hardcoded in `pipeline/video/wan.py`.
- The UI must show a clear "this spends DashScope credit" warning before enabling.

---

## 8. Progress / SSE

- Worker publishes JSON events to Redis channel `project:{id}:events`:
  `{stage, level, message, status, scene_index?}`.
- `GET /api/projects/{id}/events/` subscribes to that channel and relays as
  `text/event-stream`.
- On connect, the endpoint first replays current `status` + recent `JobLog` so a
  refresh/late join shows correct state, then tails live events.
- Browser uses `EventSource`; closes the stream on a terminal `status`
  (`DONE`/`FAILED`).

---

## 9. Frontend (server-rendered)

Two pages, Django templates + vanilla JS. No framework.

1. **Index** (`/`): a prompt box + options (image backend, animate toggle with the
   credit warning, voice) → POST creates a project and redirects to its page. Below,
   a list of past projects with status badges.
2. **Project** (`/projects/{id}/`):
   - **REVIEW** — the shot plan, revised two ways side by side, plus Approve / Delete:
     - **Refine box** — a text input + "Refine" button that POSTs an instruction to
       `/refine/` (the LLM path); spinner while `PLANNING`, updated plan via SSE.
     - **Manual edit** — inline-editable plan fields that PATCH `shot_plan` directly.
   - **GENERATING** — live progress log (SSE); the image gallery fills in as each scene
     lands (tile status PENDING → RUNNING → DONE).
   - **DONE / FAILED** — three editable panels over the generated assets, each using the
     same edit-then-regenerate pattern:
     - **Images** — grid of all scene images; per-image **Regenerate** + a
       **Regenerate all images** button.
     - **Voiceover** — per scene, the editable **narration** text and an optional voice
       override, with a **Re-voice** button; plus **Regenerate all voiceovers**. Editing
       narration here updates `shot_plan` and re-runs only that scene's TTS.
     - **Video** — embedded `<video>` + Download. A **Rebuild video** button,
       highlighted when assets are **stale** (an image or voiceover changed since the
       last assemble), re-stitches `final.mp4` from the current assets.
     Failed tiles show the error inline with a retry.

---

## 10. What's deferred (and the upgrade path to `webapp-spec.md`)

| Deferred | Becomes (full spec) |
|----------|---------------------|
| No auth / single operator | User model, sessions, API keys. |
| SQLite | PostgreSQL / RDS. |
| Local disk `output/<id>/` | S3 + CloudFront, presigned URLs. |
| Redis local | ElastiCache. |
| Django templates + vanilla JS | Next.js 14 frontend. |
| One worker on localhost | ECS services, autoscaling Celery workers. |
| No billing | Stripe, Plans, Subscriptions, quotas. |

The data models are a strict subset of the SaaS models (drop `User`/`Plan`/
`Subscription` FKs); the API paths align with `/api/v1/` so the lean endpoints can be
versioned in place later.

---

## 11. Decisions

These were open; now settled (explicit by preference — no defaults left implicit).

| # | Decision |
|---|----------|
| D1 | **Plan JSON is the single source of truth.** `Scene` rows hold image state only, (re)built from `shot_plan` on approve (§4). |
| D2 | **Progress uses SSE**, not WebSockets — one-way, simpler, no extra deps. |
| D3 | **`.env` is the source of truth for providers/credentials.** The UI overrides only per-project, and only `image_backend`, `animate`, `voice`, `music`. |
| D4 | **One Celery worker, default concurrency.** Image tasks fan out via the chord's `group`; if a free-tier backend (Qwen) rate-limits, lower worker concurrency rather than adding backpressure logic. |
| D5 | **Music: plan-driven mood first.** Reuse `music/` + its CC-BY attribution; a file picker comes later. |

---

## 12. Run (when we build it)

```bash
python3.12 -m venv .venv-web && source .venv-web/bin/activate
pip install -r requirements-web.txt
redis-server &                       # broker + pub/sub
celery -A webapp worker -l info &    # the generation worker
python manage.py migrate
python manage.py runserver           # http://127.0.0.1:8000
```

`.env` (the existing one) drives provider/flag config — never committed.
