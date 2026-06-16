# Epic A2 — Data Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four Django models (UserProfile, Project, Scene, JobLog) with migrations, state-machine enforcement on Project.status, and full test coverage.

**Architecture:** Two Django apps — `apps.users` owns UserProfile; `apps.projects` owns Project, Scene, JobLog. Project carries a `transition_status(new)` method that raises `ValueError` on illegal transitions — state is always mutated through this method, never by direct assignment. Scene rows hold image artifact state only; all plan content lives in `Project.shot_plan` (D1).

**Tech Stack:** Django 5.2, SQLite, Django test runner (`manage.py test`).

---

## File Structure

```
backend/apps/users/
  __init__.py
  apps.py
  models.py             — UserProfile
  migrations/
    __init__.py
    0001_initial.py     — generated

backend/apps/projects/
  __init__.py
  apps.py
  models.py             — Project (+ Status enum), Scene (+ ImageStatus enum), JobLog
  migrations/
    __init__.py
    0001_initial.py     — generated

backend/config/settings.py   — add apps.users, apps.projects to INSTALLED_APPS

backend/tests/
  test_models_users.py        — UserProfile creation + uniqueness
  test_models_projects.py     — Project fields, defaults, cascade deletes
  test_state_machine.py       — valid + invalid status transitions
  test_models_scenes.py       — Scene creation, image status enum
  test_models_joblog.py       — JobLog creation, append-only pattern
```

---

## Task 1: `apps.users` — UserProfile model

**Files:**
- Create: `backend/apps/users/__init__.py`
- Create: `backend/apps/users/apps.py`
- Create: `backend/apps/users/models.py`
- Modify: `backend/config/settings.py`
- Create: `backend/tests/test_models_users.py`

- [ ] **Step 1: Write the failing tests**

Write `backend/tests/test_models_users.py`:

```python
from django.test import TestCase
from django.db import IntegrityError
from apps.users.models import UserProfile


class UserProfileTest(TestCase):
    def _make_profile(self, sub="sub-123", email="a@example.com", name="Alice"):
        return UserProfile.objects.create(cognito_sub=sub, email=email, name=name)

    def test_create_profile(self):
        p = self._make_profile()
        self.assertEqual(p.cognito_sub, "sub-123")
        self.assertEqual(p.email, "a@example.com")
        self.assertEqual(p.name, "Alice")
        self.assertIsNotNone(p.created_at)

    def test_cognito_sub_is_unique(self):
        self._make_profile()
        with self.assertRaises(IntegrityError):
            self._make_profile()  # same sub

    def test_name_is_optional(self):
        p = UserProfile.objects.create(cognito_sub="sub-456", email="b@example.com")
        self.assertEqual(p.name, "")

    def test_str(self):
        p = self._make_profile()
        self.assertIn("a@example.com", str(p))
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend && uv run python manage.py test tests.test_models_users --verbosity=2 2>&1
```

Expected: `ModuleNotFoundError: No module named 'apps.users'`

- [ ] **Step 3: Create the app files**

Create `backend/apps/users/__init__.py` (empty).

Write `backend/apps/users/apps.py`:

```python
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
```

Write `backend/apps/users/models.py`:

```python
from django.db import models


class UserProfile(models.Model):
    cognito_sub = models.CharField(max_length=128, unique=True, db_index=True)
    email = models.CharField(max_length=254)
    name = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
```

- [ ] **Step 4: Register app in settings**

In `backend/config/settings.py`, update `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "apps.health",
    "apps.users",
    "apps.projects",   # add now — model created next task
]
```

Wait — add `apps.projects` only after Task 2. For now add only `apps.users`:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "apps.health",
    "apps.users",
]
```

- [ ] **Step 5: Make and apply migration**

```bash
cd backend && uv run python manage.py makemigrations users
uv run python manage.py migrate
```

Expected:
```
Migrations for 'users':
  apps/users/migrations/0001_initial.py
    + Create model UserProfile
