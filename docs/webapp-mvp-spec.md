# Web App — Lean MVP Spec

A thin web UI over the existing CLI pipeline. **Multi-user (AWS Cognito auth),
local media, no billing.** The goal is to drive the same prompt → plan → review →
generate flow from a browser instead of the terminal, with live progress — with each
user seeing only their own projects.

This supersedes `webapp-spec.md` (the full SaaS vision: Next.js, S3/CloudFront, RDS,
Stripe) **for what we build first**. That doc stays as the north star / upgrade path;
everything deferred here is captured in §10.

> **Decision log:** auth was initially out of scope ("single-user, no auth"), then
> changed to **multi-user accounts via AWS Cognito**. Media still lives on local disk
> (S3 deferred); billing still deferred.

---

## 1. Scope

**In:**
- **Sign up / log in via AWS Cognito** (email+password and Google); each user sees and
  manages only their own projects.
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
- No billing/Stripe/quotas.
- No media in the cloud — `final.mp4`, images, audio stay on **local disk** (S3/CloudFront
  deferred). Auth is the one cloud dependency (AWS Cognito).
- No Next.js/React build step — server-rendered Django templates + vanilla JS.
- Animation stays **off by default** (spends DashScope credit; opt-in only — see §7).

**Success criteria:** from a clean checkout (plus a configured Cognito user pool), a
developer can run three processes (Redis, Celery worker, Django), sign in, and produce
the same `output/<owner>/<id>/final.mp4` the CLI produces — driven entirely from the browser,
with progress streamed live, isolated to the signed-in user.

---

## 2. Stack

| Layer        | Choice                                  | Notes |
|--------------|-----------------------------------------|-------|
| Language     | **Python 3.10+** (3.12 available locally) | Django 5.2 needs ≥3.10. The `pipeline/` package itself stays 3.9-compatible. |
| Web          | **Django 5.2** + **Django REST Framework** | Server-rendered templates for pages; DRF for the JSON API the JS calls. |
| Auth         | **AWS Cognito** user pool               | Hosted UI / OAuth2; Django validates Cognito JWTs (JWKS). See §4a. |
| Async jobs   | **Celery 5.4** + **Redis**              | Redis is broker + result backend + SSE pub/sub. |
| DB           | **SQLite**                              | Single file, zero setup. Holds projects + a thin user-profile row keyed by Cognito `sub`. |
| Frontend     | Django templates + vanilla JS (`fetch` + `EventSource`) | No npm, no bundler. |
| Media        | Local filesystem, served by Django (dev) | Reuses the pipeline's `output/<owner>/<id>/` layout. |
| System dep   | `ffmpeg-full` (libass), edge-tts        | Same as the CLI today. |

**Dependencies** (a `requirements-web.txt`, created when we build — not now):
`Django>=5.2,<5.3`, `djangorestframework>=3.15`, `celery>=5.4`, `redis>=5.0`,
`python-jose[cryptography]` (verify Cognito JWTs) or `mozilla-django-oidc`,
plus the existing `pipeline/` requirements.

Runs in a separate **Python 3.12 venv** (`.venv-web`) so the repo's 3.9 `.venv`
(used by the CLI) is untouched.

---

## 3. Architecture

```
                  AWS Cognito (user pool, Hosted UI)
                        ▲ OAuth code ▼ JWT
Browser ──fetch──▶ Django (DRF views) ──enqueue──▶ Redis ──▶ Celery worker
   ▲                     │                                        │
   │                     │ reads/writes                           │ calls pipeline/ functions
   └──EventSource(SSE)───┤                                        ▼
        progress         └── SQLite (UserProfile/Project/   ◀── output/<owner>/<id>/ on disk
                              Scene/JobLog)                       (images, audio, final.mp4)
```

