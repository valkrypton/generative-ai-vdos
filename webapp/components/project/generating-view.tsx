'use client'

import { useEffect, useRef, useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Project, Scene } from '@/lib/project-types'
import { Button } from '@/components/ui/button'
import SceneGrid from './scene-grid'
import StatusPill from './status-pill'

interface Props {
  project: Project
  onUpdate: (updates: Partial<Project>) => void
}

interface LogEntry {
  id: number
  stage: string
  level: 'info' | 'warn' | 'error'
  message: string
}

const LEVEL_COLOR: Record<string, string> = {
  info: '#9aa3b2',
  warn: '#f0a35e',
  error: '#f06a6a',
}

export default function GeneratingView({ project, onUpdate }: Props) {
  const router = useRouter()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [scenes, setScenes] = useState<Scene[]>(project.scenes)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isDeleting, startDelete] = useTransition()
  const logEndRef = useRef<HTMLDivElement>(null)
  const onUpdateRef = useRef(onUpdate)
  onUpdateRef.current = onUpdate

  function handleDelete() {
    startDelete(async () => {
      const res = await fetch(`/api/projects/${project.id}/`, { method: 'DELETE' })
      if (res.status === 204) { router.refresh(); router.push('/home') }
    })
  }

  useEffect(() => {
    let done = false
    let lastLogId = 0

    function finish(updated: Partial<Project>) {
      if (done) return
      done = true
      onUpdateRef.current(updated)
    }

    // Poll scenes + project status every 3 s.
    const scenePoll = setInterval(async () => {
      try {
        const res = await fetch(`/api/projects/${project.id}/`)
        if (!res.ok) return
        const updated: Project = await res.json()
        setScenes(updated.scenes)
        if (!['GENERATING', 'VIDEO_GENERATING'].includes(updated.status)) {
          clearInterval(scenePoll)
          clearInterval(logPoll)
          finish(updated)
        }
      } catch { /* keep polling */ }
    }, 3000)

    // Poll logs every 2 s, requesting only rows newer than the last seen id.
    const logPoll = setInterval(async () => {
      try {
        const res = await fetch(
          `/api/projects/${project.id}/logs/?after=${lastLogId}`
        )
        if (!res.ok) return
        const newLogs: LogEntry[] = await res.json()
        if (newLogs.length > 0) {
          lastLogId = newLogs[newLogs.length - 1].id
          setLogs(prev => [...prev, ...newLogs])
        }
      } catch { /* keep polling */ }
    }, 2000)

    return () => {
      done = true
      clearInterval(scenePoll)
      clearInterval(logPoll)
    }
  }, [project.id])

  useEffect(() => {
    const es = new EventSource(`/api/projects/${project.id}/events/`)

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.scene_index != null && data.preview_url) {
          setScenes(prev =>
            prev.map(s =>
              s.index === data.scene_index
                ? { ...s, preview_url: data.preview_url }
                : s
            )
          )
        }
        if (data.project_status === 'DONE' || data.project_status === 'FAILED') {
          es.close()
        }
      } catch {
        // ignore malformed events
      }
    }

    es.onerror = () => {}

    return () => {
      es.close()
    }
  }, [project.id])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <StatusPill status="GENERATING" />
        {confirmDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#9aa3b2]">Delete this project?</span>
            <Button
              disabled={isDeleting}
              onClick={handleDelete}
              className="bg-[#f06a6a] text-white text-xs px-3 py-1.5 rounded-lg hover:bg-[#d95858] disabled:opacity-50"
            >
              {isDeleting ? 'Deleting…' : 'Yes, delete'}
            </Button>
            <Button
              onClick={() => setConfirmDelete(false)}
              className="bg-transparent border border-[#2a2f3a] text-[#e7e9ee] text-xs px-3 py-1.5 rounded-lg hover:bg-[#1e222b]"
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            onClick={() => setConfirmDelete(true)}
            className="bg-transparent border border-[#f06a6a]/40 text-[#f06a6a] text-xs px-3 py-1.5 rounded-lg hover:bg-[#f06a6a]/10"
          >
            Delete project
          </Button>
        )}
      </div>

      {/* Side-by-side on lg+: log panel left, scene grid right */}
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_3fr] gap-5 items-start">
        {/* Log terminal */}
        <div className="lg:sticky lg:top-6">
          <p className="text-[10px] uppercase tracking-[0.2em] font-medium text-[#4a5568] mb-2">
            Pipeline log
          </p>
          <div className="bg-[#1e222b] border border-[#2a2f3a] rounded-[10px] p-4 h-64 overflow-y-auto font-mono text-xs space-y-1">
            {logs.length === 0 ? (
              <p className="text-[#4a5568]">Waiting for events…</p>
            ) : (
              logs.map(log => (
                <p key={log.id} style={{ color: LEVEL_COLOR[log.level] }}>
                  <span className="text-[#4a5568]">[{log.stage}]</span>{' '}
                  {log.message}
                </p>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Scene thumbnails */}
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] font-medium text-[#4a5568] mb-2">
            Scenes
          </p>
          {scenes.length > 0 ? (
            <SceneGrid scenes={scenes} />
          ) : (
            <p className="text-xs text-[#4a5568]">Scene images will appear here.</p>
          )}
        </div>
      </div>
    </div>
  )
}