```

- [ ] **Step 6: Run tests — expect pass**

```bash
cd backend && uv run python manage.py test tests.test_models_users --verbosity=2 2>&1
```

Expected:
```
test_cognito_sub_is_unique ... ok
test_create_profile ... ok
test_name_is_optional ... ok
test_str ... ok
Ran 4 tests in 0.XXXs
OK
```

---

## Task 2: `apps.projects` — Project model + status state machine

**Files:**
- Create: `backend/apps/projects/__init__.py`
- Create: `backend/apps/projects/apps.py`
- Create: `backend/apps/projects/models.py`
- Modify: `backend/config/settings.py`
- Create: `backend/tests/test_models_projects.py`
- Create: `backend/tests/test_state_machine.py`

- [ ] **Step 1: Write failing tests for Project fields**

Write `backend/tests/test_models_projects.py`:

```python
import uuid
from django.test import TestCase
from apps.users.models import UserProfile
from apps.projects.models import Project


def make_user(sub="sub-1"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@example.com")


def make_project(owner=None, **kwargs):
    if owner is None:
        owner = make_user()
    return Project.objects.create(owner=owner, prompt="a test prompt", **kwargs)


class ProjectFieldsTest(TestCase):
    def test_id_is_uuid(self):
        p = make_project()
        self.assertIsInstance(p.id, uuid.UUID)

    def test_defaults(self):
        p = make_project()
        self.assertEqual(p.status, Project.Status.DRAFT)
        self.assertIsNone(p.shot_plan)
        self.assertEqual(p.image_backend, "")
        self.assertFalse(p.animate)
        self.assertEqual(p.narrator_voice, "")
        self.assertEqual(p.music, "")
        self.assertEqual(p.error, "")
        self.assertFalse(p.stale)
        self.assertEqual(p.title, "")

    def test_owner_fk(self):
        user = make_user("sub-owner")
        p = make_project(owner=user)
        self.assertEqual(p.owner, user)

    def test_cascade_delete(self):
        user = make_user("sub-del")
        p = make_project(owner=user)
        pid = p.id
        user.delete()
        self.assertFalse(Project.objects.filter(id=pid).exists())

    def test_timestamps(self):
        p = make_project()
        self.assertIsNotNone(p.created_at)
        self.assertIsNotNone(p.updated_at)
```

- [ ] **Step 2: Write failing tests for state machine**

Write `backend/tests/test_state_machine.py`:

```python
from django.test import TestCase
from apps.users.models import UserProfile
from apps.projects.models import Project


def make_project_in(status):
    user = UserProfile.objects.create(
        cognito_sub=f"sub-{status}", email=f"{status}@example.com"
    )
    p = Project.objects.create(owner=user, prompt="test")
    # force status without going through state machine (test setup only)
    Project.objects.filter(pk=p.pk).update(status=status)
    p.refresh_from_db()
    return p


class ValidTransitionsTest(TestCase):
    def test_draft_to_planning(self):
        p = make_project_in(Project.Status.DRAFT)
        p.transition_status(Project.Status.PLANNING)
        self.assertEqual(p.status, Project.Status.PLANNING)

    def test_planning_to_review(self):
        p = make_project_in(Project.Status.PLANNING)
        p.transition_status(Project.Status.REVIEW)
        self.assertEqual(p.status, Project.Status.REVIEW)

    def test_planning_to_failed(self):
        p = make_project_in(Project.Status.PLANNING)
        p.transition_status(Project.Status.FAILED)
        self.assertEqual(p.status, Project.Status.FAILED)

    def test_review_to_generating(self):
        p = make_project_in(Project.Status.REVIEW)
        p.transition_status(Project.Status.GENERATING)
        self.assertEqual(p.status, Project.Status.GENERATING)

    def test_generating_to_done(self):
        p = make_project_in(Project.Status.GENERATING)
        p.transition_status(Project.Status.DONE)
        self.assertEqual(p.status, Project.Status.DONE)

    def test_generating_to_failed(self):
        p = make_project_in(Project.Status.GENERATING)
        p.transition_status(Project.Status.FAILED)
        self.assertEqual(p.status, Project.Status.FAILED)

    def test_failed_to_generating(self):
        p = make_project_in(Project.Status.FAILED)
        p.transition_status(Project.Status.GENERATING)
        self.assertEqual(p.status, Project.Status.GENERATING)


class InvalidTransitionsTest(TestCase):
    def _assert_raises(self, from_status, to_status):
        p = make_project_in(from_status)
        with self.assertRaises(ValueError):
            p.transition_status(to_status)

    def test_done_to_anything(self):
        for s in [Project.Status.DRAFT, Project.Status.PLANNING,
                  Project.Status.REVIEW, Project.Status.GENERATING,
                  Project.Status.FAILED]:
            with self.subTest(to=s):
                self._assert_raises(Project.Status.DONE, s)

    def test_review_to_failed(self):
        self._assert_raises(Project.Status.REVIEW, Project.Status.FAILED)

    def test_review_to_done(self):
        self._assert_raises(Project.Status.REVIEW, Project.Status.DONE)

    def test_draft_to_done(self):
        self._assert_raises(Project.Status.DRAFT, Project.Status.DONE)

    def test_failed_to_review(self):
        self._assert_raises(Project.Status.FAILED, Project.Status.REVIEW)
```

- [ ] **Step 3: Run tests — expect failure**

```bash
cd backend && uv run python manage.py test tests.test_models_projects tests.test_state_machine --verbosity=2 2>&1
```

Expected: `ModuleNotFoundError: No module named 'apps.projects'`

- [ ] **Step 4: Create the projects app**

Create `backend/apps/projects/__init__.py` (empty).

Write `backend/apps/projects/apps.py`:

```python
from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.projects"
```

Write `backend/apps/projects/models.py`:

```python
import uuid
from django.db import models
from apps.users.models import UserProfile

# Valid status transitions: {from_status: set_of_allowed_to_statuses}
_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT":      {"PLANNING"},
    "PLANNING":   {"REVIEW", "FAILED"},
    "REVIEW":     {"GENERATING"},
    "GENERATING": {"DONE", "FAILED"},
    "FAILED":     {"GENERATING"},
    "DONE":       set(),
}


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT      = "DRAFT"
        PLANNING   = "PLANNING"
        REVIEW     = "REVIEW"
        GENERATING = "GENERATING"
        DONE       = "DONE"
        FAILED     = "FAILED"

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner          = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
                                       related_name="projects", db_index=True)
    prompt         = models.TextField()
    title          = models.CharField(max_length=200, blank=True, default="")
    status         = models.CharField(max_length=20, choices=Status.choices,
                                      default=Status.DRAFT)
    shot_plan      = models.JSONField(null=True, blank=True)
    image_backend  = models.CharField(max_length=50, blank=True, default="")
    animate        = models.BooleanField(default=False)
    narrator_voice = models.CharField(max_length=100, blank=True, default="")
    music          = models.CharField(max_length=200, blank=True, default="")
    error          = models.TextField(blank=True, default="")
    stale          = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    def transition_status(self, new_status: str) -> None:
        allowed = _TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition Project from {self.status!r} to {new_status!r}."
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"Project({self.id}, {self.status})"
```

- [ ] **Step 5: Add `apps.projects` to INSTALLED_APPS**

In `backend/config/settings.py`, update `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "apps.health",
    "apps.users",
    "apps.projects",
]
```

- [ ] **Step 6: Make and apply migration**

```bash
cd backend && uv run python manage.py makemigrations projects
uv run python manage.py migrate
```

Expected:
```
Migrations for 'projects':
  apps/projects/migrations/0001_initial.py
    + Create model Project
