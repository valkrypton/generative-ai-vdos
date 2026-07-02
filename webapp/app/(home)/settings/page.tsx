import type { ApiKey, Provider } from '@/components/settings/api-keys'
import { SettingsPanels } from '@/components/settings/settings-panels'
import { serverFetch } from '@/lib/server-fetch'
import type { LLMModel } from '@/lib/project-types'

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
      <SettingsPanels initialKeys={initialKeys} providers={providers} initialModels={initialModels} />
    </div>
  )
}
