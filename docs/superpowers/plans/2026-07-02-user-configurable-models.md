# User-Configurable Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let end users configure which AI models they use — the create-video form reads the real DB-backed model catalog instead of hardcoded arrays, users can register their own `model_id` under a provider they hold a key for, and generation stages stop silently falling back to the app's `.env` API keys.

**Architecture:** Three independent slices on top of existing infrastructure (`LLMModel`, `Provider`, `UserAPIKey` already exist and are wired into Celery tasks via `resolve_secure_key`). Backend: add nullable `owner` to `LLMModel`, extend the read-only `LLMModelViewSet` into a create/list/destroy endpoint scoped to the caller, and make `resolve_secure_key` raise instead of silently returning `None`. Frontend: fetch `/api/models/` + `/api/auth/keys/` server-side and pass real data into the existing `ProjectForm`, and add a "Custom Models" panel to the existing Settings page next to `ApiKeysPanel`.

**Tech Stack:** Django 5 / DRF (backend, `backend/apps/projects`, `backend/apps/core`, `backend/apps/accounts`), Next.js App Router / React Server Components (webapp, `webapp/app/(home)`, `webapp/components`), Postgres.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-02-user-configurable-models-design.md` — read it before starting; every task below traces to one of its three Parts.
- The behavior change in Part 3 (no `.env` fallback) is scoped to the webapp/Django dispatch path only — do not touch `pipeline/` provider classes or the standalone CLI (`python -m pipeline.*`).
- Narrator voice / music mood are explicitly out of scope — do not touch `NarratorVoice`/`MusicMood` or the voice/music dropdowns.
- No webapp test suite exists (per `CLAUDE.md`) — frontend tasks are verified manually against a running dev server, not with automated tests.
- Backend tests run with `python manage.py test apps` from `backend/` (uses `config.settings.test`, dummy COGNITO/`FIELD_ENCRYPTION_KEY` values already configured).
- Follow existing patterns exactly: DRF viewsets/mixins style in `apps/projects/views.py`, test helpers in `apps/projects/tests/helpers.py`, the `serverFetch`-in-cookies pattern in `app/(home)/settings/page.tsx`, the `ApiKeysPanel` visual/interaction pattern in `components/settings/api-keys.tsx`.

---

## Task 1: `LLMModel.owner` field — schema + model-level tests

**Files:**
- Modify: `backend/apps/projects/models.py:21-52` (`LLMModel` class)
- Create: `backend/apps/projects/migrations/0007_llmmodel_owner.py`
- Modify: `backend/apps/projects/tests/test_models_llm.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `LLMModel.owner` (nullable FK to `apps.accounts.models.UserProfile`, `related_name="custom_llm_models"`). Global/admin rows have `owner=None`; a user's own rows have `owner=<that user>`. Uniqueness is enforced by two partial constraints — `(provider, capability, model_id)` where `owner IS NULL`, and `(provider, capability, model_id, owner)` where `owner IS NOT NULL` — not a single constraint including `owner`, since SQL treats every `NULL` as distinct and wouldn't stop two global rows from colliding. Task 2 and Task 3 both read `llm.owner_id`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/projects/tests/test_models_llm.py` (after the existing `LLMModelTest` class, before `UserAPIKeyTest`):

```python
class LLMModelOwnershipTest(TestCase):
    def test_two_users_can_register_same_model_id(self):
        p = _provider()
        u1 = UserProfile.objects.create(cognito_sub="u1", email="u1@example.com")
        u2 = UserProfile.objects.create(cognito_sub="u2", email="u2@example.com")
        _llm(provider=p, model_id="custom-1", owner=u1)
        _llm(provider=p, model_id="custom-1", owner=u2)  # must not raise

    def test_user_cannot_duplicate_own_model_id(self):
        p = _provider()
        u1 = UserProfile.objects.create(cognito_sub="u1", email="u1@example.com")
        _llm(provider=p, model_id="custom-1", owner=u1)
        with self.assertRaises(IntegrityError):
            _llm(provider=p, model_id="custom-1", owner=u1)

    def test_owner_null_still_unique_among_global_rows(self):
        p = _provider()
        _llm(provider=p, model_id="global-1")
        with self.assertRaises(IntegrityError):
            _llm(provider=p, model_id="global-1")

    def test_user_row_does_not_collide_with_global_row(self):
        p = _provider()
        u1 = UserProfile.objects.create(cognito_sub="u1", email="u1@example.com")
        _llm(provider=p, model_id="shared-id")  # global, owner=None
        _llm(provider=p, model_id="shared-id", owner=u1)  # must not raise
