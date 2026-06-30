# Image Review Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert an `IMAGE_REVIEW` status between image generation and voice/assembly so users can inspect and regenerate scenes before the pipeline continues.

**Architecture:** New `IMAGE_REVIEW` status added to the Django state machine. `_dispatch_generate_stage` now chains images → `transition_to_image_review` (stops there). A new `POST /approve-images/` endpoint transitions to `VIDEO_GENERATING` and dispatches voice → assembly. Frontend adds `ImageReviewView` with per-scene regen + an approve button locked until all scenes are `DONE`. `DoneView` becomes read-only.

**Tech Stack:** Django 5 + Celery (backend), DRF `@action` decorators, Next.js 14 App Router + React 18 (frontend), Tailwind CSS inline classes.

## Global Constraints
- Never commit `.env` or real API keys
- Python 3.13+ syntax (`X | None`, `match`, etc.)
- No new pip/npm dependencies
- `make test` must pass after every backend task
- `CELERY_TASK_ALWAYS_EAGER = True` in test settings — Celery chains/tasks run synchronously when called via `.apply()` or `.delay()` in tests
- Django test settings module: `config.settings.test`
- Session auth: tests set `session["cognito_sub"]` directly on `self.client.session`
- All API routes are under `/api/` prefix

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/projects/choices.py` | Modify | Add `IMAGE_REVIEW` to `Status` |
| `backend/apps/projects/constants.py` | Modify | Update `TRANSITIONS` for new status |
| `backend/apps/projects/migrations/0004_add_image_review_status.py` | Create (auto) | Record new choice in Django migrations |
| `backend/apps/projects/tasks.py` | Modify | Add `transition_to_image_review` shared task |
| `backend/apps/projects/views.py` | Modify | Rewrite `_dispatch_generate_stage`; add `approve_images` action + `_dispatch_voice_assembly` |
| `backend/apps/projects/tests/test_state_machine.py` | Modify | Update for new valid/invalid transitions |
| `backend/apps/projects/tests/test_views_actions.py` | Modify | Add `approve_images` test cases; add `transition_to_image_review` task test |
| `webapp/lib/project-types.ts` | Modify | Add `'IMAGE_REVIEW'` to `ProjectStatus` union |
| `webapp/components/project/status-pill.tsx` | Modify | Add `IMAGE_REVIEW` entry to `DOT` map |
| `webapp/components/project/image-review-view.tsx` | Create | New view: scene accordion + approve button |
| `webapp/components/project/project-page.tsx` | Modify | Add `IMAGE_REVIEW` branch |
| `webapp/components/project/done-view.tsx` | Modify | Strip all regen controls; read-only scene strip |

---

## Task 1: State machine — choices, constants, migration

**Files:**
- Modify: `backend/apps/projects/choices.py`
- Modify: `backend/apps/projects/constants.py`
- Create: `backend/apps/projects/migrations/0004_add_image_review_status.py` (auto-generated)
- Modify: `backend/apps/projects/tests/test_state_machine.py`

**Interfaces:**
- Produces: `Status.IMAGE_REVIEW` constant, valid transitions `GENERATING → IMAGE_REVIEW` and `IMAGE_REVIEW → VIDEO_GENERATING`, invalid `GENERATING → DONE`

- [ ] **Step 1: Write the failing state-machine tests**

Add to `backend/apps/projects/tests/test_state_machine.py`:

```python
# In ValidTransitionsTest — add these two methods:
def test_generating_to_image_review(self):
    p = make_project_in(Status.GENERATING)
    p.transition_status(Status.IMAGE_REVIEW)
    self.assertEqual(p.status, Status.IMAGE_REVIEW)

def test_image_review_to_video_generating(self):
    p = make_project_in(Status.IMAGE_REVIEW)
    p.transition_status(Status.VIDEO_GENERATING)
    self.assertEqual(p.status, Status.VIDEO_GENERATING)

def test_image_review_to_failed(self):
    p = make_project_in(Status.IMAGE_REVIEW)
    p.transition_status(Status.FAILED)
    self.assertEqual(p.status, Status.FAILED)

# In InvalidTransitionsTest — add these two methods:
def test_generating_to_done_is_now_invalid(self):
    self._assert_raises(Status.GENERATING, Status.DONE)