- Django process is thin: handle the Cognito OAuth callback, validate input, read/write
  the DB, enqueue Celery tasks, stream SSE, serve media (only the owner's files).
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

Four tables. Identity comes from **AWS Cognito** (§4a); we store only a thin profile.

### UserProfile
A local mirror of the Cognito identity so projects have a stable FK and we can show a
name/email without calling Cognito on every request.
| Field | Type | Notes |
|-------|------|-------|
| `id` | int (pk) | |
| `cognito_sub` | char, unique, indexed | The Cognito user's `sub` claim — the real identity. |
| `email` | char | Mirrored from the token on first login. |
| `name` | char, blank | Display name. |
| `created_at` | datetime | First login (just-in-time provisioned). |

> On first authenticated request we **get-or-create** the profile from the verified
> JWT claims. (If using `mozilla-django-oidc`, this maps onto Django's `User` instead —
> either way it's keyed by `cognito_sub`.)

### Project
| Field          | Type                        | Notes |
|----------------|-----------------------------|-------|
| `id`           | UUID (pk)                   | Also the `output/<owner>/<id>/` folder name. |
| `owner`        | FK → UserProfile, indexed   | **Every project query filters by the signed-in user.** |
| `prompt`       | text                        | The raw idea the user typed. |
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
| `image_path` | char, blank | Relative to `output/<owner>/<id>/` (e.g. `images/scene_03.png`). |
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
│ UserProfile                │  ← mirror of the AWS Cognito identity
│  id            int  (pk)   │
│  cognito_sub   char uniq   │
│  email / name  char        │
└────────────┬───────────────┘
             │ 1
             │ N  (owner)
┌────────────┴───────────────┐
│ Project                    │
│  id            uuid  (pk)  │
│  owner         fk →profile │  ← every query filtered by signed-in user
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

## 4a. Authentication (AWS Cognito)

Identity is fully delegated to a **Cognito user pool** — Django never stores passwords.

**Flow (Authorization Code + Hosted UI, recommended):**
1. Unauthenticated request → redirect to the Cognito **Hosted UI** (`/login`) for the
   app client. Sign-up, email verification, password reset, and Google sign-in (a
   Cognito social IdP) are all handled there — *those screens are Cognito's*, so the
   mockup's login/signup pages are illustrative of the experience, not custom code.
2. Cognito redirects back to `/auth/callback?code=…`; Django exchanges the code for
   **ID + access + refresh tokens**.
3. Django stores the session (signed cookie) and **get-or-creates** the `UserProfile`
   from the verified ID-token claims (`sub`, `email`, `name`).
4. API calls are authorized by the session; DRF resolves `request.user` →
   `UserProfile`. Tokens are verified against the pool's **JWKS** (issuer + audience +
   expiry checked).

**Config (env, never committed):** `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`,
`COGNITO_APP_CLIENT_SECRET`, `COGNITO_DOMAIN`, `COGNITO_REGION`, `OAUTH_REDIRECT_URI`.

**Endpoints:** `GET /auth/login` (→ Hosted UI), `GET /auth/callback` (code exchange),
`POST /auth/logout` (clear session + Cognito logout URL). `mozilla-django-oidc` can
provide all three; otherwise a thin custom view + `python-jose` for verification.

**Isolation:** every `/api/projects/...` view requires auth and filters
`owner=request.user`; a project belonging to another user returns **404** (not 403, so
ids aren't enumerable). Anonymous → **401**.

> **Local dev note:** Cognito is the one cloud dependency in the MVP. A dev still needs
> a (free-tier) user pool + app client configured; everything else runs locally.

---

## 5. API

DRF, JSON. **All endpoints below require an authenticated session** (§4a) and operate
only on the caller's own projects. Base path `/api/`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/projects/` | Create a project from `{prompt, image_backend?, animate?, voice?}`; enqueues the plan task → `PLANNING`. |
| `GET`  | `/api/projects/` | List projects (id, title, status, created_at). |
| `GET`  | `/api/projects/{id}/` | Detail: project + scenes + recent JobLog. |
| `PATCH`| `/api/projects/{id}/` | Manually edit `shot_plan` (allowed only while `REVIEW`). |
| `POST` | `/api/projects/{id}/refine/` | Revise the plan via a natural-language instruction (LLM re-run); `REVIEW` only. |
| `DELETE`| `/api/projects/{id}/` | Delete row + `output/<owner>/<id>/` folder. |
| `POST` | `/api/projects/{id}/approve/` | Approve the plan; enqueues the assets pipeline → `GENERATING`. |
| `POST` | `/api/projects/{id}/scenes/{index}/regenerate/` | Re-run one scene's image. |
| `POST` | `/api/projects/{id}/regenerate-images/` | Re-run **all** scene images. |
| `POST` | `/api/projects/{id}/scenes/{index}/revoice/` | Edit one scene's narration/voice and re-run its TTS. |
| `POST` | `/api/projects/{id}/regenerate-voiceovers/` | Re-run **all** scene voiceovers. |
| `POST` | `/api/projects/{id}/reassemble/` | Re-stitch `final.mp4` from current assets (clears `stale`). |
| `GET`  | `/api/projects/{id}/events/` | **SSE** stream of progress events. |
| `GET`  | `/api/projects/{id}/download/` | Serve `output/<owner>/<id>/final.mp4`. |

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

**Errors** use DRF defaults: `401` (not signed in), `400` (validation), `404` (no such
project/scene **or not owned by the caller** — see §4a), `409` (action not allowed in
current status). Body: `{ "detail": "…" }`.

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

Pages are Django templates + vanilla JS. No framework. A persistent header shows the
signed-in user (name/email) and a **Log out** action; unauthenticated visits redirect
to the Cognito Hosted UI (§4a). A visual reference for every screen lives in
[`mockup.html`](./mockup.html) (open in a browser).

0. **Auth** — login / sign-up / email-verification are presented by **Cognito Hosted
   UI** (`mockup.html` shows the equivalent screens for handoff). After callback the
   user lands on Home.
1. **Index** (`/`): a prompt box + options (image backend, animate toggle with the
   credit warning, voice) → POST creates a project and redirects to its page. Below,
   **the signed-in user's** projects with status badges.
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
| Cognito auth, local profile mirror | Same Cognito pool + roles/quotas, API keys, org/teams. |
| SQLite | PostgreSQL / RDS. |
| Local disk `output/<owner>/<id>/` | S3 + CloudFront, presigned URLs (ACLs disabled — see `webapp-spec.md` §8). |
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

**One-time:** create a Cognito **user pool** + **app client** (allow the
authorization-code flow, callback `http://127.0.0.1:8000/auth/callback`, enable Google
IdP if wanted), then add the `COGNITO_*` values to `.env`.

```bash
python3.12 -m venv .venv-web && source .venv-web/bin/activate
pip install -r requirements-web.txt
redis-server &                       # broker + pub/sub
celery -A webapp worker -l info &    # the generation worker
python manage.py migrate
python manage.py runserver           # http://127.0.0.1:8000 → redirects to Cognito login
```

`.env` (the existing one) drives provider/flag config **and** the `COGNITO_*` settings
— never committed.

---

## 13. AI-First Execution Plan (epics → work items)

This section operationalises the spec above following Arbisoft's **ai-first-engineering**
skill: when agents generate much of the implementation, *planning quality and acceptance
criteria matter more than typing speed*. Every work item below therefore carries an
explicit **contract**, **measurable acceptance criteria**, **tests & edge cases**, and a
**review focus** — so "done" is verifiable and review targets system behaviour, not style.

**Global Definition of Ready (DoR)** — a ticket may start only when it has: a contract
(interface in/out), acceptance criteria, named test cases, and its `.env`/config inputs
listed. **Definition of Done (DoD)** — code + passing tests (incl. the edge cases named),
the acceptance criteria demonstrably met, no secrets added (pre-commit hook green), and a
review against the stated focus. Style is delegated to automation (formatter/linter), not
review.

Epics map 1:1 to the Plane modules in *Arbisoft Open Source Projects*:

| Epic (Plane module) | Lead | Spec refs |
|---------------------|------|-----------|
| **A. Authentication & Signup (Backend)** | Zahid | §2, §3, §4, §4a, §6 |
| **B. Web Application (Front-end)** | Ali Tariq | §5, §8, §9 |
| **C. Video Generation Pipeline** | Laraib | §5, §6, §7 |

Cross-cutting items (data models, async infra) sit in Epic A as the backend foundation
the other epics build on. Jawad floats across all three.

---

### Epic A — Authentication & Signup (Backend) · *lead: Zahid*

**A1. Backend scaffolding — Django 5.2 + DRF + `.venv-web`**
- **Contract:** A `webapp/` Django 5.2 project + DRF installed in a Python 3.12 `.venv-web`;
  `requirements-web.txt` pins `Django>=5.2,<5.3`, `djangorestframework>=3.15`. The CLI's
  3.9 `.venv` and `pipeline/` are untouched.
- **Acceptance criteria:** `python manage.py check` passes; `runserver` boots; `pipeline/`
  imports unchanged; CLI still runs from its own venv.
- **Tests & edge cases:** smoke test imports `pipeline.schema` from the web venv; CI asserts
  two venvs don't share deps; missing `.env` → clear startup error, not a stack trace.
- **Review focus:** dependency isolation, no accidental coupling into `pipeline/`.

**A2. Data models — UserProfile / Project / Scene / JobLog (§4)**
- **Contract:** Four models exactly per §4, with the `Project.status` enum
  `DRAFT→PLANNING→REVIEW→GENERATING→DONE (·→FAILED)` and `owner` FK indexed.
- **Acceptance criteria:** migrations apply on a clean SQLite file; `Project.shot_plan` is
  the single source of truth (no scene content duplicated in `Scene`); `Scene` rows hold
  image state only.
- **Tests & edge cases:** state-transition table (§4) enforced (illegal transition raises);
  deleting a Project cascades `Scene`/`JobLog`; `stale` defaults False.
- **Review focus:** data integrity, single-source-of-truth invariant (D1), index on `owner`.

**A3. AWS Cognito Hosted-UI OAuth (§4a)**
- **Contract:** `GET /auth/login` → Hosted UI; `GET /auth/callback?code=…` exchanges code for
  ID+access+refresh tokens; `POST /auth/logout` clears session + Cognito logout. Config from
  `COGNITO_*` env only.
- **Acceptance criteria:** a configured pool lets a user sign up (incl. Google IdP) and land
  on Home with a session cookie; Django stores **no** passwords.
- **Tests & edge cases:** invalid/expired `code` → 401; state/CSRF param verified; refresh
  flow on expired access token; missing `COGNITO_*` → explicit config error.
- **Review focus:** security assumptions — token exchange, session fixation, secrets only in `.env`.

**A4. JWT (JWKS) verification + just-in-time UserProfile (§4a)**
- **Contract:** Every authed request verifies the Cognito JWT against the pool's JWKS
  (issuer + audience + expiry); DRF resolves `request.user` → get-or-create `UserProfile`
  keyed by `cognito_sub`.
- **Acceptance criteria:** first login provisions a profile from verified claims; subsequent
  logins reuse it; tampered/expired tokens rejected.
- **Tests & edge cases:** wrong `aud`/`iss` → 401; expired token → 401; JWKS key rotation
  handled (refetch); duplicate concurrent first-login is idempotent (one profile).
- **Review focus:** correctness of signature/claim verification; no trust of unverified claims.

**A5. Per-user isolation (§4a)**
- **Contract:** Every `/api/projects/...` view filters `owner=request.user`; a foreign or
  missing id returns **404** (not 403, ids non-enumerable); anonymous → **401**.
- **Acceptance criteria:** user B cannot read, mutate, or download user A's project or media;
  media serving also enforces ownership.
- **Tests & edge cases:** cross-user GET/PATCH/DELETE/download all 404; anonymous → 401;
  direct media path traversal blocked.
- **Review focus:** authorization on **every** path incl. SSE + media; behavioral regression
  tests for isolation.

**A6. Celery + Redis async infrastructure (§6)**
- **Contract:** Celery 5.4 + Redis as broker/result/pub-sub; tasks `run_plan_stage`,
  `run_refine_stage`, `run_image_stage`, `run_voice_stage`, `run_assemble_stage` wrap the
  existing `pipeline/` functions as a library (no shelling out).
- **Acceptance criteria:** approve enqueues the chord
  `group(images) | voice | assemble`; each task publishes progress to `project:{id}:events`
  and persists `JobLog`.
- **Tests & edge cases:** any task raising sets `status=FAILED` + error JobLog + terminal SSE
  event; worker restart mid-job leaves consistent state; Qwen rate-limit lowers concurrency
  (D4), no backpressure code.
- **Review focus:** error handling, deployment safety, the FAILED-path contract.

---

### Epic B — Web Application (Front-end) · *lead: Ali Tariq*

**B1. App shell + auth-gated layout (§9)**
- **Contract:** Server-rendered base template + vanilla JS; persistent header shows the
  signed-in user + Log out; unauthenticated visits redirect to Cognito Hosted UI. No npm/bundler.
- **Acceptance criteria:** matches `mockup.html`; anon → redirect; signed-in → Home with
  identity shown.
- **Tests & edge cases:** expired session mid-navigation → redirect, not a 500; logout clears
  session + Cognito.
- **Review focus:** auth gating on every page; no client-side secret exposure.

**B2. Index — submit idea + project list (§5 `POST/GET /api/projects/`, §9.1)**
- **Contract:** Prompt box + options (image backend, animate toggle **with credit warning**,
  voice) → `POST /api/projects/` → redirect to project page; below, the caller's projects with
  status badges.
- **Acceptance criteria:** only `prompt` required (rest fall back to `.env`, D3); animate is
  off by default and shows the DashScope-credit warning before enabling.
- **Tests & edge cases:** empty prompt → inline validation (no request); list shows only the
  user's projects; gpt-image-1 never preselected.
- **Review focus:** money rules surfaced in UI (animate/gpt-image-1), correct default fallbacks.

**B3. Plan review + revise UI (§5 `PATCH`/`refine`, §9.2 REVIEW)**
- **Contract:** REVIEW screen offers both paths — a **Refine** box → `POST /refine/` (LLM) and
  inline **manual edit** → `PATCH /shot_plan` — plus Approve / Delete.
- **Acceptance criteria:** refine shows a spinner during `PLANNING` and updates the plan via
  SSE; manual edits persist; editing outside REVIEW → 409 surfaced to the user.
- **Tests & edge cases:** concurrent refine + manual edit resolves to one source of truth;
  approve disabled until a plan exists; 409 handled gracefully.
- **Review focus:** the review gate is enforced (no generation pre-approve); single-source plan.

**B4. Generation screen + live progress via SSE (§8, §9.2 GENERATING)**
- **Contract:** Subscribe to `GET /api/projects/{id}/events/` with `EventSource`; render the
  log live and fill the image gallery as each scene lands (PENDING→RUNNING→DONE).
- **Acceptance criteria:** ≥1 event per stage rendered; on (re)connect the client replays
  current status + recent JobLog then tails; stream closes on terminal status.
- **Tests & edge cases:** late-joiner/refresh shows correct state (replay); reconnect after
  drop loses no terminal event; FAILED renders error + retry.
- **Review focus:** reconnect/replay correctness; no busy-polling fallback.

**B5. Asset editing panels — images / voiceover / video (§5 regenerate*/revoice/reassemble, §9.2 DONE)**
- **Contract:** Three edit-then-regenerate panels: image grid (per-image **Regenerate** +
  **Regenerate all**), per-scene narration/voice (**Re-voice** + **Regenerate all voiceovers**),
  and `<video>` + Download + **Rebuild video** (highlighted when `stale`).
- **Acceptance criteria:** regenerating an image/voiceover sets `stale=true` and the Rebuild
  button highlights; `reassemble/` clears `stale`; iterating never re-runs the LLM.
- **Tests & edge cases:** force gpt-image-1 on a single scene works and is explicit-only;
  stale indicator accurate after partial regen; failed tile shows inline error + retry.
- **Review focus:** stale/`final.mp4` consistency; money rules (explicit paid backend) in UI.

---

### Epic C — Video Generation Pipeline · *lead: Laraib*

> The engine already exists in `pipeline/`. These items wrap/verify it behind the web tasks
> (§6) and the spec's API — *reuse, don't rewrite* (§3). Each item's contract is the Celery
> task + the `pipeline/` function it wraps.

**C1. Plan stage — `run_plan_stage` (§6)**
- **Contract:** Wraps `script_agent` (plan + **auto-polish + consistency review**, run
  automatically); saves `shot_plan`; `PLANNING → REVIEW`.
- **Acceptance criteria:** a prompt yields a valid `ShotPlan` (schema.py); polish + review run
  without manual flags; subscribe/CTA scenes only for listicle-style (story videos end on the
  final beat).
- **Tests & edge cases:** LLM/JSON-shape failure → FAILED + error log; character looks never
  inlined per scene (consistency enforced by code, not the LLM).
- **Review focus:** schema-contract conformance; existing consistency invariants preserved.

**C2. Refine stage — `run_refine_stage` (§5 refine, §6)**
- **Contract:** Wraps `script_agent.revise_shot_plan(plan, instruction)` (+ re-run
  polish/review); REVIEW-only; saves revised `shot_plan`, back to REVIEW.
- **Acceptance criteria:** a natural-language instruction measurably changes the plan; polish +
  review re-run as for a fresh plan.
- **Tests & edge cases:** refine outside REVIEW → 409; empty/garbage instruction → no
  destructive change; idempotent re-runs.
- **Review focus:** plan integrity across edits; no character-consistency regressions.

**C3. Image stage — `run_image_stage` (§6, money rules)**
- **Contract:** Wraps `images.get_provider(...).generate(...)` per scene; honors character
  refs/negatives via `ShotPlan.expand()`; provider order Qwen(free)→Flux→Pexels→placeholder,
  **gpt-image-1 only on explicit opt-in**.
- **Acceptance criteria:** per-scene status streamed; fallback chain ends at placeholder;
  `global_negative` + `Character.negative` merged into every scene.
- **Tests & edge cases:** Qwen rate-limit falls back, not crashes; gpt-image-1 never
  auto-selected; negatives respected (no drawn "negated" traits).
- **Review focus:** money rules (no surprise paid calls); character-consistency code path.

**C4. Voiceover stage — `run_voice_stage` (§6)**
- **Contract:** Wraps `pipeline.voiceover` (edge-tts, `boundary="WordBoundary"`); one scene
  when `scene_index` set, else all; emits mp3 + `.words.json`.
- **Acceptance criteria:** word-timing JSON present for captions; re-voice updates
  `shot_plan` + that scene's audio only and sets `stale=true`.
- **Tests & edge cases:** missing word timings → caught (captions depend on them); voice
  override applies; all-vs-single scope correct.
- **Review focus:** caption-timing contract; stale propagation.

**C5. Assembly stage — `run_assemble_stage` + download (§5 download/reassemble, §6)**
- **Contract:** Wraps `pipeline.assemble` (FFmpeg, absolute `.resolve()` paths,
  `ffmpeg-full`); scene durations **measured from the mp3s**, never the plan; clears `stale`;
  `GENERATING → DONE`. `GET /download/` serves the owner's `final.mp4`.
- **Acceptance criteria:** `final.mp4` matches what the CLI produces from the same inputs;
  `reassemble/` refreshes the video and clears `stale`.
- **Tests & edge cases:** missing libass/`ffmpeg-full` → actionable error; download enforces
  ownership (404 otherwise); durations come from audio.
- **Review focus:** the duration invariant; deployment dep (`ffmpeg-full`); media authz.

**C6. Animation stage (opt-in, money-gated) — `run_video_stage` (§7)**
- **Contract:** Only when `animate=true`; inserts between images and voice; capped at
  `MAX_ANIMATED_SCENES` (2) by the existing `ShotPlan` validator; Wan constants stay hardcoded
  in `pipeline/video/wan.py`.
- **Acceptance criteria:** off by default; the web layer never raises the cap; UI credit
  warning shown before enabling.
- **Tests & edge cases:** cap enforced (3rd scene rejected); animation disabled path is the
  default; never enabled implicitly.
- **Review focus:** money rules (DashScope credit) — the highest-risk item; explicit opt-in only.
