"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import RunTrace from "@/components/runs/RunTrace"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface RunMeta {
  id: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string
}

export default function RunDetailPage() {
  const { id: workflowId, run_id: runId } = useParams<{ id: string; run_id: string }>()
  const { getToken } = useAuth()

  const [run, setRun] = useState<RunMeta | null>(null)
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const token = await getToken()
      const workspaceId = getCookie("delegator_project_id")
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [runRes, wfRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers }),
      ])

      if (runRes.ok) setRun(await runRes.json())
      if (wfRes.ok) {
        const wf = await wfRes.json()
        setWorkflowName(wf.name ?? null)
      }
      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId])

  if (loading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <p className="text-stone-400 text-sm">Loading…</p>
      </div>
    )
  }

  if (!run) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <p className="text-stone-500">Run not found.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href={`/workflows/${workflowId}/runs`} className="text-stone-400 hover:text-stone-700 text-sm">←</Link>
          <span className="font-semibold text-stone-900">{workflowName ?? "Agent"}</span>
          <span className="text-xs text-stone-400">/ Runs /</span>
          <span className="font-mono text-xs text-stone-500">{run.id.slice(0, 8)}…</span>
        </div>
        <Link
          href={`/workflows/${workflowId}`}
          className="text-xs text-stone-500 hover:text-stone-800 transition-colors"
        >
          Edit agent
        </Link>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-stone-900">Run trace</h2>
          <p className="text-sm text-stone-400 mt-1 font-mono">{run.id}</p>
        </div>

        <div className="bg-white rounded-xl border border-stone-200 p-6">
          <RunTrace
            workflowId={workflowId}
            runId={runId}
            initialStatus={run.status}
            initialMeta={{
              triggered_by: run.triggered_by,
              started_at: run.started_at,
              completed_at: run.completed_at,
              paused_at: run.paused_at,
              current_block_id: run.current_block_id,
              workflow_version_id: run.workflow_version_id,
            }}
          />
        </div>
      </main>
    </div>
  )
}