def test_image_review_to_done_is_invalid(self):
    self._assert_raises(Status.IMAGE_REVIEW, Status.DONE)
```

Also **remove** `test_generating_to_done` from `ValidTransitionsTest` (it will move to invalid).

- [ ] **Step 2: Run to verify failures**

```bash
cd backend && python manage.py test apps.projects.tests.test_state_machine -v 2
```

Expected: new tests fail with `ValueError` or `Status.IMAGE_REVIEW` not found; `test_generating_to_done` passes (it's still in valid, so it passes until we change the code — that's fine at this stage).

- [ ] **Step 3: Add `IMAGE_REVIEW` to choices**

In `backend/apps/projects/choices.py`, add after `REVIEW`:

```python
class Status(models.TextChoices):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    REVIEW = "REVIEW"
    IMAGE_REVIEW = "IMAGE_REVIEW"
    GENERATING = "GENERATING"
    DONE = "DONE"
    VIDEO_GENERATING = "VIDEO_GENERATING"
    FAILED = "FAILED"
```

- [ ] **Step 4: Update TRANSITIONS**

Replace the entire content of `backend/apps/projects/constants.py`:

```python
from apps.projects.choices import Status

TRANSITIONS: dict[str, set[str]] = {
    Status.DRAFT:         {Status.PLANNING},
    Status.PLANNING:      {Status.REVIEW, Status.FAILED},
    Status.REVIEW:        {Status.PLANNING, Status.GENERATING},
    Status.GENERATING:    {Status.IMAGE_REVIEW, Status.FAILED},
    Status.IMAGE_REVIEW:  {Status.VIDEO_GENERATING, Status.FAILED},
    Status.FAILED:        {Status.GENERATING},
    Status.DONE:          {Status.VIDEO_GENERATING},
    Status.VIDEO_GENERATING: {Status.DONE},
}
```

- [ ] **Step 5: Generate and apply migration**

```bash
cd backend && python manage.py makemigrations projects --name add_image_review_status
python manage.py migrate
```

Expected: creates `0004_add_image_review_status.py`, applies cleanly with no errors.

- [ ] **Step 6: Run state-machine tests**

```bash
cd backend && python manage.py test apps.projects.tests.test_state_machine -v 2
```

Expected: all tests pass.

- [ ] **Step 7: Run full test suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/projects/choices.py \
        backend/apps/projects/constants.py \
        backend/apps/projects/migrations/0004_add_image_review_status.py \
        backend/apps/projects/tests/test_state_machine.py
git commit -m "feat: add IMAGE_REVIEW status to project state machine"
```

---

## Task 2: `transition_to_image_review` task + dispatch rewrite

**Files:**
- Modify: `backend/apps/projects/tasks.py`
- Modify: `backend/apps/projects/views.py`
- Modify: `backend/apps/projects/tests/test_views_actions.py`

**Interfaces:**
- Consumes: `Status.IMAGE_REVIEW` from Task 1
- Produces: `transition_to_image_review(project_id: str)` shared task; `_dispatch_voice_assembly(project_id: str)` helper function

- [ ] **Step 1: Write failing tests**

Add to `backend/apps/projects/tests/test_views_actions.py` — inside the existing `ProjectActionsTest` class (which already has `setUp` with an owner, project in `REVIEW` status, and one scene):

```python
from apps.projects.tasks import transition_to_image_review as _transition_task

class TransitionToImageReviewTaskTest(TestCase):
    def setUp(self):
        self.owner = make_user("owner-transition")
        self.project = Project.objects.create(
            owner=self.owner, prompt="p", status=Status.GENERATING
        )

    def test_transitions_generating_project_to_image_review(self):
        _transition_task(str(self.project.id))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Status.IMAGE_REVIEW)

    def test_no_op_when_project_is_failed(self):
        Project.objects.filter(pk=self.project.pk).update(status=Status.FAILED)
        self.project.refresh_from_db()
        _transition_task(str(self.project.id))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Status.FAILED)
```

Also add inside `ProjectActionsTest`:

