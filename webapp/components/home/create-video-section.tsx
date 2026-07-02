import { cookies } from 'next/headers'
import ProjectForm from './project-form'

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
  const [imageModels, videoModels] = await Promise.all([
    serverFetch<LLMModel[]>('/api/models/?capability=image'),
    serverFetch<LLMModel[]>('/api/models/?capability=video'),
  ])

  return (
    <section>
      <h2 className="text-lg font-semibold text-[#e7e9ee] mb-1">Create a video</h2>
      <p className="text-sm text-[#9aa3b2] mb-4">
        Describe an idea. We&apos;ll write a shot plan you can review and refine before anything is generated.
      </p>
      <ProjectForm imageModels={imageModels} videoModels={videoModels} />
    </section>
  )
}
