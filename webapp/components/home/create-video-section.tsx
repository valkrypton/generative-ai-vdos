import ProjectForm from './project-form'
import { serverFetch } from '@/lib/server-fetch'
import type { LLMModel } from '@/lib/project-types'

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
