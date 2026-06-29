# B2 — Index: Submit Idea + Project List — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the home page's `<ProjectForm />` (prompt + options → POST /api/projects/ → navigate to new project) and `<ProjectList />` (server-rendered list of user's projects).

**Architecture:** `ProjectForm` is a client component managing form state and the POST call. `ProjectList` is a server component that fetches `GET /api/projects/` at render time by forwarding the `sessionid` cookie (same pattern as `lib/auth-server.ts:getUser()`). The home page layout drops its placeholder "New video" button since the form is always visible.

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind CSS, native `<select>` / `<textarea>` styled with design tokens (no new shadcn components needed).

## Global Constraints

- Next.js 14.2.35 — App Router only; no Pages Router patterns.
- No CSRF token required — `CognitoSessionAuthentication` extends `BaseAuthentication`, not DRF's `SessionAuthentication`.
- `gpt-image-1` must never be the pre-selected default — `imageBackend` defaults to `""` (env default).
- `animate` must default to `false`; DashScope-credit warning badge must appear inline next to the checkbox.
- Empty prompt must show inline validation error without sending a request.
- Server-side fetches to Django use `process.env.DJANGO_ORIGIN ?? 'http://localhost:8000'` — same as `lib/auth-server.ts`.
- Design tokens (hex values, not CSS vars — the webapp uses inline hex throughout): `bg=#171a21`, `panel2=#1e222b`, `line=#2a2f3a`, `ink=#e7e9ee`, `muted=#9aa3b2`, `accent=#6ea8fe`, `accent2=#5cd6a4`, `warn=#f0a35e`, `danger=#f06a6a`.
- Django runs on `:8000`; Next.js proxies `/api/*` → `http://localhost:8000/api/*` via `next.config.mjs`.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `webapp/app/(home)/home/page.tsx` | Modify | Remove "New video" button + wrapper |
| `webapp/components/home/project-form.tsx` | Create | Client form component |
| `webapp/components/home/create-video-section.tsx` | Modify | Import + render `<ProjectForm />` |
| `webapp/components/home/project-list.tsx` | Modify | Replace null stub with server component |

---

### Task 1: Remove "New video" button from home page

**Files:**
- Modify: `webapp/app/(home)/home/page.tsx`

**Interfaces:**
- Consumes: nothing new
- Produces: home page without the "New video" button and its wrapping div; `<WelcomeBanner />` renders standalone

- [ ] **Step 1: Read current home page**

Open `webapp/app/(home)/home/page.tsx`. Note the `<div className="flex items-start justify-between ...">` that wraps both `<WelcomeBanner />` and the `<Button>New video</Button>`.

- [ ] **Step 2: Replace the wrapper div with just the WelcomeBanner**

```tsx
// webapp/app/(home)/home/page.tsx
import { Suspense } from 'react'
import ProjectsSection from "@/components/home/project-section";
import CreateVideoSection from "@/components/home/create-video-section";
import WelcomeBanner from "@/components/home/welcome";
import WelcomeSkeleton from "@/components/home/welcome-skeleton";

export default function HomePage() {
  return (
    <div className="space-y-7">
      <Suspense fallback={<WelcomeSkeleton />}>
        <WelcomeBanner />
      </Suspense>

      <CreateVideoSection />

      <ProjectsSection />
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add webapp/app/\(home\)/home/page.tsx
git commit -m "feat(B2): remove placeholder New video button from home page"
```

---

### Task 2: Build `<ProjectForm />` and wire it into `CreateVideoSection`

**Files:**
- Create: `webapp/components/home/project-form.tsx`
- Modify: `webapp/components/home/create-video-section.tsx`

**Interfaces:**
- Consumes: `Button` from `@/components/ui/button`; `useRouter` from `next/navigation`
- Produces: default export `ProjectForm` — `'use client'` component, no props

- [ ] **Step 1: Create `project-form.tsx`**

