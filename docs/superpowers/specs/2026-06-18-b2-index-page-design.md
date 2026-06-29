# B2 — Index: Submit Idea + Project List

**Epic B — Web Application (Front-end) · ticket B2**
**Date:** 2026-06-18
**Lead:** Ali Tariq

---

## 1. Scope

Build the home page's two interactive sections:

1. **`<ProjectForm />`** — prompt textarea + options → `POST /api/projects/` → navigate to the new project.
2. **`<ProjectList />`** — server-rendered list of the signed-in user's projects from `GET /api/projects/`.

Remove the placeholder "New video" button (form is always visible on the page).

---

## 2. Architecture

`ProjectForm` is a **client component** (`'use client'`) — needs form state, validation, and `router.push`.

`ProjectList` is a **server component** — fetches `GET /api/projects/` at render time by forwarding the `sessionid` cookie (same pattern as `getUser()` in `lib/auth-server.ts`). Fresh on every navigation. No polling, no `useEffect`, no client bundle cost.

`CreateVideoSection` gains a `<ProjectForm />` below its existing heading/description. The home page layout (`app/(home)/home/page.tsx`) drops the "New video" button.

---

## 3. Components

### 3.1 `components/home/project-form.tsx` — new, client

**Form fields:**

| Field | Input | Default | Notes |
|-------|-------|---------|-------|
| `prompt` | `<textarea>` | `""` | Required. Inline validation error if empty on submit. |
| `imageBackend` | `<select>` | `""` (env default) | Options: `"" = env default`, `qwen`, `flux`, `gpt-image-1`, `placeholder`. gpt-image-1 never pre-selected. |
| `voice` | `<select>` | `"en-US-AndrewNeural"` | Options from `NarratorVoice` enum: Andrew, Ryan, Ava. |
| `music` | `<select>` | `"calm"` | Options from `MusicMood` enum: calm, upbeat, dramatic, mysterious, inspiring. |
| `animate` | `<input type="checkbox">` | `false` | Always off by default. Must show "spends DashScope credit" badge inline. |

**Submit flow:**
1. Validate: empty `prompt` → show inline error below textarea, abort.
2. `POST /api/projects/` with `Content-Type: application/json`, body `{prompt, image_backend, narrator_voice, music, animate}`. Omit `image_backend` when `""` (let Django use `.env`).
3. `201` → `router.push('/projects/' + data.id)`.
4. Non-`201` → show inline error message from `data.detail` (or generic fallback).
5. Submit button shows loading state while request in flight; disabled during submit.

**Validation rules:**
- Empty prompt → inline error, no network request.
- `gpt-image-1` is selectable (explicit user action) but never the pre-selected default.

### 3.2 `components/home/project-list.tsx` — replace stub, server

Fetches `GET /api/projects/` by forwarding the `sessionid` cookie:

```ts
const cookieStore = await cookies()
const session = cookieStore.get('sessionid')
const res = await fetch(`${DJANGO_ORIGIN}/api/projects/`, {
  headers: { Cookie: `sessionid=${session?.value ?? ''}` },
  cache: 'no-store',
})
```

**List row per project:**
- Colored icon square (gradient picked deterministically from the project `id`, cycling through 5 accent gradients)
- Title (fallback to `"Untitled"` when blank)
- Status badge (see §3.3)
- Relative time (simple helper: `"just now"`, `"2h ago"`, `"yesterday"`, `"3 days ago"`)
- Full row is a `<Link href="/projects/{id}">` 

**Empty state:** `"No projects yet — create your first one above."`

**Error state:** `"Could not load projects."` (non-ok response; never throws to crash the page).

### 3.3 Status badge colours

Matches mockup token system:

| Status | Text colour | Border colour |
|--------|-------------|---------------|
| `DRAFT` | `#9aa3b2` (muted) | `#2a2f3a` (line) |
| `PLANNING` | `#f0a35e` (warn) | `#5e472b` |
| `REVIEW` | `#6ea8fe` (accent) | `#33507e` |
| `GENERATING` | `#f0a35e` (warn) | `#5e472b` |
| `DONE` | `#5cd6a4` (accent2) | `#2c5544` |
| `FAILED` | `#f06a6a` (danger) | `#5e2b2b` |

### 3.4 Files modified

| File | Change |
|------|--------|
| `components/home/project-form.tsx` | **New** — client form |
| `components/home/project-list.tsx` | **Replace** stub with server component |
| `components/home/create-video-section.tsx` | Add `<ProjectForm />` |
| `app/(home)/home/page.tsx` | Remove "New video" button + wrapper div |
| `components/ui/select.tsx` | Install via `npx shadcn add select` |
| `components/ui/badge.tsx` | Install via `npx shadcn add badge` |

---

## 4. API contract (consumed)

**`POST /api/projects/`**
```jsonc
// request
{ "prompt": "...", "image_backend": "qwen", "narrator_voice": "en-US-AndrewNeural",
  "music": "calm", "animate": false }
// 201
{ "id": "9f1c…", "status": "PLANNING", "title": "", "created_at": "…" }
```
`image_backend` omitted (not sent) when the user leaves the dropdown at env default — the backend falls back to `.env` (D3).

**`GET /api/projects/`**
```jsonc
// 200 — array ordered by -created_at
[{ "id": "…", "title": "…", "status": "REVIEW", "created_at": "…" }, …]
```

---

## 5. Acceptance criteria (from spec §13 B2)

- [ ] Only `prompt` required; rest fall back to `.env` (D3).
- [ ] `animate` off by default; DashScope-credit warning shown inline.
- [ ] Empty prompt → inline validation error, no request sent.
- [ ] `gpt-image-1` never pre-selected.
- [ ] Project list shows only the signed-in user's projects.
- [ ] Successful submit → navigates to `/projects/{id}`.

---

## 6. Out of scope

- Real-time project list updates (SSE, polling) — B4.
- `/projects/[id]` page — B3/B4/B5.
- Any backend changes — backend API is already implemented.
