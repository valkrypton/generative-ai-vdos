import ProjectList from './project-list'

export default function ProjectsSection() {
  return (
    <section>
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#4a5568] font-medium mb-3">
        Recent
      </p>
      <ProjectList />
    </section>
  )
}