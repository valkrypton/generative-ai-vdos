# Web Application Specification
## AI Video Pipeline — Public SaaS

**Stack:** Next.js 14 (App Router) + Django 5 + DRF + Celery + Redis + PostgreSQL + S3  
**Hosting:** AWS (ECS Fargate + RDS + ElastiCache + S3 + CloudFront)  
**Audience:** Public SaaS — anyone can sign up and create videos

---

## 1. Product Overview

A web UI that wraps the existing CLI pipeline into a step-by-step guided creator flow:

```
Enter prompt → Review shot plan → Approve → Watch generation progress → Download video
```

The existing Python pipeline code (`pipeline/`) becomes the **job worker** — Django REST 
Framework serves the API, Celery executes pipeline stages in the background, and the 
Next.js frontend shows real-time progress via Server-Sent Events.

---

## 2. User Stories

### Core (MVP)

| As a… | I want to… | So that… |
|--------|-----------|---------|
| Visitor | Sign up with email | Create my first video |
| Creator | Enter a text prompt | Get an AI-generated shot plan |
| Creator | Edit the shot plan in the browser | Fine-tune scenes before generating images |
| Creator | Approve the plan and watch images generate | See progress scene by scene |
| Creator | Preview each image and request a regeneration | Fix a bad image before assembling |
| Creator | Download the final `.mp4` | Upload to YouTube |
| Creator | See all my past videos | Manage my work |

### Post-MVP

| Feature | Priority |
|---------|----------|
| Animate scenes (Wan) — opt-in per project | High |
| Choose background music from library | High |
| Choose narrator voice | High |
| Team workspaces / sharing | Medium |
| Export shot plan as JSON for CLI re-use | Medium |
| Webhook on job completion | Low |
| API access (headless) | Low |

---

## 3. Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Frontend | Next.js 14 (App Router) | SSR + streaming + RSC; file-based routing |
| UI | shadcn/ui + Tailwind CSS | Fast, unstyled-first, accessible |
| Backend API | Django 5 + Django REST Framework | Reuses existing Python pipeline code directly |
| Auth | Django Allauth + SimpleJWT | Email/password + social (Google) |
| Background jobs | Celery 5 + Redis | Long-running pipeline stages |
| Real-time progress | SSE (Server-Sent Events) via Django | Simple; no WebSocket server needed |
| Database | PostgreSQL 16 (AWS RDS) | Relational; Celery result backend |
| File storage | AWS S3 + CloudFront CDN | Images, audio, final video served via CDN |
| Container | Docker; deployed on AWS ECS Fargate | Autoscaling; no EC2 management |
| Cache / broker | AWS ElastiCache (Redis) | Celery broker + SSE state |
| Video processing | FFmpeg on worker container | Same as CLI; worker image includes ffmpeg-full |
| CI/CD | GitHub Actions → ECR → ECS | Standard AWS deploy pipeline |

---

## 4. Data Models

### 4.1 User & Billing

```python
# users/models.py

class User(AbstractUser):
    """Extends Django's user; email is the login identifier."""
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=100, blank=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    credits_remaining = models.IntegerField(default=10)  # free tier
    created_at = models.DateTimeField(auto_now_add=True)

class Plan(models.Model):
    """Subscription plan (free / pro / team)."""
    name = models.CharField(max_length=50)       # "free", "pro", "team"
    monthly_credits = models.IntegerField()       # videos per month
    price_usd_cents = models.IntegerField()       # 0 = free
    animate_enabled = models.BooleanField()
    api_access = models.BooleanField()

class Subscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    current_period_end = models.DateTimeField(null=True)
    status = models.CharField(max_length=20)     # "active", "canceled", "past_due"
```

### 4.2 Video Project