```

- [ ] **Step 7: Run tests — expect pass**

```bash
cd backend && uv run python manage.py test tests.test_models_projects tests.test_state_machine --verbosity=2 2>&1
```

Expected: all tests pass, no failures.

---

## Task 3: Scene model

**Files:**
- Modify: `backend/apps/projects/models.py`
- Create: `backend/tests/test_models_scenes.py`

- [ ] **Step 1: Write failing tests**

Write `backend/tests/test_models_scenes.py`:

```python
from django.test import TestCase
from django.db import IntegrityError
from apps.users.models import UserProfile
from apps.projects.models import Project, Scene


def make_project():
    user = UserProfile.objects.create(cognito_sub="sub-scene", email="s@example.com")
    return Project.objects.create(owner=user, prompt="test")


class SceneTest(TestCase):
    def setUp(self):
        self.project = make_project()

    def test_create_scene(self):
        s = Scene.objects.create(project=self.project, index=0)
        self.assertEqual(s.project, self.project)
        self.assertEqual(s.index, 0)
        self.assertEqual(s.image_status, Scene.ImageStatus.PENDING)
        self.assertEqual(s.image_path, "")
        self.assertEqual(s.image_provider, "")

    def test_unique_together_project_index(self):
        Scene.objects.create(project=self.project, index=0)
        with self.assertRaises(IntegrityError):
            Scene.objects.create(project=self.project, index=0)

    def test_cascade_delete_with_project(self):
        Scene.objects.create(project=self.project, index=0)
        pid = self.project.id
        self.project.delete()
        self.assertFalse(Scene.objects.filter(project_id=pid).exists())

    def test_ordering_by_index(self):
        Scene.objects.create(project=self.project, index=2)
        Scene.objects.create(project=self.project, index=0)
        Scene.objects.create(project=self.project, index=1)
        indices = list(Scene.objects.filter(project=self.project).values_list("index", flat=True))
        self.assertEqual(indices, [0, 1, 2])
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend && uv run python manage.py test tests.test_models_scenes --verbosity=2 2>&1
```

Expected: `ImportError` — `cannot import name 'Scene' from 'apps.projects.models'`

- [ ] **Step 3: Add Scene to models.py**

Append to `backend/apps/projects/models.py` (after the Project class):

```python
class Scene(models.Model):
    class ImageStatus(models.TextChoices):
        PENDING    = "PENDING"
        RUNNING    = "RUNNING"
        DONE       = "DONE"
        FAILED     = "FAILED"

    project        = models.ForeignKey(Project, on_delete=models.CASCADE,
                                       related_name="scenes")
    index          = models.IntegerField()
    image_path     = models.CharField(max_length=500, blank=True, default="")
    image_status   = models.CharField(max_length=20, choices=ImageStatus.choices,
                                      default=ImageStatus.PENDING)
    image_provider = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]
