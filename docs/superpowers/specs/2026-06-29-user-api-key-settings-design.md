# User API Key Settings — Design Spec
Date: 2026-06-29

## Problem
Users cannot manage their own API keys. Only admins can. The backend model, serializer,
and viewset already exist; only the frontend and one small backend endpoint are missing.

## Scope
- New `/settings` page in the Next.js webapp
- One new Django endpoint: `GET /api/core/providers/`
- Header navigation link to `/settings`

Out of scope: user preferences, billing, notification settings.

---

## Backend

### New: `GET /api/core/providers/`
Returns the list of active `Provider` records. No authentication required (provider names
are not sensitive). Implemented in `apps/core/views.py` + `apps/core/urls.py`, wired into
`config/urls.py` at `api/core/`.

Response shape:
```json
[{"id": 1, "code": "openai", "name": "OpenAI"}]
```

### Existing endpoints (no changes needed)
| Method   | URL                        | Action                      |
|----------|----------------------------|-----------------------------|
| GET      | `/api/auth/keys/`          | List user's API keys        |
| POST     | `/api/auth/keys/`          | Add a key                   |
| PATCH    | `/api/auth/keys/{id}/`     | Update label or rotate key  |
| DELETE   | `/api/auth/keys/{id}/`     | Delete a key                |

Key response shape (list item):
```json
{"id": 1, "provider": 1, "key_hint": "sk-l•••••y7z", "label": "", "created_at": "..."}
```

---

## Frontend

### New files
```
app/(home)/settings/page.tsx          async Server Component
components/settings/api-keys.tsx      'use client' — all interactive state
```

### Modified files
```
components/header.tsx                 add Settings nav link
next.config.mjs                       ensure /api/core/* is proxied (if not already)
```

### Data flow
1. `settings/page.tsx` fetches `/api/auth/keys/` and `/api/core/providers/` server-side,
   forwarding the `sessionid` cookie (same pattern as `getUser()`).
2. Passes `initialKeys` and `providers` as props to `<ApiKeysPanel>`.
3. `ApiKeysPanel` (client component) owns local state. Mutations call Django directly
   via browser `fetch` to `/api/auth/keys/` (proxied by Next.js rewrites).

### UI behaviour
- Table of existing keys: provider name, masked key hint, label, date added, delete button.
- "Add key" inline form: provider dropdown (filtered to providers not yet added), key
  input (password type), optional label, submit button.
- Inline error below form for failures. No toast library.
- Specific error for duplicate provider: "You already have a key for [Provider]."
- Delete confirmation: none (key hint shown in row is enough context; key can be re-added).

---

## Error handling
| Scenario                        | Handling                                          |
|---------------------------------|---------------------------------------------------|
| Server-side fetch fails         | Throw — Next.js error boundary                    |
| POST 400 duplicate provider     | Inline: "You already have a key for [Provider]."  |
| POST/PATCH/DELETE network error | Inline: "Something went wrong. Try again."        |

---

## Testing
- `apps/core/tests/test_providers.py` — `GET /api/core/providers/` returns active providers,
  excludes inactive ones.
- No new frontend tests (no webapp test suite exists).