```python
# projects/models.py

class Project(models.Model):
    """One video. Mirrors an output/<slug>/ folder in the CLI."""

    class Status(models.TextChoices):
        DRAFT      = "draft"        # shot plan being edited
        PLANNING   = "planning"     # LLM generating plan
        REVIEW     = "review"       # waiting for user approval
        GENERATING = "generating"   # images / audio / assembly running
        DONE       = "done"         # final.mp4 ready
        FAILED     = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=200, blank=True)
    prompt = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # The shot plan JSON (ShotPlan schema)
    shot_plan = models.JSONField(null=True, blank=True)

    # Output files (S3 keys)
    final_video_key = models.CharField(max_length=500, blank=True)
    final_video_url = models.URLField(blank=True)  # CloudFront CDN URL
    thumbnail_url   = models.URLField(blank=True)

    # Options chosen at creation
    image_backend  = models.CharField(max_length=50, blank=True)  # "" = auto
    animate        = models.BooleanField(default=False)
    music_key      = models.CharField(max_length=200, blank=True) # S3 key of selected track
    narrator_voice = models.CharField(max_length=100, blank=True)

    # Metadata
    scene_count    = models.IntegerField(default=0)
    duration_secs  = models.FloatField(null=True)
    credit_cost    = models.IntegerField(default=1)  # 1 base + 2 if animate

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True)

class Scene(models.Model):
    """One scene within a project. Mirrors a scene in shot_plan.scenes[]."""
    project  = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="scenes")
    index    = models.IntegerField()              # 0-based position
    narration       = models.TextField()
    image_prompt    = models.TextField()
    negative_prompt = models.TextField(blank=True)
    motion          = models.TextField(blank=True)
    voice           = models.CharField(max_length=100, blank=True)
    on_screen_text  = models.CharField(max_length=200, blank=True)

    # Generated assets (S3 keys)
    image_key   = models.CharField(max_length=500, blank=True)
    image_url   = models.URLField(blank=True)
    video_key   = models.CharField(max_length=500, blank=True)
    audio_key   = models.CharField(max_length=500, blank=True)

    class ImageStatus(models.TextChoices):
        PENDING    = "pending"
        GENERATING = "generating"
        DONE       = "done"
        FAILED     = "failed"

    image_status = models.CharField(max_length=20, choices=ImageStatus.choices,
                                    default=ImageStatus.PENDING)
    image_provider = models.CharField(max_length=50, blank=True)  # which backend was used

    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]

class JobLog(models.Model):
    """Append-only event log for a project's pipeline run (shown in progress UI)."""
    project   = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="logs")
    stage     = models.CharField(max_length=50)   # "plan", "images", "voice", "assemble"
    message   = models.TextField()
    level     = models.CharField(max_length=10, default="info")  # "info", "error", "warn"
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 5. API Endpoints

All endpoints are under `/api/v1/`. Auth: Bearer JWT (`Authorization: Bearer <token>`).

### 5.1 Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register/` | Email + password signup |
| `POST` | `/auth/login/` | Returns `{access, refresh}` JWT pair |
| `POST` | `/auth/refresh/` | Refresh access token |
| `GET`  | `/auth/me/` | Current user + credit balance |

### 5.2 Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/projects/` | List user's projects (paginated) |
| `POST`   | `/projects/` | Create project + queue plan generation |
| `GET`    | `/projects/{id}/` | Project detail + scenes + status |
| `PATCH`  | `/projects/{id}/` | Edit shot_plan JSON (while in REVIEW) |
| `DELETE` | `/projects/{id}/` | Soft-delete |
| `POST`   | `/projects/{id}/approve/` | Approve plan → queue image/voice/assemble jobs |
| `POST`   | `/projects/{id}/regenerate-image/` | Re-queue one scene's image (body: `{scene_index}`) |
| `GET`    | `/projects/{id}/download/` | Redirect to signed S3 URL for final.mp4 |
| `GET`    | `/projects/{id}/events/` | SSE stream of job progress events |

### 5.3 Assets

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/music/` | List available music tracks (name, mood, duration) |
| `GET` | `/voices/` | List available edge-tts voices |

### 5.4 Billing

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/billing/plans/` | Available subscription plans |
| `POST` | `/billing/checkout/` | Create Stripe checkout session |
| `POST` | `/billing/portal/` | Stripe customer portal link |
| `POST` | `/billing/webhook/` | Stripe webhook (unsigned, verified by sig) |

### Key Request/Response Shapes

**POST `/api/v1/projects/`**
```json
// Request
{
  "prompt": "The story of a sparrow who learns to share",
  "image_backend": "",         // "" = auto, or "gpt-image-1", "qwen-image"
  "animate": false,
  "music_mood": "",            // "" = auto-pick from plan
  "narrator_voice": ""         // "" = pipeline default
}

// Response 201
{
  "id": "uuid",
  "status": "planning",
  "title": "",
  "created_at": "..."
}
```