```python
@patch("apps.projects.views._eager_thread")
def test_approve_dispatches_only_image_chain(self, eager_thread):
    """approve action should trigger GENERATING, not go all the way to voice/assembly."""
    resp = self.client.post(f"/api/projects/{self.project.id}/approve/")
    self.assertEqual(resp.status_code, 202)
    self.project.refresh_from_db()
    self.assertEqual(self.project.status, Status.GENERATING)
    eager_thread.assert_called_once()
```

- [ ] **Step 2: Run to verify failures**

```bash
cd backend && python manage.py test apps.projects.tests.test_views_actions.TransitionToImageReviewTaskTest -v 2
```

Expected: `ImportError` or `AttributeError` — `transition_to_image_review` does not exist yet.

- [ ] **Step 3: Add `transition_to_image_review` task to `tasks.py`**

At the end of `backend/apps/projects/tasks.py`, add:

```python
@shared_task
def transition_to_image_review(project_id):
    project = Project.objects.get(id=project_id)
    if project.status == Status.GENERATING:
        project.transition_status(Status.IMAGE_REVIEW)
        publish_event(
            project_id, Stage.IMAGES, Level.INFO,
            "Images ready — review and approve to continue",
        )
    return {"project_id": project_id}
```

- [ ] **Step 4: Update `views.py` — imports and `_dispatch_generate_stage`**

In `backend/apps/projects/views.py`, update the tasks import line:

```python
from .tasks import (
    run_assemble_stage,
    run_image_stage,
    run_refine_stage,
    run_video_stage,
    run_voice_stage,
    transition_to_image_review,
)
```

Replace `_dispatch_generate_stage` (at the bottom of the file) with:

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
        tasks += [transition_to_image_review.si(project_id)]
        _eager_thread(chain(*tasks).delay)
    else:
        _eager_thread(transition_to_image_review.delay, project_id)


def _dispatch_voice_assembly(project_id: str) -> None:
    _eager_thread(chain(
        run_video_stage.s(project_id),
        run_voice_stage.si(project_id),
        run_assemble_stage.si(project_id),
    ).delay)
```

- [ ] **Step 5: Run the new tests**

```bash
cd backend && python manage.py test apps.projects.tests.test_views_actions -v 2
```

Expected: all tests in that file pass.

- [ ] **Step 6: Run full test suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/projects/tasks.py \
        backend/apps/projects/views.py \
        backend/apps/projects/tests/test_views_actions.py
git commit -m "feat: add transition_to_image_review task and rewrite dispatch chain"
```

---

## Task 3: `approve_images` endpoint

**Files:**
- Modify: `backend/apps/projects/views.py`
- Modify: `backend/apps/projects/tests/test_views_actions.py`

**Interfaces:**
- Consumes: `Status.IMAGE_REVIEW` (Task 1), `_dispatch_voice_assembly` (Task 2)
- Produces: `POST /api/projects/{id}/approve-images/` → 202 with updated project JSON, or 409

- [ ] **Step 1: Write failing tests**

Add a new test class to `backend/apps/projects/tests/test_views_actions.py`:

```python
class ApproveImagesTest(TestCase):
    def setUp(self):
        self.owner = make_user("owner-approve-images")
        self.project = Project.objects.create(
            owner=self.owner,
            prompt="p",
            status=Status.IMAGE_REVIEW,
            shot_plan={"title": "T"},
        )
        self.scene = Scene.objects.create(
            project=self.project,
            index=0,
            narration="n",
            media_prompt="m",
            media_status="DONE",
        )
        session = self.client.session
        session["cognito_sub"] = self.owner.cognito_sub
        session.save()

    @patch("apps.projects.views._eager_thread")
    def test_approve_transitions_to_video_generating_and_dispatches(self, eager_thread):
        resp = self.client.post(f"/api/projects/{self.project.id}/approve-images/")
        self.assertEqual(resp.status_code, 202)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Status.VIDEO_GENERATING)
        eager_thread.assert_called_once()

    @patch("apps.projects.views._eager_thread")
    def test_approve_blocked_when_scene_not_done(self, eager_thread):
        self.scene.media_status = "PENDING"
        self.scene.save(update_fields=["media_status", "updated_at"])
        resp = self.client.post(f"/api/projects/{self.project.id}/approve-images/")
        self.assertEqual(resp.status_code, 409)
        eager_thread.assert_not_called()

    @patch("apps.projects.views._eager_thread")
    def test_approve_blocked_when_scene_failed(self, eager_thread):
        self.scene.media_status = "FAILED"
        self.scene.save(update_fields=["media_status", "updated_at"])
        resp = self.client.post(f"/api/projects/{self.project.id}/approve-images/")
        self.assertEqual(resp.status_code, 409)
        eager_thread.assert_not_called()

    def test_approve_wrong_status_returns_409(self):
        Project.objects.filter(pk=self.project.pk).update(status=Status.REVIEW)
        resp = self.client.post(f"/api/projects/{self.project.id}/approve-images/")
        self.assertEqual(resp.status_code, 409)

    def test_approve_unauthenticated_returns_403(self):
        client = self.__class__._pre_setup.__func__  # fresh client with no session
        from django.test import Client
        anon = Client()
        resp = anon.post(f"/api/projects/{self.project.id}/approve-images/")
        self.assertIn(resp.status_code, [401, 403])
```

