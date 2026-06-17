# AI Video Studio — Frontend

Next.js 14 (App Router) frontend for the AI video pipeline. Talks to the Django backend on `:8000` via a proxy rewrite.

## Dev setup

```bash
# from repo root
make frontend      # Next.js dev server on :3000
make backend       # Django dev server on :8000 (separate terminal)
make migrate       # run once after clone or new migration
```

## Routes

| Path | Description |
|------|-------------|
| `/` | Redirects to `/home` |
| `/login` | Public login page — "Log in" button → Cognito hosted UI |
| `/home` | Authenticated home: welcome, create video, recent projects |

## Auth

Auth is entirely server-side — no client-side guards or React context.

```
Browser → middleware.ts (cookie check)
        → (home)/layout.tsx (async Server Component)
            → lib/auth-server.ts getUser()
                → GET http://localhost:8000/api/auth/me  (sessionid cookie forwarded)
```

- **Middleware** does a fast cookie-presence check. No cookie → `/login`. Authed user on `/login` → `/home`.
- **`(home)/layout.tsx`** calls `getUser()` on every navigation. Returns 401 → `redirect('/login')`.
- **`React.cache()`** deduplicates `getUser()` within a single render pass — layout + page both calling it = one network request.
- The `sessionid` cookie is opaque. User data lives in Django's session store; `/api/auth/me` is the only way to read it from Next.js.

## Key files

```
middleware.ts                  # cookie check + redirect logic
app/
  layout.tsx                   # HTML shell (fonts, globals.css) — no auth logic
  page.tsx                     # / → redirect /home
  login/page.tsx               # public login page
  (home)/
    layout.tsx                 # async auth gate + Header
    home/page.tsx              # /home page
components/
  home/welcome.tsx             # async Server Component, calls getUser()
  header.tsx                   # sticky header — 'use client' for logout only; gets user as props
  login-screen.tsx             # login card with href to /api/auth/login
lib/
  auth-server.ts               # getUser() — React.cache() wrapped fetch to Django
```

## Notes

- `/api/*` rewrites (in `next.config.mjs`) only apply to browser requests. Server Components must fetch Django directly at `http://localhost:8000`.
- `Header` is the only client component that receives user data — passed as props from the server layout, not via context.
- `FRONTEND_URL` env var on the Django side controls where Cognito redirects after login (default `http://localhost:3000`, lands on `/` which redirects to `/home`).