```tsx
// webapp/components/home/project-form.tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'

const IMAGE_BACKENDS = [
  { value: '', label: 'qwen — free (env default)' },
  { value: 'flux', label: 'flux — free tier' },
  { value: 'gpt-image-1', label: 'gpt-image-1 — paid' },
  { value: 'placeholder', label: 'placeholder' },
]

const VOICES = [
  { value: 'en-US-AndrewNeural', label: 'Andrew (US Male)' },
  { value: 'en-US-RyanNeural', label: 'Ryan (GB Male)' },
  { value: 'en-US-AvaNeural', label: 'Ava (US Female)' },
]

const MUSIC_MOODS = [
  { value: 'calm', label: 'Calm' },
  { value: 'upbeat', label: 'Upbeat' },
  { value: 'dramatic', label: 'Dramatic' },
  { value: 'mysterious', label: 'Mysterious' },
  { value: 'inspiring', label: 'Inspiring' },
]

const SELECT_CLASS =
  'w-full bg-[#1e222b] text-[#e7e9ee] border border-[#2a2f3a] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-[#6ea8fe]'

export default function ProjectForm() {
  const router = useRouter()
  const [prompt, setPrompt] = useState('')
  const [imageBackend, setImageBackend] = useState('')
  const [voice, setVoice] = useState('en-US-AndrewNeural')
  const [music, setMusic] = useState('calm')
  const [animate, setAnimate] = useState(false)
  const [promptError, setPromptError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setPromptError('')
    setSubmitError('')

    if (!prompt.trim()) {
      setPromptError('Please describe an idea for your video.')
      return
    }

    setLoading(true)
    try {
      const body: Record<string, unknown> = {
        prompt: prompt.trim(),
        narrator_voice: voice,
        music,
        animate,
      }
      if (imageBackend) body.image_backend = imageBackend

      const res = await fetch('/api/projects/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (res.status === 201) {
        const data = await res.json()
        router.push(`/projects/${data.id}`)
        return
      }

      const data: { detail?: string } = await res.json().catch(() => ({}))
      setSubmitError(data.detail ?? 'Something went wrong. Please try again.')
    } catch {
      setSubmitError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-[#171a21] border border-[#2a2f3a] rounded-[12px] p-[18px] space-y-4"
    >
      {/* Prompt */}
      <div>
        <label className="block text-xs text-[#9aa3b2] mb-1.5">Idea</label>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="a lonely lighthouse keeper befriends a storm petrel during a winter gale"
          rows={3}
          className="w-full bg-[#1e222b] text-[#e7e9ee] border border-[#2a2f3a] rounded-lg px-3 py-2.5 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-[#6ea8fe] placeholder:text-[#4a5568]"
        />
        {promptError && (
          <p className="text-xs text-[#f06a6a] mt-1">{promptError}</p>
        )}
      </div>

      {/* Options row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-[#9aa3b2] mb-1.5">Image backend</label>
          <select
            value={imageBackend}
            onChange={e => setImageBackend(e.target.value)}
            className={SELECT_CLASS}
          >
            {IMAGE_BACKENDS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-[#9aa3b2] mb-1.5">Narrator voice</label>
          <select
            value={voice}
            onChange={e => setVoice(e.target.value)}
            className={SELECT_CLASS}
          >
            {VOICES.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-[#9aa3b2] mb-1.5">Music mood</label>
          <select
            value={music}
            onChange={e => setMusic(e.target.value)}
            className={SELECT_CLASS}
          >
            {MUSIC_MOODS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Animate + submit row */}
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-[#e7e9ee] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={animate}
            onChange={e => setAnimate(e.target.checked)}
            className="accent-[#6ea8fe]"
          />
          Animate stills
        </label>
        <span className="text-xs px-2.5 py-1 rounded-full border border-[#5e472b] text-[#f0a35e]">
          spends DashScope credit
        </span>

        <div className="ml-auto flex flex-col items-end gap-1">
          {submitError && (
            <p className="text-xs text-[#f06a6a]">{submitError}</p>
          )}
          <Button
            type="submit"
            disabled={loading}
            className="bg-[#6ea8fe] text-[#0a0d14] font-semibold text-sm px-4 py-2.5 rounded-lg hover:bg-[#5a97f0] active:scale-[0.98] transition-all disabled:opacity-50"
          >
            {loading ? 'Creating…' : 'Create plan →'}
          </Button>
        </div>
      </div>

      <p className="text-[11px] text-[#4a5568]">
        Defaults come from <code className="text-[#6ea8fe]">.env</code> — overrides here apply to this project only.
      </p>
    </form>
  )
}
```

- [ ] **Step 2: Wire `ProjectForm` into `CreateVideoSection`**

```tsx
// webapp/components/home/create-video-section.tsx
import ProjectForm from './project-form'

export default function CreateVideoSection() {
  return (
    <section>
      <h2 className="text-lg font-semibold text-[#e7e9ee] mb-1">Create a video</h2>
      <p className="text-sm text-[#9aa3b2] mb-4">
        Describe an idea. We&apos;ll write a shot plan you can review and refine before anything is generated.
      </p>
      <ProjectForm />
    </section>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Start the dev server and verify the form renders**

```bash
cd webapp && npm run dev
```

Open `http://localhost:3000/home`. Verify:
- Prompt textarea renders with placeholder text
- Three select dropdowns render (image backend, voice, music)
- Image backend defaults to `"qwen — free (env default)"` (first option, value `""`)
- Animate checkbox is unchecked by default
- "spends DashScope credit" orange badge is visible
- "Create plan →" button is present

- [ ] **Step 5: Verify inline validation — empty prompt**

In the running browser: leave the prompt empty and click "Create plan →".
Expected:
- Error message `"Please describe an idea for your video."` appears below the textarea
- Network tab in DevTools shows **no** POST request was made

- [ ] **Step 6: Verify form submission (requires running backend)**

