'use client'

import { useState } from 'react'
import { ApiKeysPanel, type ApiKey, type Provider } from './api-keys'
import { CustomModelsPanel } from './custom-models'
import type { LLMModel } from '@/lib/project-types'

interface Props {
  initialKeys: ApiKey[]
  providers: Provider[]
  initialModels: LLMModel[]
}

export function SettingsPanels({ initialKeys, providers, initialModels }: Props) {
  // Lifted here (not owned by ApiKeysPanel) so CustomModelsPanel's provider
  // dropdown sees a key the moment it's added, instead of a stale snapshot.
  const [keys, setKeys] = useState<ApiKey[]>(initialKeys)

  return (
    <>
      <section className="mb-8">
        <h2 className="text-xs font-medium text-[#9aa3b2] uppercase tracking-widest mb-3">
          API Keys
        </h2>
        <ApiKeysPanel keys={keys} onKeysChange={setKeys} providers={providers} />
      </section>
      <section>
        <h2 className="text-xs font-medium text-[#9aa3b2] uppercase tracking-widest mb-3">
          Custom Models
        </h2>
        <CustomModelsPanel initialModels={initialModels} keys={keys} providers={providers} />
      </section>
    </>
  )
}