**GET `/api/v1/projects/{id}/`**
```json
{
  "id": "uuid",
  "status": "review",
  "title": "The Sparrow Who Learned to Share",
  "prompt": "...",
  "shot_plan": { /* full ShotPlan JSON */ },
  "scenes": [
    {
      "index": 0,
      "narration": "...",
      "image_prompt": "...",
      "image_url": "https://cdn.example.com/...",
      "image_status": "done"
    }
  ],
  "final_video_url": null,
  "duration_secs": null,
  "credit_cost": 1
}
```

**GET `/api/v1/projects/{id}/events/`** — SSE stream
```
data: {"stage": "plan", "message": "Generating shot plan...", "level": "info"}

data: {"stage": "images", "scene_index": 0, "message": "Scene 1/8 done", "level": "info", "image_url": "https://..."}

data: {"stage": "images", "scene_index": 1, "message": "Scene 2/8 done", "level": "info", "image_url": "https://..."}

data: {"stage": "assemble", "message": "Assembling final video...", "level": "info"}

data: {"stage": "done", "final_video_url": "https://...", "duration_secs": 72.4}
```

---

## 6. Async Job Architecture

The pipeline stages run as **Celery tasks**. Redis is the broker. Each stage is a separate 
task so Celery can run image generation for all scenes in parallel.

```
                  ┌─────────────────────────────────────────────┐
                  │                Django API                    │
                  │  POST /projects/ ──► create_plan_job(id)    │
                  │  POST /approve/  ──► create_assets_job(id)  │
                  └───────────────────┬─────────────────────────┘
                                      │ enqueue
                                      ▼
                  ┌───────────────────────────────────────────────┐
                  │              Redis (Celery broker)             │
                  └──┬─────────────────────────────────────────┬──┘
                     │                                         │
              ┌──────▼──────────────┐           ┌─────────────▼─────────┐
              │   plan_worker       │           │   asset_worker(s)      │
              │                     │           │                         │
              │ 1. generate_shot_   │           │ 2. generate_image(     │
              │    plan(prompt)     │           │    project_id, scene)   │
              │ 2. save to DB       │           │    × N scenes parallel  │
              │ 3. project.status   │           │ 3. generate_voiceover   │
              │    = "review"       │           │    (project_id)         │
              │ 4. push SSE event   │           │ 4. assemble(project_id) │
              └─────────────────────┘           │ 5. project.status="done"│
                                                └─────────────────────────┘
```

### Celery Task Definitions

```python
# projects/tasks.py

@app.task(bind=True, max_retries=2)
def run_plan_stage(self, project_id: str):
    project = Project.objects.get(id=project_id)
    project.status = Project.Status.PLANNING
    project.save(update_fields=["status"])

    try:
        plan = generate_shot_plan(project.prompt, model=default_model())
        project.shot_plan = plan.model_dump()
        project.title = plan.title
        project.scene_count = len(plan.scenes)
        project.status = Project.Status.REVIEW
        project.save()
        # Create Scene rows
        for i, s in enumerate(plan.scenes):
            Scene.objects.update_or_create(
                project=project, index=i,
                defaults={"narration": s.narration, "image_prompt": s.image_prompt, ...}
            )
        push_sse(project_id, stage="plan", message="Shot plan ready — please review")
    except Exception as exc:
        project.status = Project.Status.FAILED
        project.save()
        raise self.retry(exc=exc, countdown=5)


@app.task(bind=True, max_retries=3)
def run_image_stage(self, project_id: str, scene_index: int):
    """One task per scene — Celery runs these concurrently."""
    project = Project.objects.get(id=project_id)
    scene = project.scenes.get(index=scene_index)
    scene.image_status = "generating"
    scene.save()

    try:
        plan = ShotPlan.model_validate(project.shot_plan)
        path, provider = generate_scene_image(
            plan, scene_index, tmp_dir(project_id), get_provider(project.image_backend or None),
            fallback=not project.image_backend,
        )
        s3_key = upload_to_s3(path, project_id, f"images/scene_{scene_index:02d}.png")
        scene.image_key = s3_key
        scene.image_url = cdn_url(s3_key)
        scene.image_status = "done"
        scene.image_provider = provider.name
        scene.save()
        push_sse(project_id, stage="images", scene_index=scene_index,
                 message=f"Scene {scene_index + 1}/{project.scene_count} done",
                 image_url=scene.image_url)
    except Exception as exc:
        scene.image_status = "failed"
        scene.save()
        raise self.retry(exc=exc, countdown=10)


@app.task
def run_assets_pipeline(project_id: str):
    """
    Orchestrates: fan-out images in parallel, then voice, then assemble.
    Uses Celery chord: images group → voice callback → assemble callback.
    """
    from celery import chord, group

    project = Project.objects.get(id=project_id)
    project.status = Project.Status.GENERATING
    project.save()

    n = project.scene_count
    image_tasks = group(run_image_stage.s(project_id, i) for i in range(n))
    pipeline = (image_tasks | run_voice_stage.si(project_id) | run_assemble_stage.si(project_id))
    pipeline.delay()
```

