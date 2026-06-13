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
- Review/edit the plan in the browser, then approve.
- Generate assets (images → voiceover → FFmpeg assembly) with live progress.
- Watch/download the finished `final.mp4`.
- Regenerate a single scene's image.
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

---

## 5. API

DRF, JSON, no auth. Base path `/api/`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/projects/` | Create a project from `{prompt, image_backend?, animate?, voice?}`; enqueues the plan task → `PLANNING`. |
| `GET`  | `/api/projects/` | List projects (id, title, status, created_at). |
| `GET`  | `/api/projects/{id}/` | Detail: project + scenes + recent JobLog. |
| `PATCH`| `/api/projects/{id}/` | Edit `shot_plan` (allowed only while `REVIEW`). |
| `DELETE`| `/api/projects/{id}/` | Delete row + `output/<id>/` folder. |
| `POST` | `/api/projects/{id}/approve/` | Approve the plan; enqueues the assets pipeline → `GENERATING`. |
| `POST` | `/api/projects/{id}/scenes/{index}/regenerate/` | Re-run one scene's image. |
| `GET`  | `/api/projects/{id}/events/` | **SSE** stream of progress events. |
| `GET`  | `/api/projects/{id}/download/` | Serve `output/<id>/final.mp4`. |

The review gate (`approve`) is the web equivalent of the CLI's plan→images review
gate. Generation never starts until the operator approves, matching the
review-first preference. (gpt-image-1 is never selected unless explicitly chosen;
Qwen free default — same money rules as the CLI.)

---

## 6. Celery tasks

Each task wraps an existing pipeline function and publishes progress.

| Task | Wraps | Emits |
|------|-------|-------|
| `run_plan_stage(project_id)` | `script_agent` (plan + auto-polish + consistency review) | `PLANNING` log lines; saves `shot_plan`; → `REVIEW`. |
| `run_image_stage(project_id, scene_index)` | `pipeline.images.get_provider(...).generate(...)` | per-scene status; honors character refs / negatives via `ShotPlan.expand()`. |
| `run_voice_stage(project_id)` | `pipeline.voiceover` | edge-tts per scene + word timings. |
| `run_assemble_stage(project_id)` | `pipeline.assemble` | FFmpeg assembly → `final.mp4`; → `DONE`. |

**Assets pipeline** (on approve): a Celery **chord** —
`group(run_image_stage for each scene) | run_voice_stage | run_assemble_stage`.
Images fan out in parallel; voice and assembly run once all images land.
(Animation, if enabled, inserts a capped video stage between images and voice — §7.)

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
   - **REVIEW:** editable view of the shot plan (title, scenes, characters,
     negatives) with Approve / Edit / Delete. Per-scene image thumbnails once
     generated, each with a Regenerate button.
   - **GENERATING:** live progress log (SSE) + per-scene status.
   - **DONE:** embedded `<video>` + Download button.
   - **FAILED:** the error + a Retry affordance.

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
