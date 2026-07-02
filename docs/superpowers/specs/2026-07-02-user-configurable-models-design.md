# User-Configurable Models — Design Spec
Date: 2026-07-02

## Problem
Plan/image/video model options are hardcoded twice — once in `webapp/components/home/project-form.tsx`
(frontend arrays) and once in `apps/projects/management/commands/seed_providers.py` (DB seed) — and
they've already drifted (form is missing/has stale entries vs the DB catalog). Separately, BYO API
keys (`UserAPIKey`, Settings page) already exist and are wired into generation via `resolve_secure_key`,
but that function silently falls back to the app's `.env` key when a user has none — so "bring your
own key" isn't actually enforced, and users can't register a model outside the admin-curated catalog.

## Scope
1. Wire the project-creation form to the existing `GET /api/models/` catalog instead of hardcoded arrays.
2. Let a user register their own `model_id` under a provider they hold a key for.
3. Remove the silent `.env` fallback for providers that require a key, in the webapp/Django dispatch
   path only.

Out of scope: narrator voice / music mood (stay as hardcoded `TextChoices` — confirmed with user),
the standalone CLI pipeline (`python -m pipeline.*`, no `owner` concept, keeps using `.env` as today),
plan-model picker in the create form (not present today, not added here), billing/usage metering.

---

## Part 1 — Frontend uses the real model catalog

### Backend
No changes — `GET /api/models/?capability=image|video` (`apps/projects/views.py:396`,
`LLMModelSerializer`) already returns `{id, model_id, display_name, provider, capability, is_free,
is_default}` for `is_active=True` rows.

### Frontend
- New Server Component fetch in `app/(home)/home/page.tsx` (same pattern as
  `app/(home)/settings/page.tsx`'s `serverFetch`): fetch `/api/models/?capability=image`,
  `/api/models/?capability=video`, and `/api/auth/keys/`, pass down as props into `<ProjectForm>`.
- `project-form.tsx`: delete `IMAGE_MODELS`/`VIDEO_MODELS` constants. Accept `imageModels`,
  `videoModels`, `userKeys` (list of `{provider: number}`) as props.
- Build a `Set<providerCode>` of providers the user has a key for. Filter each model list to
  `userProviderCodes.has(model.provider)`. This applies uniformly regardless of `is_free` — with
  Part 3, DashScope's free quota still requires the user's own DashScope key, not the app's.
- If a capability has zero selectable models (user has no keys yet), show inline text: "Add an API
  key in Settings to unlock image/video models" linking to `/settings`, and disable submission for
  that capability's paid path — mirrors the existing empty-state pattern in `ApiKeysPanel`.
- `VOICES`/`MUSIC_MOODS` arrays stay as-is.

---

## Part 2 — Users can register their own model

### Backend
- **Migration on `LLMModel`:** add `owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE,
  null=True, blank=True, related_name="custom_models")`. Replace the existing
  `unique_provider_capability_model` constraint with one that includes `owner`
  (`fields=["provider", "capability", "model_id", "owner"]`) — Postgres treats `NULL` as distinct per
  row, so admin rows (`owner=NULL`) stay unique among themselves and each user's rows are unique to
  that user.
- **`LLMModelViewSet`** (`apps/projects/views.py`): change `get_queryset` to
  `LLMModel.objects.filter(is_active=True).filter(Q(owner__isnull=True) | Q(owner=self.request.user))`.
  Add `mixins.CreateModelMixin` and `mixins.DestroyModelMixin`.
  - `perform_create`: force `owner=request.user, is_free=False, is_default=False, is_active=True`.
    Validate the submitted `provider` has a matching `UserAPIKey` for `request.user` (400 if not —
    "add an API key for this provider first").
  - `get_queryset` already scopes destroy/update to visible rows; add an explicit check in
    `perform_destroy`/a custom `get_object` override so a user can only delete `owner=request.user`
    rows (admin/global rows return 403, not editable via this endpoint — those stay `/admin/`-only).
- **`LLMModelSerializer`**: add writable `provider` (PK, not the read-only `provider.code`), `model_id`,
  `display_name`, `capability` for create; keep `is_free`/`is_default`/`id` read-only. Simplest:
  a small `LLMModelCreateSerializer` used only for `create`, reusing `LLMModelSerializer` for list/read.

### Frontend
- Settings page (`app/(home)/settings/page.tsx`): add a second section, "Custom Models", next to
  `ApiKeysPanel` — same visual/interaction pattern (inline add form, list with delete). Fetches
  `GET /api/models/` (all capabilities, includes both global and the user's own rows — own rows
  need a visual marker, e.g. a "custom" badge, and only those get a delete button).
  - Add form: provider dropdown (filtered to providers the user has a key for, reusing
    `usedIds`/`available` logic already in `api-keys.tsx`), capability dropdown (plan/image/video),
    `model_id` text input, `display_name` text input.

---

## Part 3 — Remove silent `.env` fallback for keyed providers

### Backend
- `resolve_secure_key(owner, provider)` (`apps/projects/utils.py:59`): raise `MissingAPIKeyError`
  (new, subclass of a plain `Exception` — not `(ConnectionError, TimeoutError)`, so it does **not**
  hit the retry path) instead of returning `None` when `UserAPIKey.DoesNotExist`.
- Call sites (`run_plan_stage`, `run_refine_stage` in `tasks.py`, and the image/video dispatch in
  `utils.py`) already wrap the body in `try / except (ConnectionError, TimeoutError) / except
  Exception as exc: fail_project(...)`. `MissingAPIKeyError` falls into the generic `except Exception`
  branch, so `fail_project` already logs it via `JobLog` and transitions the project to a failed
  state — no new error-handling scaffolding needed. Only change: give `MissingAPIKeyError.__str__`
  a clear message ("No API key configured for {provider.name} — add one in Settings") so it shows up
  verbatim in the `JobLog` the frontend already polls.
- Remove the `"db" if secure_key else "env-fallback"` log-source branch in `tasks.py:77-80` (dead
  once fallback is impossible) — replace with a flat "key_source=db" log or drop the field.
- **Explicitly unaffected:** the pipeline's own placeholder fallback chain (mid-generation provider
  failure → try next `PROVIDERS` entry → `PlaceholderProvider`, in `pipeline/images/__init__.py`)
  is a resilience feature, not a credential-fallback — `PlaceholderProvider` calls no external API
  and was never a seeded `Provider`/`LLMModel` row, so it's untouched.
