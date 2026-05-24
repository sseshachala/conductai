"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import AgentTabs from "@/components/canvas/AgentTabs"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface Run {
  id: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  max_turns: number | null
}

const STATUS_STYLES: Record<string, string> = {
  pending:   "bg-stone-100 text-stone-500",
  running:   "bg-blue-100 text-blue-700",
  succeeded: "bg-green-100 text-green-700",
  failed:    "bg-red-100 text-red-700",
  cancelled: "bg-stone-100 text-stone-400",
}

export default function RunsPage() {
  const { id: workflowId } = useParams<{ id: string }>()
  const { getToken } = useAuth()

  const [runs, setRuns] = useState<Run[]>([])
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const token = await getToken()
      const workspaceId = getCookie("delegator_project_id")
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [runsRes, wfRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs`, { headers }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers }),
      ])

      if (runsRes.ok) setRuns(await runsRes.json())
      if (wfRes.ok) {
        const wf = await wfRes.json()
        setWorkflowName(wf.name ?? null)
      }
      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  return (
    <AppShell noPadding>
      <AgentTabs workflowId={workflowId} workflowName={workflowName ?? undefined} />
      <div className="flex-1 overflow-auto">
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold text-stone-900">Runs</h2>
          </div>
          <Link
            href={`/workflows/${workflowId}`}
            className="rounded-lg bg-stone-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
          >
            Edit agent
          </Link>
        </div>

        {loading ? (
          <p className="text-stone-400 text-sm">Loading…</p>
        ) : runs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
            <p className="text-stone-500 text-sm">No runs yet.</p>
            <Link
              href={`/workflows/${workflowId}`}
              className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:underline"
            >
              Open canvas to start a test run
            </Link>
          </div>
        ) : (
          <div className="grid gap-2">
            {runs.map((run) => (
              <Link
                key={run.id}
                href={`/workflows/${workflowId}/runs/${run.id}`}
                className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[run.status] ?? STATUS_STYLES.pending}`}>
                    {run.status}
                  </span>
                  <span className="text-sm text-stone-700 font-mono">{run.id.slice(0, 8)}…</span>
                  {run.triggered_by && (
                    <span className="text-xs text-stone-400">{run.triggered_by}</span>
                  )}
                </div>
                <div className="flex items-center gap-4">
                  {run.max_turns != null && (
                    <span className="text-xs text-stone-400 font-mono">
                      est. {run.max_turns} turns
                    </span>
                  )}
                  <span className="text-xs text-stone-400">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
      </div>
    </AppShell>
  )
}