- [ ] **Step 2: Run to verify failures**

```bash
cd backend && python manage.py test apps.projects.tests.test_views_actions.ApproveImagesTest -v 2
```

Expected: 404 responses (action not registered yet).

- [ ] **Step 3: Add `approve_images` action to `ProjectViewSet`**

In `backend/apps/projects/views.py`, add this method inside `ProjectViewSet`, after the `reassemble` action:

```python
@action(detail=True, methods=["post"], url_path="approve-images")
def approve_images(self, request, pk=None):
    with transaction.atomic():
        project = self._get_locked_project()
        if project.status != Status.IMAGE_REVIEW:
            return Response(
                {"detail": f"Cannot approve images from {project.status} state."},
                status=status.HTTP_409_CONFLICT,
            )
        not_done = project.scenes.exclude(media_status=MediaStatus.DONE)
        if not_done.exists():
            return Response(
                {"detail": "All scenes must be DONE before approving."},
                status=status.HTTP_409_CONFLICT,
            )
        project.transition_status(Status.VIDEO_GENERATING)
    project_id = str(project.id)
    transaction.on_commit(lambda: _dispatch_voice_assembly(project_id))
    return Response(self.get_serializer(project).data, status=status.HTTP_202_ACCEPTED)
```

- [ ] **Step 4: Run the approve tests**

```bash
cd backend && python manage.py test apps.projects.tests.test_views_actions.ApproveImagesTest -v 2
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/projects/views.py \
        backend/apps/projects/tests/test_views_actions.py
git commit -m "feat: add approve-images endpoint to gate voiceover on user approval"
```

---

## Task 4: Frontend types + status pill

**Files:**
- Modify: `webapp/lib/project-types.ts`
- Modify: `webapp/components/project/status-pill.tsx`

**Interfaces:**
- Produces: `ProjectStatus` union includes `'IMAGE_REVIEW'`; `StatusPill` renders it with orange pulse dot and label `"image_review"`

- [ ] **Step 1: Add `IMAGE_REVIEW` to `ProjectStatus` union**

In `webapp/lib/project-types.ts`, update `ProjectStatus`:

```typescript
export type ProjectStatus =
  | 'DRAFT'
  | 'PLANNING'
  | 'REVIEW'
  | 'IMAGE_REVIEW'
  | 'GENERATING'
  | 'VIDEO_GENERATING'
  | 'DONE'
  | 'FAILED'
```

- [ ] **Step 2: Add `IMAGE_REVIEW` to the status pill DOT map**

In `webapp/components/project/status-pill.tsx`, update the `DOT` constant:

```typescript
const DOT: Record<string, { color: string; pulse: boolean }> = {
  DRAFT:            { color: '#9aa3b2', pulse: false },
  PLANNING:         { color: '#6ea8fe', pulse: true  },
  REVIEW:           { color: '#5cd6a4', pulse: false },
  IMAGE_REVIEW:     { color: '#6ea8fe', pulse: false },
  GENERATING:       { color: '#f0a35e', pulse: true  },
  VIDEO_GENERATING: { color: '#f0a35e', pulse: true  },
  DONE:             { color: '#5cd6a4', pulse: false },
  FAILED:           { color: '#f06a6a', pulse: false },
}
```