### Redis SSE Events

Progress is pushed to Redis pub/sub. The Django SSE endpoint subscribes:

```python
# projects/views.py

def project_events(request, project_id):
    def event_stream():
        r = redis.Redis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        pubsub.subscribe(f"project:{project_id}:events")
        for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data'].decode()}\n\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
```

---

## 7. Frontend Pages (Next.js 14)

### Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Landing | Hero, how it works, pricing |
| `/dashboard` | Dashboard | All user projects (grid) |
| `/create` | Create | Enter prompt, choose options |
| `/projects/[id]` | Project | Status + stage-by-stage display |
| `/projects/[id]/review` | Review | Edit shot plan, approve |
| `/login` | Auth | Sign in / sign up |
| `/billing` | Billing | Plan + usage |
| `/settings` | Settings | Voice, default backend, API key |

### Key Components

**`<CreateForm />`**  
Text area for prompt, toggles for animate/music/voice. Submit → `POST /api/v1/projects/` 
→ redirect to `/projects/[id]`.

**`<PlanEditor />`**  
JSON editor for the shot plan. Renders each scene as a card with editable fields:
- Narration (textarea)
- Image prompt (textarea)
- Negative prompt (collapsible)
- On-screen text (input)
- Voice selector (dropdown)

Approve button calls `POST /api/v1/projects/{id}/approve/`.

**`<ProgressView />`**  
Connects to SSE stream (`/api/v1/projects/{id}/events/`). Shows:
- Stage pipeline: `Plan → Images → Voice → Assemble`
- Per-scene image grid that fills in as images complete
- Spinning indicator on in-progress scenes
- Error badge with retry button on failed scenes

**`<SceneCard />`**  
Displays: generated image (or placeholder skeleton), narration text, image prompt, 
regenerate button. Clicking regenerate calls `POST /api/v1/projects/{id}/regenerate-image/`
`{scene_index: N}`.

**`<VideoPlayer />`**  
When `project.status === "done"`: inline `<video>` tag with CloudFront URL + download 
button. Shows metadata: title, duration, YouTube description (copyable).

### Page Flow

```
/create
  └─► POST /projects/
        │
        ├─ 201 → /projects/[id]
        │         └─ SSE: stage="plan" → loading spinner
        │         └─ SSE: plan ready → redirect to /projects/[id]/review
        │
/projects/[id]/review
  └─► User edits plan (optional)
  └─► PATCH /projects/[id]/ (save edits)
  └─► POST /projects/[id]/approve/
        └─ → /projects/[id]   (back to progress view)
              └─ SSE: images/0 done → scene card shows image
              └─ SSE: images/1 done → ...
              └─ SSE: voice done → audio stage badge turns green
              └─ SSE: done → video player appears, confetti
```

---

## 8. Storage Layout (S3)

```
s3://ai-video-pipeline/
  users/{user_id}/
    projects/{project_id}/
      shot_plan.json
      images/
        scene_00.png
        scene_01.png
        ...
      video/          # only if animate=true
        scene_00.mp4
        ...
      audio/
        scene_00.mp3
        scene_00.words.json
        ...
      final.mp4
      thumbnail.png   # first scene image, resized to 1280x720
```

All files served via CloudFront CDN. Presigned URLs for download links (expire 1h).

---

## 9. Auth & Multi-tenancy

- Email/password registration (Django Allauth)
- Google OAuth2 (one-click signup)
- JWT tokens: 15-minute access, 7-day refresh
- Row-level isolation: every DB query filters `owner=request.user`
- S3 keys are not guessable (`{user_id}/{project_id}/...`) but still presigned for access

---

## 10. Pricing Model (Suggested)

