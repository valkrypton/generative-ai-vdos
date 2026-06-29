# User API Key Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authenticated users add, rotate, and delete their own provider API keys via a `/settings` page.

**Architecture:** One new Django endpoint lists active providers; the existing `/api/auth/keys/` CRUD endpoints handle keys. A Next.js Server Component fetches both server-side and passes data to a Client Component that owns all interactive state.

**Tech Stack:** Django 5.2 + DRF, Next.js 15 (App Router), React, Tailwind CSS, shadcn/ui Button component.

## Global Constraints

- Python 3.13+ — use `X | None` union syntax.
- No CSRF token needed — DRF views are `@csrf_exempt` because `CognitoSessionAuthentication` extends `BaseAuthentication`, not DRF's `SessionAuthentication`.
- Browser mutations hit `/api/auth/keys/` (proxied by the existing `next.config.mjs` rewrite).
- `/api/core/providers/` is also covered by the existing catch-all rewrite: `source: '/api/:path*'` → `djangoOrigin/api/:path*/`.
- Settings page lives inside the `(home)` route group — inherits the auth redirect from `app/(home)/layout.tsx`.
- Styling must match the existing dark palette: `bg-[#0c0e12]`, `border-[#2a2f3a]`, text `#9aa3b2` / `#e7e9ee`.
- Use the existing `<Button>` from `@/components/ui/button` — no new UI library installs.
- Run Django tests with: `python manage.py test apps.core` from `backend/`.
- Run Next.js type-check with: `cd webapp && npx tsc --noEmit`.

---

### Task 1: Backend — providers list endpoint

**Files:**
- Create: `backend/apps/core/views.py`
- Create: `backend/apps/core/urls.py`
- Create: `backend/apps/core/tests/__init__.py`
- Create: `backend/apps/core/tests/test_providers.py`
- Modify: `backend/config/urls.py` — add `path("api/core/", include("apps.core.urls"))`

**Interfaces:**
- Produces: `GET /api/core/providers/` → `[{"id": int, "code": str, "name": str}, ...]` (active providers only, no auth required)

- [ ] **Step 1: Create test file**

`backend/apps/core/tests/__init__.py` — empty file.

`backend/apps/core/tests/test_providers.py`:
```python
from django.test import TestCase
from apps.core.models import Provider


class ProviderListViewTest(TestCase):
    def test_returns_active_providers(self):
        Provider.objects.create(code="openai", name="OpenAI", is_active=True)
        Provider.objects.create(code="dashscope", name="DashScope", is_active=True)
        res = self.client.get("/api/core/providers/")
        self.assertEqual(res.status_code, 200)
        codes = {p["code"] for p in res.json()}
        self.assertIn("openai", codes)
        self.assertIn("dashscope", codes)

    def test_excludes_inactive_providers(self):
        Provider.objects.create(code="openai", name="OpenAI", is_active=True)
        Provider.objects.create(code="gone", name="Gone", is_active=False)
        res = self.client.get("/api/core/providers/")
        codes = {p["code"] for p in res.json()}
        self.assertNotIn("gone", codes)

    def test_response_shape(self):
        Provider.objects.create(code="openai", name="OpenAI", is_active=True)
        res = self.client.get("/api/core/providers/")
        item = res.json()[0]
        self.assertIn("id", item)
        self.assertIn("code", item)
        self.assertIn("name", item)
        self.assertNotIn("is_active", item)
        self.assertNotIn("created_at", item)

    def test_empty_when_no_providers(self):
        res = self.client.get("/api/core/providers/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])
```

- [ ] **Step 2: Run tests — expect failure (URL not found)**

```bash
cd backend && python manage.py test apps.core.tests.test_providers -v 2
```

Expected: 4 errors — `404` or `NoReverseMatch` because the URL doesn't exist yet.

- [ ] **Step 3: Create `backend/apps/core/views.py`**

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Provider


@api_view(["GET"])
def provider_list(request):
    providers = Provider.objects.filter(is_active=True).values("id", "code", "name")
    return Response(list(providers))
```

- [ ] **Step 4: Create `backend/apps/core/urls.py`**

```python
from django.urls import path
from . import views

urlpatterns = [
    path("providers/", views.provider_list, name="provider-list"),
]
```

- [ ] **Step 5: Wire into `backend/config/urls.py`**

Current file:
```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.health.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.projects.urls")),
]
```

Add the core line (insert after health):
```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.health.urls")),
    path("api/core/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.projects.urls")),
]
```

- [ ] **Step 6: Run tests — expect all 4 to pass**

```bash
cd backend && python manage.py test apps.core.tests.test_providers -v 2
```

Expected: `Ran 4 tests in ...s OK`

- [ ] **Step 7: Commit**

```bash
git add backend/apps/core/views.py backend/apps/core/urls.py \
        backend/apps/core/tests/__init__.py backend/apps/core/tests/test_providers.py \
        backend/config/urls.py
