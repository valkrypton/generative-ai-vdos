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