```

- [ ] **Step 4: Make and apply migration**

```bash
cd backend && uv run python manage.py makemigrations projects
uv run python manage.py migrate
```

Expected:
```
Migrations for 'projects':
  apps/projects/migrations/0002_scene.py
    + Create model Scene
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd backend && uv run python manage.py test tests.test_models_scenes --verbosity=2 2>&1
```

Expected: all 4 tests pass.

---

## Task 4: JobLog model

**Files:**
- Modify: `backend/apps/projects/models.py`
- Create: `backend/tests/test_models_joblog.py`

- [ ] **Step 1: Write failing tests**

Write `backend/tests/test_models_joblog.py`:

```python
from django.test import TestCase
from apps.users.models import UserProfile
from apps.projects.models import Project, JobLog


def make_project():
    user = UserProfile.objects.create(cognito_sub="sub-log", email="log@example.com")
    return Project.objects.create(owner=user, prompt="test")


class JobLogTest(TestCase):
    def setUp(self):
        self.project = make_project()

    def test_create_log_entry(self):
        log = JobLog.objects.create(
            project=self.project,
            stage="plan",
            level="info",
            message="Shot plan ready.",
        )
        self.assertEqual(log.stage, "plan")
        self.assertEqual(log.level, "info")
        self.assertIsNotNone(log.created_at)

    def test_cascade_delete_with_project(self):
        JobLog.objects.create(project=self.project, stage="plan",
                               level="info", message="ok")
        pid = self.project.id
        self.project.delete()
        self.assertFalse(JobLog.objects.filter(project_id=pid).exists())

    def test_multiple_entries_per_project(self):
        for i in range(3):
            JobLog.objects.create(project=self.project, stage="images",
                                   level="info", message=f"scene {i}")
        self.assertEqual(JobLog.objects.filter(project=self.project).count(), 3)

    def test_ordering_is_chronological(self):
        JobLog.objects.create(project=self.project, stage="plan",
                               level="info", message="first")
        JobLog.objects.create(project=self.project, stage="images",
                               level="info", message="second")
        stages = list(JobLog.objects.filter(project=self.project)
                      .values_list("stage", flat=True))
        self.assertEqual(stages, ["plan", "images"])
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend && uv run python manage.py test tests.test_models_joblog --verbosity=2 2>&1
```

Expected: `ImportError` — `cannot import name 'JobLog' from 'apps.projects.models'`

- [ ] **Step 3: Add JobLog to models.py**

Append to `backend/apps/projects/models.py` (after the Scene class):

```python
class JobLog(models.Model):
    class Level(models.TextChoices):
        INFO  = "info"
        WARN  = "warn"
        ERROR = "error"

    project    = models.ForeignKey(Project, on_delete=models.CASCADE,
                                   related_name="logs")
    stage      = models.CharField(max_length=50)
    level      = models.CharField(max_length=10, choices=Level.choices,
                                  default=Level.INFO)
    message    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
