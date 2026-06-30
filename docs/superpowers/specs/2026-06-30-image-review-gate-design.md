# Image Review Gate — Design Spec

**Date:** 2026-06-30
**Status:** Approved

## Problem

Currently `REVIEW → approve → GENERATING` runs the full pipeline in one chain:
images → video → voice → assembly → DONE. Users have no opportunity to inspect
or regenerate scene images before voiceover and assembly spend compute.

## Goal

Insert a review gate after image generation. Users inspect scenes, regenerate any
that need it, then explicitly approve before voiceover + assembly run.

## New State Machine

```
DRAFT → PLANNING → REVIEW → GENERATING → IMAGE_REVIEW → VIDEO_GENERATING → DONE
                                  ↓                              ↓
                               FAILED                         FAILED
```

| Status | Meaning |
|---|---|
| `GENERATING` | Image generation in progress (was: full pipeline) |
| `IMAGE_REVIEW` | All images settled; user reviewing / regenerating |
| `VIDEO_GENERATING` | Voice + assembly running (unchanged) |

## Backend Changes

### 1. `apps/projects/choices.py`
Add `IMAGE_REVIEW = "IMAGE_REVIEW"` to `Status`.

### 2. Migration
Auto-generated — adds `IMAGE_REVIEW` to the `status` field's choices.

### 3. `apps/projects/tasks.py` — new task
```python
@shared_task
def transition_to_image_review(project_id):
    project = Project.objects.get(id=project_id)
    if project.status == Status.GENERATING:
        project.transition_status(Status.IMAGE_REVIEW)
        publish_event(project_id, Stage.IMAGES, Level.INFO,
                      "Images ready — review and approve to continue")
    return {"project_id": project_id}
```

### 4. `apps/projects/views.py` — `_dispatch_generate_stage`
Remove voice/video/assembly from the initial chain. New chain:
```python
tasks = [run_image_stage.s(project_id, scene_indices[0])]
tasks += [run_image_stage.si(project_id, idx) for idx in scene_indices[1:]]
tasks += [transition_to_image_review.si(project_id)]
```
(No-scene edge case: if `scene_indices` is empty, dispatch only `transition_to_image_review.si(project_id).delay()` via `_eager_thread`.)

### 5. `apps/projects/views.py` — new `approve_images` action
```
POST /api/projects/{id}/approve-images/
```
- Guard: `project.status != IMAGE_REVIEW` → 409
- Guard: any scene with `media_status != DONE` exists → 409 with message
  `"All scenes must be DONE before approving."`
- Transition project to `VIDEO_GENERATING`
- On commit: dispatch `run_video_stage → run_voice_stage → run_assemble_stage`

### 6. `apps/projects/views.py` — `_dispatch_voice_assembly` helper
```python
def _dispatch_voice_assembly(project_id: str) -> None:
    _eager_thread(chain(
        run_video_stage.s(project_id),
        run_voice_stage.si(project_id),
        run_assemble_stage.si(project_id),
    ).delay)
```

### Unchanged
- `POST /scenes/{idx}/regenerate/` — works from any status; no changes needed.
- `POST /regenerate-images/` — works from any status; no changes needed.
- `run_voice_stage`, `run_assemble_stage` — no changes needed.

## Frontend Changes

### 1. `webapp/lib/project-types.ts`
Add `'IMAGE_REVIEW'` to the `ProjectStatus` union.

### 2. `webapp/components/project/project-page.tsx`
Add branch before the `DONE` check:
```tsx
if (status === 'IMAGE_REVIEW') {
  return <ImageReviewView project={project} onUpdate={updateProject} />
}
```

### 3. `webapp/components/project/image-review-view.tsx` — new file

**Behaviour:**
- On mount and while any scene is `RUNNING` or `PENDING`, poll
  `GET /api/projects/{id}/` every 3 s; update local scene state.
- Stop polling when all scenes are settled (`DONE` or `FAILED`).

**Layout:**
```
┌──────────────────────────────────────────────────────┐
│ [IMAGE_REVIEW pill]               [Delete project]   │
├──────────────────────────────────────────────────────┤
│ Eyebrow: "Review your scenes"                        │
│ Sub: "Regenerate any scene before approving"         │
├──────────────────────────────────────────────────────┤
│ Scene cards (accordion)                              │
│   Collapsed: thumbnail · scene # · status dot ·     │
│              narration preview · ▾                   │
│   Expanded:  full image preview                      │
│              image prompt textarea                   │
│              [Regenerate scene] button               │
│              (NO narration / voice controls)         │
├──────────────────────────────────────────────────────┤
│ [Approve all & generate voiceover]  ← disabled when  │
│  any scene is not DONE; tooltip explains why         │
└──────────────────────────────────────────────────────┘
```

**Approve button:**
- Disabled and shows `title="Regenerate failed scenes first"` when any scene
  has `media_status` that is not `'DONE'` (covers PENDING, RUNNING, and FAILED).
- On click: `POST /api/projects/{id}/approve-images/` → on 202 call `onUpdate`
  with the returned project (status will be `VIDEO_GENERATING`).

**Per-scene regen:**
- Same fetch + poll logic as `DoneSceneCard.handleRegen`.
- On regen start: set that scene's `media_status` to `'RUNNING'` locally.
- Poll scene endpoint every 2 s until `DONE` or `FAILED`; update local state.

### 4. `webapp/components/project/done-view.tsx` — simplified to read-only

**Remove:**
- `DoneSceneCard` component and all its state/logic
- "Regenerate all images" button
- "Regenerate all voiceovers" button
- `isRegenAll`, `isRevoiceAll` transitions
- `handleRegenAll`, `handleRevoiceAll` functions
- `updateSceneStatus`, `updateScene`, `setStale` callbacks (no longer needed)

**Keep:**
- `StatusPill` with `DONE`
- Delete / confirm-delete controls
- `VideoPlayer`
- Simple read-only scene strip: thumbnail + narration text (no expand, no edit)

### 5. `webapp/components/project/status-pill.tsx`
Add `IMAGE_REVIEW` → display label `"Reviewing"` (or `"Image Review"`),
color `#6ea8fe` (existing blue accent).

## Out of Scope
- Re-enabling video animation (still disabled per CLAUDE.md)
- Per-scene approval checkboxes (single approve-all button chosen)
- Voice preview / re-voice controls in the image review view

## Success Criteria
1. After images generate, project lands on `IMAGE_REVIEW` and `ImageReviewView` renders.
2. Approve button is disabled while any scene is `FAILED` or `RUNNING`.
3. Clicking approve transitions to `VIDEO_GENERATING`; `GeneratingView` renders and
   voice + assembly complete; project reaches `DONE`.
4. `DoneView` shows only the video player + read-only scene strip.
5. Existing tests pass; new `approve_images` action has test coverage.