| Plan | Price | Credits/mo | Animate | API Access |
|------|-------|-----------|---------|-----------|
| Free | $0 | 10 videos | No | No |
| Creator | $19/mo | 100 videos | Yes (+3 credits/video) | No |
| Pro | $49/mo | 300 videos | Yes | Yes |
| Team | $149/mo | 1,000 videos | Yes | Yes + team seats |

Credits deducted at assembly start (not plan). Rollover: none. Overage: $0.25/credit.

---

## 11. Deployment Architecture (AWS)

```
                         ┌─────────────────┐
                         │   Route 53 DNS   │
                         └────────┬────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │   CloudFront Distribution   │
                    │   /api/* → ALB             │
                    │   /static/* → S3           │
                    │   /cdn/* → S3 (assets)     │
                    └──┬──────────────────────┬──┘
                       │                      │
          ┌────────────▼──────┐    ┌──────────▼──────────┐
          │  ECS Service      │    │  S3 Bucket           │
          │  (Next.js + Nginx)│    │  ai-video-pipeline   │
          │  Auto-scale 1-10  │    └─────────────────────┘
          └────────────┬──────┘
                       │ /api/*
          ┌────────────▼──────────┐
          │  ALB (Application     │
          │  Load Balancer)       │
          └──┬──────────────────┬─┘
             │                  │
  ┌──────────▼────┐   ┌─────────▼──────────┐
  │  ECS Service  │   │  ECS Service        │
  │  Django API   │   │  Celery Workers     │
  │  (Gunicorn)   │   │  (plan, assets)     │
  │  Auto 2-20    │   │  Auto 1-10          │
  └──────┬────────┘   └────────┬────────────┘
         │                     │
  ┌──────▼─────────────────────▼──┐
  │   AWS ElastiCache (Redis)      │
  │   Celery broker + SSE pub/sub  │
  └──────────────┬────────────────┘
                 │
  ┌──────────────▼────────────────┐
  │   AWS RDS PostgreSQL 16        │
  │   Multi-AZ, encrypted          │
  └───────────────────────────────┘
```

### Docker Images

Three images, all in the same repo:

- **`Dockerfile.web`**: Next.js app (`npm run build && next start`)
- **`Dockerfile.api`**: Django + Gunicorn (no ffmpeg needed)
- **`Dockerfile.worker`**: Django + Celery + **ffmpeg-full** + Python pipeline deps

### Environment Variables (Worker + API)

```
OPENAI_API_KEY
DASHSCOPE_API_KEY
DASHSCOPE_API_URL
DATABASE_URL
REDIS_URL
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
S3_BUCKET_NAME
CLOUDFRONT_BASE_URL
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
DJANGO_SECRET_KEY
ALLOWED_HOSTS
```

---

## 12. MVP Scope vs Full Scope

### Phase 1 — MVP (6-8 weeks)

- [ ] Django API: User model, Project model, Scene model, JobLog
- [ ] Celery tasks: plan + images + voice + assemble (no animate)
- [ ] SSE progress events
- [ ] Next.js pages: create, project detail/review, dashboard
- [ ] S3 upload + CloudFront CDN
- [ ] Email/password auth + JWT
- [ ] Free tier (10 credits) only
- [ ] Deploy to ECS via GitHub Actions

### Phase 2 — Post-MVP (weeks 9-14)

- [ ] Stripe billing (Creator + Pro plans)
- [ ] Wan animation (opt-in per project, extra credits)
- [ ] Google OAuth login
- [ ] Music library in UI (choose track, preview)
- [ ] Voice selector (listen to samples)
- [ ] Per-scene regenerate in UI (with backend selector)
- [ ] Team workspaces

### Phase 3 — Growth

- [ ] REST API access + API keys for Pro/Team
- [ ] Webhooks on job completion
- [ ] YouTube direct upload (OAuth)
- [ ] Usage analytics dashboard

---

## 13. Open Questions

| Question | Options | Recommended |
|----------|---------|-------------|
| LLM for plan generation | OpenAI `gpt-4o-mini` vs Anthropic Haiku | Keep as-is (env-driven); expose model selector to Pro users |
| FFmpeg location | Worker ECS container vs AWS MediaConvert | Worker container (same as CLI, simpler, cheaper) |
| Free trial Wan credits | Per-account DashScope quota | Separate DashScope account per user, or resell from a pool |
| Video retention | Keep forever vs expire after 30 days | Expire after 30 days on free, keep forever on paid |
| SSE vs WebSocket | SSE simpler, WS bidirectional | SSE for now (one-direction progress is enough) |