git commit -m "feat: add GET /api/core/providers/ endpoint"
```

---

### Task 2: Frontend — settings page + API keys panel

**Files:**
- Create: `webapp/app/(home)/settings/page.tsx`
- Create: `webapp/components/settings/api-keys.tsx`

**Interfaces:**
- Consumes: `GET /api/core/providers/` → `Provider[]` (from Task 1)
- Consumes: `GET /api/auth/keys/` → `ApiKey[]` (existing)
- Consumes: `POST /api/auth/keys/` body `{provider: number, api_key: string, label: string}` → `ApiKey`
- Consumes: `PATCH /api/auth/keys/{id}/` body `{api_key?: string, label: string}` → `ApiKey`
- Consumes: `DELETE /api/auth/keys/{id}/` → 204
- Produces: `/settings` page accessible from the browser

- [ ] **Step 1: Create `webapp/components/settings/api-keys.tsx`**

```tsx
'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'

export interface Provider {
  id: number
  code: string
  name: string
}

export interface ApiKey {
  id: number
  provider: number
  key_hint: string
  label: string
  created_at: string
}

interface Props {
  initialKeys: ApiKey[]
  providers: Provider[]
}

export function ApiKeysPanel({ initialKeys, providers }: Props) {
  const [keys, setKeys] = useState<ApiKey[]>(initialKeys)
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ provider: '', api_key: '', label: '' })
  const [editForm, setEditForm] = useState({ api_key: '', label: '' })

  const usedIds = new Set(keys.map(k => k.provider))
  const available = providers.filter(p => !usedIds.has(p.id))
  const providerName = (id: number) => providers.find(p => p.id === id)?.name ?? String(id)

  const inputCls =
    'bg-[#0c0e12] border border-[#2a2f3a] rounded px-3 py-2 text-sm w-full text-[#e7e9ee] placeholder-[#9aa3b2] focus:outline-none focus:border-[#6ea8fe]'

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    const res = await fetch('/api/auth/keys/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: Number(form.provider),
        api_key: form.api_key,
        label: form.label,
      }),
    })
    if (!res.ok) {
      const data: Record<string, unknown> = await res.json().catch(() => ({}))
      const nonField = data?.non_field_errors
      if (
        res.status === 400 &&
        Array.isArray(nonField) &&
        nonField.some((m: unknown) => typeof m === 'string' && m.toLowerCase().includes('unique'))
      ) {
        setError(`You already have a key for ${providerName(Number(form.provider))}.`)
      } else {
        setError('Something went wrong. Try again.')
      }
      return
    }
    const newKey: ApiKey = await res.json()
    setKeys(prev => [...prev, newKey])
    setAdding(false)
    setForm({ provider: '', api_key: '', label: '' })
  }

  async function handleDelete(id: number) {
    setError('')
    const res = await fetch(`/api/auth/keys/${id}/`, { method: 'DELETE' })
    if (!res.ok) { setError('Something went wrong. Try again.'); return }
    setKeys(prev => prev.filter(k => k.id !== id))
  }

  async function handleUpdate(e: React.FormEvent, id: number) {
    e.preventDefault()
    setError('')
    const body: Record<string, string> = { label: editForm.label }
    if (editForm.api_key) body.api_key = editForm.api_key
    const res = await fetch(`/api/auth/keys/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) { setError('Something went wrong. Try again.'); return }
    const updated: ApiKey = await res.json()
    setKeys(prev => prev.map(k => (k.id === id ? updated : k)))
    setEditingId(null)
    setEditForm({ api_key: '', label: '' })
  }

  return (
    <div className="rounded-lg border border-[#2a2f3a] overflow-hidden">
      {keys.length === 0 && !adding && (
        <p className="text-[#9aa3b2] text-sm px-5 py-6">No API keys added yet.</p>
      )}

      {keys.map(key => (
        <div key={key.id} className="border-b border-[#2a2f3a] last:border-b-0">
          {editingId === key.id ? (
            <form
              onSubmit={e => handleUpdate(e, key.id)}
              className="px-5 py-4 flex flex-col gap-3"
            >
              <p className="text-sm font-medium text-[#e7e9ee]">{providerName(key.provider)}</p>
              <input
                type="password"
                placeholder="New API key (leave blank to keep current)"
                value={editForm.api_key}
                onChange={e => setEditForm(f => ({ ...f, api_key: e.target.value }))}
                className={inputCls}
              />
              <input
                type="text"
                placeholder="Label (optional)"
                value={editForm.label}
                onChange={e => setEditForm(f => ({ ...f, label: e.target.value }))}
                className={inputCls}
              />
              {error && <p className="text-red-400 text-xs">{error}</p>}
              <div className="flex gap-2">
                <Button type="submit" size="sm">Save</Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => { setEditingId(null); setError('') }}
                  className="text-xs border-[#2a2f3a] text-[#e7e9ee] bg-transparent hover:bg-[#1e222b]"
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <div className="px-5 py-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[#e7e9ee]">{providerName(key.provider)}</p>
                <p className="text-xs text-[#9aa3b2] font-mono mt-0.5">{key.key_hint}</p>
                {key.label && (
                  <p className="text-xs text-[#9aa3b2] mt-0.5">{key.label}</p>
                )}
              </div>
              <p className="text-xs text-[#9aa3b2] shrink-0">
                {new Date(key.created_at).toLocaleDateString()}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEditingId(key.id)
                  setEditForm({ api_key: '', label: key.label })
                  setError('')
                }}
                className="text-xs border-[#2a2f3a] text-[#e7e9ee] bg-transparent hover:bg-[#1e222b]"
              >
                Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDelete(key.id)}
                className="text-xs border-[#2a2f3a] text-red-400 bg-transparent hover:bg-[#1e222b] hover:text-red-300"
              >
                Delete
              </Button>
            </div>
          )}
        </div>
      ))}

      {adding ? (
        <form
          onSubmit={handleAdd}
          className="border-t border-[#2a2f3a] px-5 py-4 flex flex-col gap-3"
        >
          <select
            required
            value={form.provider}
            onChange={e => setForm(f => ({ ...f, provider: e.target.value }))}
            className={inputCls}
          >
            <option value="">Select provider…</option>
            {available.map(p => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <input
            required
            type="password"
            placeholder="API key"
            value={form.api_key}
            onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
            className={inputCls}
          />
          <input
            type="text"
            placeholder="Label (optional)"
            value={form.label}
            onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
            className={inputCls}
          />
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2">
            <Button type="submit" size="sm">Add key</Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => { setAdding(false); setError('') }}
              className="text-xs border-[#2a2f3a] text-[#e7e9ee] bg-transparent hover:bg-[#1e222b]"
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : available.length > 0 ? (
        <div className={`${keys.length > 0 ? 'border-t border-[#2a2f3a]' : ''} px-5 py-3`}>
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setAdding(true); setError('') }}
            className="text-xs border-[#2a2f3a] text-[#e7e9ee] bg-transparent hover:bg-[#1e222b]"
          >
            + Add API key
          </Button>
        </div>
      ) : null}

      {!adding && editingId === null && error && (
        <p className="text-red-400 text-xs px-5 pb-4">{error}</p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create `webapp/app/(home)/settings/page.tsx`**

```tsx
import { cookies } from 'next/headers'
import { ApiKeysPanel, type ApiKey, type Provider } from '@/components/settings/api-keys'

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
  const [initialKeys, providers] = await Promise.all([
    serverFetch<ApiKey[]>('/api/auth/keys/'),
    serverFetch<Provider[]>('/api/core/providers/'),
  ])

  return (
    <div className="max-w-xl">
      <h1 className="text-xl font-semibold text-[#e7e9ee] mb-8">Settings</h1>
      <section>
        <h2 className="text-xs font-medium text-[#9aa3b2] uppercase tracking-widest mb-3">
          API Keys
        </h2>
        <ApiKeysPanel initialKeys={initialKeys} providers={providers} />
      </section>
    </div>
  )
}
```

- [ ] **Step 3: Type-check**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add webapp/app/\(home\)/settings/page.tsx webapp/components/settings/api-keys.tsx
git commit -m "feat: add /settings page with API key management"
```

---

### Task 3: Header navigation link to /settings

**Files:**
- Modify: `webapp/components/header.tsx`

**Interfaces:**
- Consumes: nothing new
- Produces: visible "Settings" link in the header pointing to `/settings`

- [ ] **Step 1: Update `webapp/components/header.tsx`**

Add `import Link from 'next/link'` at the top, then add the Settings link inside the `ml-auto` div, before the user chip. Full updated file:

```tsx
'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'

interface HeaderProps {
  email: string
  name: string
}

export function Header({ email, name }: HeaderProps) {
  function handleLogout() {
    window.location.replace('/api/auth/logout')
  }

  const initials = (name || email).slice(0, 1).toUpperCase()

  return (
    <header className="sticky top-0 z-10 flex items-center gap-4 px-5 py-3 bg-[#0c0e12] border-b border-[#2a2f3a]">
      <span className="font-bold tracking-tight">
        🎬 AI Video Studio
      </span>

      <div className="ml-auto flex items-center gap-3">
        <Link
          href="/settings"
          className="text-xs text-[#9aa3b2] hover:text-[#e7e9ee] transition-colors"
        >
          Settings
        </Link>
        <div className="flex items-center gap-2 text-sm text-[#9aa3b2] border border-[#2a2f3a] rounded-full pl-1 pr-3 py-1">
          <span className="w-6 h-6 rounded-full bg-[#6ea8fe] text-[#0a0d14] flex items-center justify-center font-bold text-xs">
            {initials}
          </span>
          <span className="max-w-[180px] truncate">{email}</span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleLogout}
          className="text-xs border-[#2a2f3a] text-[#e7e9ee] bg-transparent hover:bg-[#1e222b]"
        >
          Log out
        </Button>
      </div>
    </header>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd webapp && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add webapp/components/header.tsx
git commit -m "feat: add Settings nav link to header"
```