- [ ] **Step 3: Commit**

```bash
git add webapp/lib/project-types.ts \
        webapp/components/project/status-pill.tsx
git commit -m "feat: add IMAGE_REVIEW to frontend types and status pill"
```

---

## Task 5: `ImageReviewView` component

**Files:**
- Create: `webapp/components/project/image-review-view.tsx`

**Interfaces:**
- Consumes: `Project`, `Scene` types (Task 4); `POST /api/projects/{id}/approve-images/`; `POST /api/projects/{id}/scenes/{idx}/regenerate/`; `GET /api/projects/{id}/scenes/{idx}/`
- Produces: `export default function ImageReviewView({ project, onUpdate }: Props)`

- [ ] **Step 1: Create the file**

Create `webapp/components/project/image-review-view.tsx` with this content:

```tsx
'use client'

import { memo, useCallback, useEffect, useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Project, Scene } from '@/lib/project-types'
import { Button } from '@/components/ui/button'
import StatusPill from './status-pill'

interface Props {
  project: Project
  onUpdate: (updates: Partial<Project>) => void
}

function stableMediaSrc(scene: Scene): string | undefined {
  if (!scene.media_path) return undefined
  if (scene.media_path.includes('?')) return scene.media_path
  return `${scene.media_path}?v=${encodeURIComponent(scene.updated_at ?? '')}`
}

function isVideo(path: string): boolean {
  return path.split('?')[0].endsWith('.mp4')
}

const IMG_STATUS_COLOR: Record<string, string> = {
  PENDING: '#9aa3b2',
  RUNNING: '#f0a35e',
  DONE:    '#5cd6a4',
  FAILED:  '#f06a6a',
}

const TEXTAREA_CLASS =
  'w-full bg-[#171a21] text-[#e7e9ee] border border-[#2a2f3a] rounded-lg px-3 py-2 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-[#6ea8fe]'

export default function ImageReviewView({ project, onUpdate }: Props) {
  const router = useRouter()
  const [scenes, setScenes] = useState<Scene[]>(project.scenes)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isApproving, startApprove] = useTransition()
  const [isDeleting, startDelete] = useTransition()

  const allDone = scenes.every(s => s.media_status === 'DONE')

  function handleDelete() {
    startDelete(async () => {
      const res = await fetch(`/api/projects/${project.id}/`, { method: 'DELETE' })
      if (res.status === 204) { router.refresh(); router.push('/home') }
    })
  }

  function handleApprove() {
    startApprove(async () => {
      const res = await fetch(`/api/projects/${project.id}/approve-images/`, {
        method: 'POST',
      })
      if (res.ok) {
        const updated: Project = await res.json()
        onUpdate(updated)
      }
    })
  }

  const updateSceneStatus = useCallback(
    (index: number, media_status: Scene['media_status']) => {
      setScenes(prev =>
        prev.map(s => (s.index === index ? { ...s, media_status } : s)),
      )
    },
    [],
  )

  const updateScene = useCallback((updated: Scene) => {
    setScenes(prev => prev.map(s => s.index === updated.index ? updated : s))
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <StatusPill status="IMAGE_REVIEW" />
        {confirmDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#9aa3b2]">Delete this project?</span>
            <Button
              disabled={isDeleting}
              onClick={handleDelete}
              className="bg-[#f06a6a] text-white text-xs px-3 py-1.5 rounded-lg hover:bg-[#d95858] disabled:opacity-50"
            >
              {isDeleting ? 'Deleting…' : 'Yes, delete'}
            </Button>
            <Button
              onClick={() => setConfirmDelete(false)}
              className="bg-transparent border border-[#2a2f3a] text-[#e7e9ee] text-xs px-3 py-1.5 rounded-lg hover:bg-[#1e222b]"
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            onClick={() => setConfirmDelete(true)}
            className="bg-transparent border border-[#f06a6a]/40 text-[#f06a6a] text-xs px-3 py-1.5 rounded-lg hover:bg-[#f06a6a]/10"
          >
            Delete project
          </Button>
        )}
      </div>

      {/* Eyebrow */}
      <div>
        <p className="text-[10px] uppercase tracking-[0.2em] font-medium text-[#4a5568]">
          Review your scenes
        </p>
        <p className="text-xs text-[#9aa3b2] mt-1">
          Regenerate any scene before approving
        </p>
      </div>

      {/* Scene cards */}
      <div className="space-y-2">
        {scenes.map(scene => (
          <ReviewSceneCard
            key={scene.id}
            scene={scene}
            projectId={project.id}
            onStatusChange={updateSceneStatus}
            onSceneUpdate={updateScene}
          />
        ))}
      </div>

      {/* Approve button */}
      <div className="pt-2">
        <Button
          disabled={!allDone || isApproving}
          onClick={handleApprove}
          title={!allDone ? 'Regenerate failed scenes first' : undefined}
          className="w-full bg-[#5cd6a4] text-[#0d1117] font-medium text-sm py-3 rounded-lg hover:bg-[#4bc494] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isApproving ? 'Approving…' : 'Approve all & generate voiceover'}
        </Button>
      </div>
    </div>
  )
}

const ReviewSceneCard = memo(function ReviewSceneCard({
  scene,
  projectId,
  onStatusChange,
  onSceneUpdate,
}: {
  scene: Scene
  projectId: string
  onStatusChange: (index: number, status: Scene['media_status']) => void
  onSceneUpdate: (updated: Scene) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [mediaPrompt, setMediaPrompt] = useState(scene.media_prompt)
  const [isRegenerating, startRegen] = useTransition()
  const mediaPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => {
    if (mediaPollRef.current) clearInterval(mediaPollRef.current)
  }, [])

  const imgColor = IMG_STATUS_COLOR[scene.media_status] ?? '#9aa3b2'

  function handleRegen() {
    startRegen(async () => {
      onStatusChange(scene.index, 'RUNNING')
      await fetch(`/api/projects/${projectId}/scenes/${scene.index}/regenerate/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: mediaPrompt }),
      })
      if (mediaPollRef.current) clearInterval(mediaPollRef.current)
      mediaPollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`/api/projects/${projectId}/scenes/${scene.index}/`)
          if (!res.ok) return
          const updated: Scene = await res.json()
          onStatusChange(scene.index, updated.media_status)
          if (updated.media_status === 'DONE' || updated.media_status === 'FAILED') {
            clearInterval(mediaPollRef.current!)
            mediaPollRef.current = null
            onSceneUpdate(updated)
          }
        } catch { /* keep polling */ }
      }, 2000)
    })
  }

  return (
    <div className="bg-[#1e222b] border border-[#2a2f3a] rounded-[10px] overflow-hidden">
      {/* Collapsed header */}
      <button
        type="button"
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-[#252a35] transition-colors text-left"
      >
        <div className="w-16 h-10 rounded bg-[#171a21] shrink-0 overflow-hidden flex items-center justify-center">
          {scene.media_path && scene.media_status === 'DONE' ? (
            isVideo(scene.media_path) ? (
              <div className="relative w-full h-full">
                <video
                  src={stableMediaSrc(scene)}
                  playsInline
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-5 h-5 rounded-full bg-black/50 flex items-center justify-center">
                    <span className="text-white text-[8px] pl-0.5">▶</span>
                  </div>
                </div>
              </div>
            ) : (
              <img
                src={stableMediaSrc(scene)}
                alt=""
                className="w-full h-full object-cover"
              />
            )
          ) : scene.media_status === 'RUNNING' ? (
            <div className="w-4 h-4 rounded-full border border-[#f0a35e] border-t-transparent animate-spin" />
          ) : (
            <span className="text-[#4a5568] text-[10px]">
              {scene.media_status.toLowerCase()}
            </span>
          )}
        </div>
        <span className="text-xs font-mono text-[#9aa3b2] shrink-0">
          {String(scene.index + 1).padStart(2, '0')}
        </span>
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ backgroundColor: imgColor }}
        />
        <span className="text-xs text-[#9aa3b2] truncate flex-1">
          {scene.narration}
        </span>
        <span className="text-[10px] text-[#4a5568] shrink-0 font-mono">
          {expanded ? '▴' : '▾'}
        </span>
      </button>

      {/* Expanded panel */}
      {expanded ? (
        <div className="border-t border-[#2a2f3a] relative overflow-hidden">
          <span
            aria-hidden
            className="absolute right-3 top-0 text-[88px] font-bold leading-none text-[#2a2f3a] select-none pointer-events-none"
          >
            {String(scene.index + 1).padStart(2, '0')}
          </span>
          <div className="relative z-10 p-4 space-y-5">
            {/* Full image preview */}
            <div className="aspect-video bg-[#171a21] rounded-lg overflow-hidden flex items-center justify-center">
              {scene.media_path && scene.media_status === 'DONE' ? (
                isVideo(scene.media_path) ? (
                  <video
                    src={stableMediaSrc(scene)}
                    controls
                    autoPlay
                    muted
                    loop
                    playsInline
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <img
                    src={stableMediaSrc(scene)}
                    alt={`Scene ${scene.index + 1}`}
                    className="w-full h-full object-cover"
                  />
                )
              ) : scene.media_status === 'RUNNING' ? (
                <div className="w-7 h-7 rounded-full border-2 border-[#f0a35e] border-t-transparent animate-spin" />
              ) : scene.media_status === 'FAILED' ? (
                <span className="text-[#f06a6a] text-2xl">✕</span>
              ) : (
                <span className="text-[#4a5568] text-xs">pending</span>
              )}
            </div>

            {/* Image prompt */}
            <div className="space-y-2">
              <label className="block text-xs text-[#9aa3b2]">Image prompt</label>
              <textarea
                value={mediaPrompt}
                onChange={e => setMediaPrompt(e.target.value)}
                rows={2}
                className={TEXTAREA_CLASS}
              />
              <Button
                disabled={isRegenerating}
                onClick={handleRegen}
                className="bg-transparent border border-[#2a2f3a] text-[#e7e9ee] text-xs px-3 py-2 rounded-lg hover:bg-[#252a35] disabled:opacity-50"
              >
                {isRegenerating ? 'Queuing…' : 'Regenerate scene'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
})
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors relating to `image-review-view.tsx`.

- [ ] **Step 3: Commit**

```bash
git add webapp/components/project/image-review-view.tsx
git commit -m "feat: add ImageReviewView component with per-scene regen and approve button"
```

---

## Task 6: Wire `ImageReviewView` into `ProjectPage` + simplify `DoneView`

**Files:**
- Modify: `webapp/components/project/project-page.tsx`
- Modify: `webapp/components/project/done-view.tsx`

**Interfaces:**
- Consumes: `ImageReviewView` (Task 5), `ProjectStatus` union with `IMAGE_REVIEW` (Task 4)

- [ ] **Step 1: Add `IMAGE_REVIEW` branch to `project-page.tsx`**

In `webapp/components/project/project-page.tsx`, add the import and branch:

```tsx
'use client'

import { useCallback, useState } from 'react'
import dynamic from 'next/dynamic'
import { Project } from '@/lib/project-types'
import PlanningView from './planning-view'
import PlanEditor from './plan-editor'
import DoneView from './done-view'
import FailedView from './failed-view'
import ImageReviewView from './image-review-view'

const GeneratingView = dynamic(() => import('./generating-view'), { ssr: false })

interface Props {
  initialProject: Project
}

export default function ProjectPage({ initialProject }: Props) {
  const [project, setProject] = useState<Project>(initialProject)

  const updateProject = useCallback((updates: Partial<Project>) => {
    setProject(prev => ({ ...prev, ...updates }))
  }, [])

  const { status } = project

  if (status === 'DRAFT' || status === 'PLANNING') {
    return <PlanningView project={project} onUpdate={updateProject} />
  }
  if (status === 'REVIEW') {
    return <PlanEditor project={project} onUpdate={updateProject} />
  }
  if (status === 'GENERATING' || status === 'VIDEO_GENERATING') {
    return <GeneratingView project={project} onUpdate={updateProject} />
  }
  if (status === 'IMAGE_REVIEW') {
    return <ImageReviewView project={project} onUpdate={updateProject} />
  }
  if (status === 'DONE') {
    return <DoneView project={project} onUpdate={updateProject} />
  }
  return <FailedView project={project} onUpdate={updateProject} />
}
```

- [ ] **Step 2: Simplify `done-view.tsx` to read-only**

Replace the entire content of `webapp/components/project/done-view.tsx` with:

```tsx
'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Project, Scene } from '@/lib/project-types'
import { Button } from '@/components/ui/button'
import VideoPlayer from './video-player'
import StatusPill from './status-pill'

interface Props {
  project: Project
  onUpdate: (updates: Partial<Project>) => void
}

function stableMediaSrc(scene: Scene): string | undefined {
  if (!scene.media_path) return undefined
  if (scene.media_path.includes('?')) return scene.media_path
  return `${scene.media_path}?v=${encodeURIComponent(scene.updated_at ?? '')}`
}

function isVideo(path: string): boolean {
  return path.split('?')[0].endsWith('.mp4')
}

export default function DoneView({ project, onUpdate }: Props) {
  const router = useRouter()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isDeleting, startDelete] = useTransition()

  function handleDelete() {
    startDelete(async () => {
      const res = await fetch(`/api/projects/${project.id}/`, { method: 'DELETE' })
      if (res.status === 204) { router.refresh(); router.push('/home') }
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <StatusPill status="DONE" />
        {confirmDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#9aa3b2]">Delete this project?</span>
            <Button
              disabled={isDeleting}
              onClick={handleDelete}
              className="bg-[#f06a6a] text-white text-xs px-3 py-1.5 rounded-lg hover:bg-[#d95858] disabled:opacity-50"
            >
              {isDeleting ? 'Deleting…' : 'Yes, delete'}
            </Button>
            <Button
              onClick={() => setConfirmDelete(false)}
              className="bg-transparent border border-[#2a2f3a] text-[#e7e9ee] text-xs px-3 py-1.5 rounded-lg hover:bg-[#1e222b]"
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            onClick={() => setConfirmDelete(true)}
            className="bg-transparent border border-[#f06a6a]/40 text-[#f06a6a] text-xs px-3 py-1.5 rounded-lg hover:bg-[#f06a6a]/10"
          >
            Delete project
          </Button>
        )}
      </div>

      <VideoPlayer
        projectId={project.id}
        stale={project.stale}
        onRebuild={(updated) => onUpdate(updated)}
      />

      <div>
        <p className="text-[10px] uppercase tracking-[0.2em] font-medium text-[#4a5568] mb-2">
          Scenes
        </p>
        <div className="space-y-2">
          {project.scenes.map(scene => (
            <div
              key={scene.id}
              className="bg-[#1e222b] border border-[#2a2f3a] rounded-[10px] flex items-center gap-3 px-3 py-2.5"
            >
              <div className="w-16 h-10 rounded bg-[#171a21] shrink-0 overflow-hidden flex items-center justify-center">
                {scene.media_path ? (
                  isVideo(scene.media_path) ? (
                    <video
                      src={stableMediaSrc(scene)}
                      playsInline
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <img
                      src={stableMediaSrc(scene)}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  )
                ) : (
                  <span className="text-[#4a5568] text-[10px]">none</span>
                )}
              </div>
              <span className="text-xs font-mono text-[#9aa3b2] shrink-0">
                {String(scene.index + 1).padStart(2, '0')}
              </span>
              <span className="text-xs text-[#9aa3b2] truncate flex-1">
                {scene.narration}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Run full backend test suite one final time**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add webapp/components/project/project-page.tsx \
        webapp/components/project/done-view.tsx
git commit -m "feat: wire ImageReviewView into project page; make DoneView read-only"
```

---

## Self-review notes

- **Spec coverage:** All 5 success criteria covered. State machine ✓, approve guard ✓, voice+assembly trigger ✓, read-only DoneView ✓, test coverage ✓.
- **Type consistency:** `transition_to_image_review` called as `transition_to_image_review.si(project_id)` in chain (Task 2) and imported via top-level tasks import (Task 2). `approve_images` calls `_dispatch_voice_assembly` defined in same file (Task 2). `ImageReviewView` export matches import in `project-page.tsx` (Tasks 5 + 6). `Scene['media_status']` used consistently throughout.
- **No placeholders:** All steps contain exact code. No TBDs.
- **YAGNI:** No extra buttons, no global polling in `ImageReviewView` (per-scene polls cover all regen cases), no backwards-compat shims in `DoneView`.