```

Add the `UserProfile` import at the top of the file (it's already imported at line 7 — confirm, no change needed if so).

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python manage.py test apps.projects.tests.test_models_llm.LLMModelOwnershipTest -v 2
```
Expected: FAIL — `TypeError: LLMModel() got unexpected keyword arguments: 'owner'` (the `_llm()` helper passes `owner` through `**kwargs` to `LLMModel.objects.create`, which doesn't have that field yet).

- [ ] **Step 3: Add the `owner` field and update the constraint**

In `backend/apps/projects/models.py`, add the import and field:

```python
from apps.accounts.models import UserProfile
```

(add this near the top with the other `from apps.accounts.models import UserProfile` — it's already imported at line 5, no new import needed.)

Replace the `LLMModel` class body (lines 21-49) with:

```python
class LLMModel(TimestampMixin):
    provider     = models.ForeignKey(
        "core.Provider", on_delete=models.PROTECT, related_name="llm_models",
    )
    capability   = models.CharField(max_length=10, choices=Capability.choices, db_index=True)
    model_id     = models.CharField(max_length=100)
    display_name = models.CharField(max_length=150)
    is_free      = models.BooleanField(default=False)
    is_default   = models.BooleanField(default=False)
    is_active    = models.BooleanField(default=True, db_index=True)
    owner        = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        null=True, blank=True, related_name="custom_llm_models",
    )

    class Meta:
        verbose_name = "LLM Model"
        verbose_name_plural = "LLM Models"
        constraints = [
            # A plain multi-column UniqueConstraint doesn't work here: SQL treats
            # every NULL as distinct, so two admin rows (owner=NULL) with the same
            # (provider, capability, model_id) would never collide. Two partial
            # constraints instead — one scoped to global rows, one to owned rows.
            models.UniqueConstraint(
                fields=["provider", "capability", "model_id"],
                condition=models.Q(owner__isnull=True),
                name="unique_global_provider_capability_model",
            ),
            models.UniqueConstraint(
                fields=["provider", "capability", "model_id", "owner"],
                condition=models.Q(owner__isnull=False),
                name="unique_owned_provider_capability_model",
            ),
        ]
        ordering = ["-is_default", "-is_free", "display_name"]

    def save(self, **kwargs):
        with transaction.atomic():
            if self.is_default:
                LLMModel.objects.select_for_update().filter(
                    capability=self.capability, is_default=True,
                ).exclude(pk=self.pk).update(is_default=False)
            super().save(**kwargs)

    def __str__(self):
        return f"{self.display_name} ({self.provider.code})"
```

- [ ] **Step 4: Generate and inspect the migration**

```bash
cd backend && python manage.py makemigrations projects
```

Expected output names a new file `apps/projects/migrations/0007_llmmodel_owner.py`. Open it and confirm it contains a `RemoveConstraint` for `unique_provider_capability_model`, an `AddField` for `owner`, and an `AddConstraint` for the two partial constraints described in Step 3 above, with `dependencies` including `("accounts", "0002_add_user_api_key")`. If Django named the file differently, rename it to `0007_llmmodel_owner.py` for consistency with the numbering already in the directory (`0006_joblog_project_id_index.py` is the current head).

> **What actually happened during implementation:** the single-constraint design was tried first (matching an earlier draft of this plan), applied to the local dev DB, and only then caught by the `test_owner_null_still_unique_among_global_rows` test failing. Since the migration had already been applied to a DB with real local data, the fix landed as a second migration, `0008_llmmodel_owner_partial_constraints.py` (`RemoveConstraint` of the old single constraint + `AddConstraint` of the two partial ones), rather than editing the already-applied `0007`. Either a single correct migration (if you catch this before applying `0007`) or the two-migration split (if you don't) is fine — just don't hand-edit a migration that's already been applied to a DB with real data.

- [ ] **Step 5: Apply the migration and run tests to verify they pass**

```bash
cd backend && python manage.py migrate projects
python manage.py test apps.projects.tests.test_models_llm -v 2
```
Expected: all tests in `test_models_llm.py` PASS, including the four new `LLMModelOwnershipTest` cases.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/projects/models.py backend/apps/projects/migrations/0007_llmmodel_owner.py backend/apps/projects/tests/test_models_llm.py
git commit -m "feat: add owner to LLMModel for user-registered custom models"
```

---

## Task 2: `LLMModelViewSet` create/destroy — API layer

**Files:**
- Modify: `backend/apps/projects/serializers.py:82-91` (`LLMModelSerializer`)
- Modify: `backend/apps/projects/views.py:396-405` (`LLMModelViewSet`)
- Create: `backend/apps/projects/tests/test_views_llmmodel.py`

**Interfaces:**
- Consumes: `LLMModel.owner` (Task 1), `UserAPIKey` (`apps.accounts.models`, existing).
- Produces: `GET/POST/DELETE /api/models/`. `GET` (list, unchanged URL, now includes the caller's own rows), `POST` (new — body `{provider: <int PK>, capability: "plan"|"image"|"video", model_id: str, display_name: str}`, 201 on success, 400 if no matching `UserAPIKey`), `DELETE /api/models/{id}/` (new — 204 own row, 403 global/other-user row). Response shape unchanged for existing fields: `{id, model_id, display_name, provider: <code str>, capability, is_free, is_default, owned: bool}` — `owned` is new.

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/projects/tests/test_views_llmmodel.py`:

```python
from django.test import TestCase

from apps.accounts.models import UserAPIKey, UserProfile
from apps.core.models import Provider
from apps.projects.choices import Capability
from apps.projects.models import LLMModel


def _user(sub="owner-sub"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@example.com")


def _provider(code="openai", name="OpenAI"):
    return Provider.objects.create(code=code, name=name)


def _key(user, provider):
    key = UserAPIKey(owner=user, provider=provider)
    key.set_api_key("sk-test-key-12345678")
    key.save()
    return key


class LLMModelViewSetTest(TestCase):
    def setUp(self):
        self.user = _user("owner-sub")
        self.provider = _provider()
        self.url = "/api/models/"

    def _login_as(self, sub):
        session = self.client.session
        session["cognito_sub"] = sub
        session.save()

    def test_unauthenticated_cannot_list(self):
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, (401, 403))

    def test_list_includes_global_and_own_rows_only(self):
        other = _user("other-sub")
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="global-model", display_name="Global",
        )
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="mine", display_name="Mine", owner=self.user,
        )
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="theirs", display_name="Theirs", owner=other,
        )
        self._login_as("owner-sub")
        resp = self.client.get(self.url)
        model_ids = {row["model_id"] for row in resp.json()}
        self.assertEqual(model_ids, {"global-model", "mine"})

    def test_list_marks_owned_flag(self):
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="mine", display_name="Mine", owner=self.user,
        )
        self._login_as("owner-sub")
        resp = self.client.get(self.url)
        row = resp.json()[0]
        self.assertTrue(row["owned"])

    def test_create_requires_matching_api_key(self):
        self._login_as("owner-sub")
        resp = self.client.post(self.url, {
            "provider": self.provider.id, "capability": "image",
            "model_id": "custom-1", "display_name": "Custom One",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(LLMModel.objects.filter(model_id="custom-1").exists())

    def test_create_succeeds_with_api_key(self):
        _key(self.user, self.provider)
        self._login_as("owner-sub")
        resp = self.client.post(self.url, {
            "provider": self.provider.id, "capability": "image",
            "model_id": "custom-1", "display_name": "Custom One",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        row = LLMModel.objects.get(model_id="custom-1")
        self.assertEqual(row.owner, self.user)
        self.assertFalse(row.is_free)
        self.assertFalse(row.is_default)
        self.assertEqual(resp.json()["provider"], "openai")

    def test_delete_own_row_succeeds(self):
        _key(self.user, self.provider)
        row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="mine", display_name="Mine", owner=self.user,
        )
        self._login_as("owner-sub")
        resp = self.client.delete(f"{self.url}{row.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(LLMModel.objects.filter(pk=row.pk).exists())

    def test_delete_global_row_forbidden(self):
        row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="global-model", display_name="Global",
        )
        self._login_as("owner-sub")
        resp = self.client.delete(f"{self.url}{row.id}/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(LLMModel.objects.filter(pk=row.pk).exists())

    def test_delete_other_users_row_not_found(self):
        other = _user("other-sub")
        row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="theirs", display_name="Theirs", owner=other,
        )
        self._login_as("owner-sub")
        resp = self.client.delete(f"{self.url}{row.id}/")
        self.assertIn(resp.status_code, (403, 404))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python manage.py test apps.projects.tests.test_views_llmmodel -v 2
```
Expected: FAIL — `test_create_requires_matching_api_key` and friends get 405 (Method Not Allowed) since `LLMModelViewSet` is currently `ReadOnlyModelViewSet`; `test_list_marks_owned_flag` gets `KeyError: 'owned'`.

- [ ] **Step 3: Update the serializer**

In `backend/apps/projects/serializers.py`, add the import at the top (line 7 area, alongside the existing `from apps.projects.models import ...`):

```python
from apps.core.models import Provider
```

Replace `LLMModelSerializer` (lines 82-91) with:

```python
class LLMModelSerializer(serializers.ModelSerializer):
    provider = serializers.PrimaryKeyRelatedField(
        queryset=Provider.objects.filter(is_active=True),
    )
    owned = serializers.SerializerMethodField()

    class Meta:
        model = LLMModel
        fields = [
            "id", "model_id", "display_name", "provider",
            "capability", "is_free", "is_default", "owned",
        ]
        read_only_fields = ["id", "is_free", "is_default", "owned"]

    def get_owned(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.owner_id == request.user.id)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["provider"] = instance.provider.code
        return rep
```

- [ ] **Step 4: Update the viewset**

In `backend/apps/projects/views.py`, add imports near the top (with the other `rest_framework` imports, line 8-12 area):

```python
from rest_framework import mixins
from rest_framework.exceptions import PermissionDenied, ValidationError
```

Add this import near line 32-33 (with the other `apps.accounts`/`apps.projects` imports):

```python
from apps.accounts.models import UserAPIKey
```

Replace `LLMModelViewSet` (lines 396-405) with:

```python
class LLMModelViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = LLMModelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = LLMModel.objects.filter(is_active=True).filter(
            models.Q(owner__isnull=True) | models.Q(owner=self.request.user)
        ).select_related("provider")
        capability = self.request.query_params.get("capability")
        if capability:
            qs = qs.filter(capability=capability)
        return qs

    def perform_create(self, serializer):
        provider = serializer.validated_data["provider"]
        if not UserAPIKey.objects.filter(owner=self.request.user, provider=provider).exists():
            raise ValidationError({"provider": "Add an API key for this provider first."})
        serializer.save(owner=self.request.user, is_free=False, is_default=False, is_active=True)

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied("Cannot delete a model you don't own.")
        instance.delete()
```

`models.Q` needs `from django.db import models` — check line 4 of `views.py`; it currently imports `from django.db import transaction`. Change that line to:

```python
from django.db import models, transaction
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python manage.py test apps.projects.tests.test_views_llmmodel apps.projects.tests.test_models_llm -v 2
```
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite to check for regressions**

```bash
cd backend && python manage.py test apps -v 1
```
Expected: PASS (this also catches any other place that assumed `LLMModelViewSet` was read-only or that `LLMModelSerializer.provider` was a plain string — grep first if anything fails).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/projects/serializers.py backend/apps/projects/views.py backend/apps/projects/tests/test_views_llmmodel.py
git commit -m "feat: let users create and delete their own LLM models via /api/models/"
```

---

## Task 3: Remove silent `.env` key fallback

**Files:**
- Modify: `backend/apps/projects/utils.py:59-65` (`resolve_secure_key`)
- Modify: `backend/apps/projects/tasks.py:73-81` (log line cleanup)
- Modify: `backend/apps/projects/tests/test_tasks_plan.py` (update `test_happy_path`, add key-required test)
- Modify: `backend/apps/projects/tests/test_tasks_video.py` (update happy-path test to create a key, add key-required test)
- Modify: `backend/apps/projects/tests/test_utils.py` (add `MissingAPIKeyError` tests for `resolve_secure_key`)

**Interfaces:**
- Consumes: `UserAPIKey` (existing).
- Produces: `apps.projects.utils.MissingAPIKeyError` (new exception, subclass of `Exception`). `resolve_secure_key(owner, provider)` now always returns a `SecureString` or raises `MissingAPIKeyError` — it never returns `None`. Every existing caller (`tasks.py` plan/refine stages, `utils.py` `generate_scene`/`animate_scene`) already wraps its call in `except Exception` → `fail_project`/scene-failure handling, so no call-site logic changes beyond the log line in Step 3 below.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/projects/tests/test_utils.py`:

```python
from apps.accounts.models import UserAPIKey, UserProfile
from apps.core.models import Provider
from apps.projects.utils import MissingAPIKeyError, resolve_secure_key


class ResolveSecureKeyTest(TestCase):
    def setUp(self):
        self.user = UserProfile.objects.create(cognito_sub="rsk-sub", email="rsk@example.com")
        self.provider = Provider.objects.create(code="openai", name="OpenAI")

    def test_raises_when_no_key_configured(self):
        with self.assertRaises(MissingAPIKeyError):
            resolve_secure_key(self.user, self.provider)

    def test_returns_secure_key_when_configured(self):
        key = UserAPIKey(owner=self.user, provider=self.provider)
        key.set_api_key("sk-test-key-12345678")
        key.save()
        result = resolve_secure_key(self.user, self.provider)
        self.assertEqual(result.decrypt(), "sk-test-key-12345678")
```

(`TestCase` is already imported at the top of `test_utils.py`; add the three new imports above it.)

Update `backend/apps/projects/tests/test_tasks_plan.py`'s `test_happy_path` (lines 46-63) — it currently asserts `api_key=None`, which will now raise before `mock_gen` is even called. Replace the method body with:

```python
    def test_happy_path(self, mock_gen, mock_polish, mock_review):
        plan = _fake_shot_plan(3)
        mock_gen.return_value = plan
        mock_polish.return_value = plan
        mock_review.return_value = plan

        llm = _make_plan_model()
        project = make_project(plan_model=llm)
        api_key = UserAPIKey(owner=project.owner, provider=llm.provider)
        api_key.set_api_key("sk-test-key-12345678")
        api_key.save()

        run_plan_stage(project.id)

        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args.kwargs
        self.assertEqual(call_kwargs["model"], llm.model_id)
        self.assertEqual(call_kwargs["provider"], llm.provider.code)
        self.assertEqual(call_kwargs["api_key"].decrypt(), "sk-test-key-12345678")
        project.refresh_from_db()
        self.assertEqual(project.status, Status.REVIEW)
        self.assertEqual(project.title, "Test Video")
        self.assertEqual(Scene.objects.filter(project=project).count(), 3)

    def test_happy_path_without_key_fails_project(self, mock_gen, mock_polish, mock_review):
        plan = _fake_shot_plan(3)
        mock_gen.return_value = plan
        mock_polish.return_value = plan
        mock_review.return_value = plan

        llm = _make_plan_model()
        project = make_project(plan_model=llm)

        run_plan_stage(project.id)

        mock_gen.assert_not_called()
        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
        self.assertIn("MissingAPIKeyError", project.error)
```

Add `from apps.accounts.models import UserAPIKey` to the imports at the top of `test_tasks_plan.py` if not already present (it isn't — only `apps.core.models.Provider` and `apps.projects.*` are imported).

Update `backend/apps/projects/tests/test_tasks_video.py`'s `test_animates_scene_and_marks_done` (lines 71-105) to add a `UserAPIKey` the same way `test_animates_scene_with_user_api_key` already does — insert before `run_video_stage(str(project.id))`:

```python
        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)
        api_key = UserAPIKey(owner=project.owner, provider=vm.provider)
        api_key.set_api_key("sk-test-dashscope-key12")
        api_key.save()

        run_video_stage(str(project.id))

        mock_submit.assert_called_once()
        mock_poll.assert_called_with("task_abc123", api_key.get_secure_key())
```

(this replaces the existing `vm = _make_video_model()` / `project = _make_animated_project(...)` / `run_video_stage(...)` / `mock_poll.assert_called_with("task_abc123", None)` lines in that test.)

Add a new test class at the end of `test_tasks_video.py`:

```python
class RunVideoStageMissingKeyTest(TestCase):
    @patch("apps.projects.utils._motion_prompt", return_value="prompt")
    @patch("pipeline.video.wan.WanProvider.submit")
    @patch("apps.projects.utils.storage_provider")
    @patch("apps.projects.utils.time")
    def test_no_key_marks_scene_failed(self, mock_time, mock_storage, mock_submit, mock_motion):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG\r\n\x1a\n"
        mock_storage.storage.open.return_value = mock_file

        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)

        run_video_stage(str(project.id))

        mock_submit.assert_not_called()
        animated = Scene.objects.get(project=project, index=0)
        self.assertEqual(animated.media_status, MediaStatus.FAILED)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python manage.py test apps.projects.tests.test_utils apps.projects.tests.test_tasks_plan apps.projects.tests.test_tasks_video -v 2
```
Expected: FAIL — `ImportError: cannot import name 'MissingAPIKeyError'` from `test_utils.py`, and the plan/video tests fail their new assertions (`test_happy_path_without_key_fails_project` currently succeeds with `api_key=None` instead of failing; `test_no_key_marks_scene_failed` currently calls `submit` with `None` instead of skipping it).

- [ ] **Step 3: Implement `MissingAPIKeyError`**

In `backend/apps/projects/utils.py`, replace `resolve_secure_key` (lines 59-65) with:

```python
class MissingAPIKeyError(Exception):
    """Raised when a project's owner has no API key configured for a required provider."""


def resolve_secure_key(owner, provider):
    try:
        return UserAPIKey.objects.get(
            owner=owner, provider=provider,
        ).get_secure_key()
    except UserAPIKey.DoesNotExist:
        raise MissingAPIKeyError(
            f"No API key configured for {provider.name} — add one in Settings."
        )
```

In `backend/apps/projects/tasks.py`, simplify the log call at lines 76-81 (remove the dead `"db" if secure_key else "env-fallback"` branch, since `secure_key` can no longer be falsy at this point without having already raised):

```python
        logger.info(
            "Plan stage — model=%s, provider=%s, style=%s",
            model_id, provider_code, project.style or "none",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python manage.py test apps.projects.tests.test_utils apps.projects.tests.test_tasks_plan apps.projects.tests.test_tasks_video -v 2
```
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite to check for regressions**

```bash
cd backend && python manage.py test apps -v 1
```
Expected: PASS. If any other test relied on `resolve_secure_key` returning `None` without a key (grep `resolve_secure_key\|generate_scene\|animate_scene` under `apps/projects/tests/` first — Task-writing research found only the files already touched above, but re-check since code may have moved), fix it the same way: create a `UserAPIKey` in setup, or assert the `MissingAPIKeyError` failure path.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/projects/utils.py backend/apps/projects/tasks.py backend/apps/projects/tests/test_utils.py backend/apps/projects/tests/test_tasks_plan.py backend/apps/projects/tests/test_tasks_video.py
git commit -m "fix: require a user API key for plan/image/video generation, no env fallback"
```

---

## Task 4: Frontend — create-video form uses the real model catalog

**Files:**
- Modify: `webapp/components/home/create-video-section.tsx`
- Modify: `webapp/components/home/project-form.tsx`

**Interfaces:**
- Consumes: `GET /api/models/?capability=image`, `GET /api/models/?capability=video`, `GET /api/auth/keys/` (all existing/Task-2-extended endpoints), the `serverFetch`-with-cookie pattern already in `webapp/app/(home)/settings/page.tsx`.
- Produces: `ProjectForm` now takes props `imageModels: LLMModel[]`, `videoModels: LLMModel[]`, `userKeys: ApiKey[]` (reusing the `ApiKey`/`Provider` shape from `components/settings/api-keys.tsx` — `ApiKey.provider` is the numeric provider PK, but `LLMModel.provider` from `/api/models/` is the provider *code* string, so the form must resolve one to the other via the provider list — see Step 3).

- [ ] **Step 1: Manually verify current behavior before changing it**

```bash
cd backend && python manage.py runserver &
cd webapp && npm run dev &
```
Open `http://localhost:3000/home`, confirm the "Create a video" form currently shows the hardcoded `IMAGE_MODELS`/`VIDEO_MODELS` options regardless of whether you have any API keys configured in Settings. This is the behavior Step 2-4 replace.

- [ ] **Step 2: Make `CreateVideoSection` an async Server Component**

Replace `webapp/components/home/create-video-section.tsx` entirely:

```tsx
import { cookies } from 'next/headers'
import ProjectForm from './project-form'
import type { ApiKey } from '@/components/settings/api-keys'

const DJANGO_ORIGIN = (process.env.DJANGO_ORIGIN ?? 'http://localhost:8000').replace(/\/$/, '')

export interface LLMModel {
  id: number
  model_id: string
  display_name: string
  provider: string
  capability: string
  is_free: boolean
  is_default: boolean
  owned: boolean
}

export interface CoreProvider {
  id: number
  code: string
  name: string
}

async function serverFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies()
  const session = cookieStore.get('sessionid')
  const res = await fetch(`${DJANGO_ORIGIN}${path}`, {
    headers: session ? { Cookie: `sessionid=${session.value}` } : {},
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`${path} responded ${res.status}`)
  return res.json() as Promise<T>
}

export default async function CreateVideoSection() {
  const [imageModels, videoModels, userKeys, providers] = await Promise.all([
    serverFetch<LLMModel[]>('/api/models/?capability=image'),
    serverFetch<LLMModel[]>('/api/models/?capability=video'),
    serverFetch<ApiKey[]>('/api/auth/keys/'),
    serverFetch<CoreProvider[]>('/api/core/providers/'),
  ])

  return (
    <section>
      <h2 className="text-lg font-semibold text-[#e7e9ee] mb-1">Create a video</h2>
      <p className="text-sm text-[#9aa3b2] mb-4">
        Describe an idea. We&apos;ll write a shot plan you can review and refine before anything is generated.
      </p>
      <ProjectForm
        imageModels={imageModels}
        videoModels={videoModels}
        userKeys={userKeys}
        providers={providers}
      />
    </section>
  )
}
```

- [ ] **Step 3: Rewrite `ProjectForm` to consume real data**

In `webapp/components/home/project-form.tsx`:

Remove the `IMAGE_MODELS` and `VIDEO_MODELS` constants (lines 7-19). Keep `VOICES` and `MUSIC_MOODS` unchanged.

Add near the top, after the existing imports:

```tsx
import Link from 'next/link'
import type { LLMModel, CoreProvider } from './create-video-section'
import type { ApiKey } from '@/components/settings/api-keys'

interface ProjectFormProps {
  imageModels: LLMModel[]
  videoModels: LLMModel[]
  userKeys: ApiKey[]
  providers: CoreProvider[]
}
```

Change the component signature and add the filtering logic — replace:

```tsx
export default function ProjectForm() {
```

with:

```tsx
export default function ProjectForm({ imageModels, videoModels, userKeys, providers }: ProjectFormProps) {
```

Right after the existing `useState` declarations (after line 48, before `handleSubmit`), add:

```tsx
  const providerCodeById = new Map(providers.map(p => [p.id, p.code]))
  const keyedProviderCodes = new Set(userKeys.map(k => providerCodeById.get(k.provider)).filter(Boolean))
  const selectableImageModels = imageModels.filter(m => keyedProviderCodes.has(m.provider))
  const selectableVideoModels = videoModels.filter(m => keyedProviderCodes.has(m.provider))
```

Update the `imageModel`/`videModel` initial state (lines 42-43) to default to the first selectable model instead of a hardcoded id:

```tsx
  const [imageModel, setImageModel] = useState(selectableImageModels[0]?.model_id ?? '')
  const [videModel, setVideModel] = useState(selectableVideoModels[0]?.model_id ?? '')
```

Replace the image-model `<select>` block (the `IMAGE_MODELS.map` one, lines 112-123) with:

```tsx
        <div>
          <label className="block text-xs text-[#9aa3b2] mb-1.5">Image model</label>
          {selectableImageModels.length > 0 ? (
            <select
              value={imageModel}
              onChange={e => setImageModel(e.target.value)}
              className={SELECT_CLASS}
            >
              {selectableImageModels.map(opt => (
                <option key={opt.id} value={opt.model_id}>
                  {opt.display_name}{opt.is_free ? ' — free' : ''}
                </option>
              ))}
            </select>
          ) : (
            <p className="text-xs text-[#9aa3b2]">
              <Link href="/settings" className="text-[#6ea8fe] hover:underline">Add an API key</Link> to unlock image models.
            </p>
          )}
        </div>
```

Replace the video-model `<select>` block (lines 124-135) the same way:

```tsx
        <div>
          <label className="block text-xs text-[#9aa3b2] mb-1.5">Video model</label>
          {selectableVideoModels.length > 0 ? (
            <select
              value={videModel}
              onChange={e => setVideModel(e.target.value)}
              className={SELECT_CLASS}
            >
              {selectableVideoModels.map(opt => (
                <option key={opt.id} value={opt.model_id}>
                  {opt.display_name}{opt.is_free ? ' — free' : ''}
                </option>
              ))}
            </select>
          ) : (
            <p className="text-xs text-[#9aa3b2]">
              <Link href="/settings" className="text-[#6ea8fe] hover:underline">Add an API key</Link> to unlock video models.
            </p>
          )}
        </div>
```

- [ ] **Step 4: Manually verify**

With the dev servers still running (Step 1), and starting from a user account with **no** API keys configured in Settings:
1. Reload `http://localhost:3000/home` — the Image model and Video model fields should show the "Add an API key to unlock…" message linking to `/settings`, instead of a dropdown.
2. Go to `/settings`, add an API key for a provider that has at least one seeded `LLMModel` (e.g. run `python manage.py seed_providers` in `backend/` first if the catalog is empty, then add a key for `dashscope` or `openai`).
3. Return to `/home` — the corresponding dropdown(s) should now list that provider's models.
4. Submit the form and confirm project creation still works (`POST /api/projects/` still receives `image_model`/`video_model` as the `model_id` string, unchanged from before).

- [ ] **Step 5: Commit**

```bash
git add webapp/components/home/create-video-section.tsx webapp/components/home/project-form.tsx
git commit -m "feat: create-video form reads the real model catalog, gated by user API keys"
```

---

## Task 5: Frontend — "Custom Models" panel in Settings

**Files:**
- Create: `webapp/components/settings/custom-models.tsx`
- Modify: `webapp/app/(home)/settings/page.tsx`

**Interfaces:**
- Consumes: `GET /api/models/` (all capabilities, Task 2), `POST /api/models/` (Task 2), `DELETE /api/models/{id}/` (Task 2), `GET /api/auth/keys/` + `GET /api/core/providers/` (already fetched in `settings/page.tsx`).
- Produces: nothing consumed by other tasks — this is the final leaf of the plan.

- [ ] **Step 1: Manually verify current Settings page**

With the dev servers running, open `http://localhost:3000/settings` and confirm only the "API Keys" section exists today.

- [ ] **Step 2: Build the `CustomModelsPanel` component**

Create `webapp/components/settings/custom-models.tsx`:

```tsx
'use client'

import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { ApiKey, Provider } from './api-keys'

export interface LLMModel {
  id: number
  model_id: string
  display_name: string
  provider: string
  capability: string
  is_free: boolean
  is_default: boolean
  owned: boolean
}

interface Props {
  initialModels: LLMModel[]
  keys: ApiKey[]
  providers: Provider[]
}

const inputCls =
  'bg-[#0a0d14] border border-[#2a2f3a] rounded px-3 py-2 text-sm w-full text-[#e7e9ee] placeholder-[#5a6275] focus:outline-none focus:border-[#6ea8fe] transition-colors'

const ghostBtn =
  'text-xs border-[#2a2f3a] text-[#e7e9ee] bg-transparent hover:bg-[#1e222b]'

const CAPABILITIES = [
  { value: 'plan', label: 'Plan' },
  { value: 'image', label: 'Image' },
  { value: 'video', label: 'Video' },
]

export function CustomModelsPanel({ initialModels, keys, providers }: Props) {
  const [models, setModels] = useState<LLMModel[]>(initialModels.filter(m => m.owned))
  const [adding, setAdding] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ provider: '', capability: 'image', model_id: '', display_name: '' })

  const providerMap = useMemo(() => new Map(providers.map(p => [p.id, p.name])), [providers])
  const keyedProviderIds = useMemo(() => new Set(keys.map(k => k.provider)), [keys])
  const keyedProviders = useMemo(
    () => providers.filter(p => keyedProviderIds.has(p.id)),
    [providers, keyedProviderIds],
  )

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    const res = await fetch('/api/models/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: Number(form.provider),
        capability: form.capability,
        model_id: form.model_id,
        display_name: form.display_name,
      }),
    })
    if (!res.ok) {
      setError('Something went wrong. Check the fields and try again.')
      return
    }
    const created: LLMModel = await res.json()
    setModels(prev => [...prev, created])
    setAdding(false)
    setForm({ provider: '', capability: 'image', model_id: '', display_name: '' })
  }

  async function handleDelete(id: number) {
    setError('')
    const res = await fetch(`/api/models/${id}/`, { method: 'DELETE' })
    if (!res.ok) { setError('Something went wrong. Try again.'); return }
    setModels(prev => prev.filter(m => m.id !== id))
  }

  const isEmpty = models.length === 0 && !adding

  return (
    <div className="rounded-lg border border-[#2a2f3a] overflow-hidden">
      {isEmpty && (
        <div className="flex flex-col items-center gap-3 py-10 px-5 text-center">
          <p className="text-sm text-[#9aa3b2]">No custom models yet.</p>
          <p className="text-xs text-[#5a6275] max-w-xs">
            Register a model_id under a provider you&apos;ve added a key for.
          </p>
          {keyedProviders.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => { setAdding(true); setError('') }} className={ghostBtn}>
              + Add custom model
            </Button>
          )}
        </div>
      )}

      {models.map(m => (
        <div key={m.id} className="border-b border-[#2a2f3a] last:border-b-0 px-5 py-4 flex items-center gap-4">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[#e7e9ee]">{m.display_name}</p>
            <p className="text-xs text-[#5a6275] mt-1">{m.provider} · {m.capability} · {m.model_id}</p>
          </div>
          {confirmDeleteId === m.id ? (
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="text-xs text-[#9aa3b2]">Delete?</span>
              <Button variant="outline" size="sm" onClick={() => handleDelete(m.id)}
                className="text-xs border-red-800 text-red-400 bg-transparent hover:bg-red-950">Yes</Button>
              <Button variant="outline" size="sm" onClick={() => setConfirmDeleteId(null)} className={ghostBtn}>No</Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setConfirmDeleteId(m.id)}
              className="text-xs border-[#2a2f3a] text-red-400 bg-transparent hover:bg-[#1e222b] hover:text-red-300">
              Delete
            </Button>
          )}
        </div>
      ))}

      {adding ? (
        <form onSubmit={handleAdd} className={`${models.length > 0 ? 'border-t border-[#2a2f3a]' : ''} px-5 py-4 flex flex-col gap-3`}>
          <select required value={form.provider} onChange={e => setForm(f => ({ ...f, provider: e.target.value }))} className={inputCls}>
            <option value="">Select provider…</option>
            {keyedProviders.map(p => <option key={p.id} value={p.id}>{providerMap.get(p.id)}</option>)}
          </select>
          <select required value={form.capability} onChange={e => setForm(f => ({ ...f, capability: e.target.value }))} className={inputCls}>
            {CAPABILITIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          <input required type="text" placeholder="model_id (e.g. gpt-4o-mini-ft-xyz)" value={form.model_id}
            onChange={e => setForm(f => ({ ...f, model_id: e.target.value }))} className={inputCls} />
          <input required type="text" placeholder="Display name" value={form.display_name}
            onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} className={inputCls} />
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2">
            <Button type="submit" size="sm">Add model</Button>
            <Button type="button" variant="outline" size="sm" onClick={() => { setAdding(false); setError('') }} className={ghostBtn}>Cancel</Button>
          </div>
        </form>
      ) : !isEmpty && keyedProviders.length > 0 ? (
        <div className="border-t border-[#2a2f3a] px-5 py-3">
          <Button variant="outline" size="sm" onClick={() => { setAdding(true); setError('') }} className={ghostBtn}>
            + Add custom model
          </Button>
        </div>
      ) : null}

      {!adding && error && <p className="text-red-400 text-xs px-5 pb-4">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 3: Wire it into the Settings page**

Replace `webapp/app/(home)/settings/page.tsx` entirely:

```tsx
import { cookies } from 'next/headers'
import { ApiKeysPanel, type ApiKey, type Provider } from '@/components/settings/api-keys'
import { CustomModelsPanel, type LLMModel } from '@/components/settings/custom-models'

const DJANGO_ORIGIN = (process.env.DJANGO_ORIGIN ?? 'http://localhost:8000').replace(/\/$/, '')

async function serverFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies()
  const session = cookieStore.get('sessionid')
  const res = await fetch(`${DJANGO_ORIGIN}${path}`, {
    headers: session ? { Cookie: `sessionid=${session.value}` } : {},
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`${path} responded ${res.status}`)
  return res.json() as Promise<T>
}

export default async function SettingsPage() {
  const [initialKeys, providers, initialModels] = await Promise.all([
    serverFetch<ApiKey[]>('/api/auth/keys/'),
    serverFetch<Provider[]>('/api/core/providers/'),
    serverFetch<LLMModel[]>('/api/models/'),
  ])

  return (
    <div className="max-w-xl">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-[#e7e9ee]">Settings</h1>
        <p className="text-sm text-[#5a6275] mt-1">Manage your provider API keys and account preferences.</p>
      </div>
      <section className="mb-8">
        <h2 className="text-xs font-medium text-[#9aa3b2] uppercase tracking-widest mb-3">
          API Keys
        </h2>
        <ApiKeysPanel initialKeys={initialKeys} providers={providers} />
      </section>
      <section>
        <h2 className="text-xs font-medium text-[#9aa3b2] uppercase tracking-widest mb-3">
          Custom Models
        </h2>
        <CustomModelsPanel initialModels={initialModels} keys={initialKeys} providers={providers} />
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Manually verify**

With dev servers running and at least one API key already configured (from Task 4's verification):
1. Open `/settings` — confirm the new "Custom Models" section appears below "API Keys", showing its empty state with "+ Add custom model" enabled (since you have a key).
2. Click it, fill in provider/capability/model_id/display name, submit — confirm the new row appears in the list.
3. Reload the page — confirm the custom model persists (fetched from the DB via `serverFetch`).
4. Go back to `/home` — if the custom model's capability is `image` or `video`, confirm it now appears in the corresponding dropdown in the create-video form (proves Task 4's provider-filter picks up newly-created rows too, since it's provider-code-based, not row-specific).
5. Delete the custom model from Settings, confirm it disappears from both Settings and the create-video form.
6. Confirm a *global* (admin-seeded) model in the list has no delete button (only `owned: true` rows should show one — verify by checking the component only renders rows from `initialModels.filter(m => m.owned)`, so seeded rows never appear here at all, which is correct: this panel is for custom models only, not a general catalog browser).

- [ ] **Step 5: Commit**

```bash
git add webapp/components/settings/custom-models.tsx webapp/app/\(home\)/settings/page.tsx
git commit -m "feat: add Custom Models panel to Settings page"
```

---

## Final check

- [ ] Run the full backend suite once more from a clean state: `cd backend && python manage.py test apps -v 1` — expect PASS.
- [ ] Re-read `docs/superpowers/specs/2026-07-02-user-configurable-models-design.md` Parts 1-3 against the five tasks above — confirm every bullet has a corresponding step (frontend filter logic → Task 4 Step 3; custom model registration → Task 2 + Task 5; env-fallback removal → Task 3).
- [ ] Confirm `.env`'s `OPENAI_API_KEY`/`DASHSCOPE_API_KEY` are still present and untouched — they remain load-bearing for the standalone CLI pipeline, only the webapp path stopped reading them.