- **Explicitly unaffected:** the standalone CLI pipeline (`python -m pipeline.refine` etc.) has no
  `owner`/`UserAPIKey` concept and keeps reading `.env` directly, same as today.

### Frontend
No dedicated changes — Part 1's provider-filtered dropdown already prevents selecting a model the
user has no key for, so `MissingAPIKeyError` should only surface for the plan-model default (which
isn't user-selected in the create form today) or for stale project state (key deleted after project
creation). In both cases the existing `JobLog`/error-banner UI on the project page displays it like
any other stage failure — no new UI needed.

---

## Data model changes summary
| Model      | Change                                                                 |
|------------|-------------------------------------------------------------------------|
| `LLMModel` | + `owner` (nullable FK to `UserProfile`); unique constraint now includes `owner` |

## API changes summary
| Method | URL                | Change                                                          |
|--------|--------------------|-----------------------------------------------------------------|
| GET    | `/api/models/`     | Now also returns the caller's own custom rows, mixed with global |
| POST   | `/api/models/`     | New — create a custom model (own provider+key required)         |
| DELETE | `/api/models/{id}/`| New — delete own custom model only (403 on global rows)          |

## Testing
- `apps/projects/tests/test_models_llm.py`: extend for the new unique constraint (two users can
  register the same `model_id` under the same provider; one user cannot duplicate their own).
- New: `LLMModelViewSet` create/destroy — 400 without a matching `UserAPIKey`, 403 deleting a
  global row, 403/404 deleting another user's row, list mixes global + own rows only.
- `apps/projects/tests/test_tasks_*.py`: extend to assert `MissingAPIKeyError` → `fail_project` →
  `JobLog(level=ERROR)` when no `UserAPIKey` exists for the resolved model's provider (replacing
  any existing test that relied on env-key fallback succeeding).
- No webapp test suite exists (per CLAUDE.md) — manual verification of the form/settings UI.
