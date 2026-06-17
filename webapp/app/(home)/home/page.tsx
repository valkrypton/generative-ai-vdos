import { Suspense } from 'react'
import dynamic from 'next/dynamic'
import { Button } from '@base-ui/react'
import ProjectsSection from "@/components/home/project-section";
import CreateVideoSection from "@/components/home/create-video-section";
import WelcomeSkeleton from "@/components/home/welcome-skeleton";

const WelcomeBanner = dynamic(() => import('components/home/welcome'))

export default function HomePage() {
  return (
    <div className="space-y-7">

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <Suspense fallback={<WelcomeSkeleton />}>
          <WelcomeBanner />
        </Suspense>

        <Button
          className="shrink-0 inline-flex items-center gap-2 bg-[#6ea8fe] text-[#0a0d14] font-semibold text-sm px-4 py-2.5 rounded-lg hover:bg-[#5a97f0] active:scale-[0.98] transition-all"
        >
          <span className="text-base leading-none">+</span>
          New video
        </Button>
      </div>

      <CreateVideoSection />

      <ProjectsSection />

    </div>
  )
}