```

- [ ] **Step 4: Make and apply migration**

```bash
cd backend && uv run python manage.py makemigrations projects
uv run python manage.py migrate
```

Expected:
```
Migrations for 'projects':
  apps/projects/migrations/0003_joblog.py
    + Create model JobLog
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd backend && uv run python manage.py test tests.test_models_joblog --verbosity=2 2>&1
```

Expected: all 4 tests pass.

---

## Task 5: Full test suite + clean migration check

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && uv run python manage.py test tests --verbosity=2 2>&1
```

Expected: all tests pass (health + users + projects + scenes + joblogs + state machine). Zero failures.

- [ ] **Step 2: Verify migrations on clean DB**

```bash
cd backend && rm -f db.sqlite3 && uv run python manage.py migrate 2>&1
```

Expected: all migrations apply cleanly from scratch, no errors.

- [ ] **Step 3: Verify manage.py check**

```bash
cd backend && uv run python manage.py check 2>&1
```

Expected: `System check identified no issues (0 silenced).`

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| UserProfile: cognito_sub unique+indexed, email, name, created_at | Task 1 |
| Project: UUID pk, owner FK indexed, all fields, stale defaults False | Task 2 |
| Project.status enum DRAFT→PLANNING→REVIEW→GENERATING→DONE (+FAILED) | Task 2 |
| State-transition table enforced (illegal raises) | Task 2 |
| Scene: project FK, index, image_path, image_status, image_provider | Task 3 |
| Scene unique_together(project, index), ordering by index | Task 3 |
| Scene rows hold image state only (no plan content) | Task 3 (no narration/prompt fields) |
| JobLog: project FK, stage, level, message, created_at, ordering=created_at | Task 4 |
| Deleting Project cascades Scene + JobLog | Tasks 3+4 |
| Migrations apply on clean SQLite | Task 5 |
| shot_plan is single source of truth (D1) | Task 2 (JSON on Project only; Scene has no plan fields) |

### Placeholder scan

None found.

### Type consistency

- `Project.Status.DRAFT/PLANNING/REVIEW/GENERATING/DONE/FAILED` used consistently across models.py, test_models_projects.py, and test_state_machine.py.
- `Scene.ImageStatus.PENDING/RUNNING/DONE/FAILED` defined in models.py and referenced in test_models_scenes.py.
- `make_project()` helper defined independently in each test file (DRY within a file, but test files are meant to be read standalone).