If Django is running (`make backend`), fill in a prompt and click "Create plan →".
Expected:
- Button shows "Creating…" while request is in flight
- On `201`: browser navigates to `/projects/<uuid>` (page will 404 until B3 is built — that's fine)
- On non-201 (e.g. 401 if not logged in): inline error renders below the submit button

- [ ] **Step 7: Commit**

```bash
git add webapp/components/home/project-form.tsx webapp/components/home/create-video-section.tsx
git commit -m "feat(B2): add ProjectForm with validation, options, and POST /api/projects/"
```

---

### Task 3: Build `<ProjectList />` server component

**Files:**
- Modify: `webapp/components/home/project-list.tsx`

**Interfaces:**
- Consumes: `cookies` from `next/headers`; `Link` from `next/link`; `DJANGO_ORIGIN` env var (same as `lib/auth-server.ts`)
- Produces: default export `ProjectList` — async server component, no props

- [ ] **Step 1: Replace the stub with the server component**

```tsx
// webapp/components/home/project-list.tsx
import { cookies } from 'next/headers'
import Link from 'next/link'

const DJANGO_ORIGIN = (process.env.DJANGO_ORIGIN ?? 'http://localhost:8000').replace(/\/$/, '')

const GRADIENTS = [
  'linear-gradient(135deg, #6ea8fe, #9b6efe)',
  'linear-gradient(135deg, #5cd6a4, #3a9bd6)',
  'linear-gradient(135deg, #f0a35e, #f06a6a)',
  'linear-gradient(135deg, #c06efe, #6e8efe)',
  'linear-gradient(135deg, #5cd6a4, #d6cf5c)',
]

function getGradient(id: string): string {
  const code = id.charCodeAt(id.length - 1)
  return GRADIENTS[code % GRADIENTS.length]
}

const STATUS_STYLES: Record<string, { color: string; border: string }> = {
  DRAFT:      { color: '#9aa3b2', border: '#2a2f3a' },
  PLANNING:   { color: '#f0a35e', border: '#5e472b' },
  REVIEW:     { color: '#6ea8fe', border: '#33507e' },
  GENERATING: { color: '#f0a35e', border: '#5e472b' },
  DONE:       { color: '#5cd6a4', border: '#2c5544' },
  FAILED:     { color: '#f06a6a', border: '#5e2b2b' },
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 2) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

interface Project {
  id: string
  title: string
  status: string
  created_at: string
}

export default async function ProjectList() {
  const cookieStore = await cookies()
  const session = cookieStore.get('sessionid')

  let projects: Project[] = []
  let fetchError = false

  try {
    const res = await fetch(`${DJANGO_ORIGIN}/api/projects/`, {
      headers: { Cookie: `sessionid=${session?.value ?? ''}` },
      cache: 'no-store',
    })
    if (res.ok) {
      projects = await res.json()
    } else {
      fetchError = true
    }
  } catch {
    fetchError = true
  }

  if (fetchError) {
    return <p className="text-sm text-[#f06a6a]">Could not load projects.</p>
  }

  if (projects.length === 0) {
    return (
      <p className="text-sm text-[#9aa3b2]">
        No projects yet — create your first one above.
      </p>
    )
  }

  return (
    <div className="space-y-2.5">
      {projects.map(project => {
        const style = STATUS_STYLES[project.status] ?? STATUS_STYLES.DRAFT
        return (
          <Link
            key={project.id}
            href={`/projects/${project.id}`}
            className="flex items-center gap-3 px-3 py-3 rounded-[10px] border border-[#2a2f3a] bg-[#1e222b] hover:bg-[#252a35] transition-colors"
          >
            <span
              className="w-[34px] h-[34px] rounded-[7px] shrink-0"
              style={{ background: getGradient(project.id) }}
            />
            <span className="font-semibold text-[#e7e9ee] truncate flex-1 min-w-0">
              {project.title || 'Untitled'}
            </span>
            <span
              className="text-xs px-2.5 py-1 rounded-full border shrink-0"
              style={{ color: style.color, borderColor: style.border }}
            >
              {project.status.toLowerCase()}
            </span>
            <span className="text-sm text-[#9aa3b2] shrink-0">
              {relativeTime(project.created_at)}
            </span>
          </Link>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Verify the list renders (requires running backend)**

With Django running and a logged-in session:
1. Open `http://localhost:3000/home`
2. If user has no projects: `"No projects yet — create your first one above."` renders below the form
3. Create a project via the form
4. Navigate back to `/home` — new project appears in the list with a status badge and relative time
5. Badge colours: REVIEW = blue, DONE = green, GENERATING/PLANNING = orange, FAILED = red

- [ ] **Step 4: Verify user isolation**

Log in as a second user (or inspect DevTools → Network to confirm `GET /api/projects/` only returns the session user's projects). The server component forwards only the signed-in user's `sessionid`, so Django's `owner=request.user` filter does the isolation.

- [ ] **Step 5: Commit**

```bash
git add webapp/components/home/project-list.tsx
git commit -m "feat(B2): add ProjectList server component with status badges and relative time"
```
