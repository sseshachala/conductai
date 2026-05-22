"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface RunWithWorkflow {
  id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

const STATUS_STYLES: Record<string, { dot: string; text: string; bg: string }> = {
  pending:   { dot: "bg-stone-300",              text: "text-stone-500",  bg: "bg-stone-100"  },
  running:   { dot: "bg-blue-400 animate-pulse", text: "text-blue-700",  bg: "bg-blue-50"    },
  succeeded: { dot: "bg-green-400",              text: "text-green-700", bg: "bg-green-50"   },
  failed:    { dot: "bg-red-400",                text: "text-red-600",   bg: "bg-red-50"     },
  cancelled: { dot: "bg-stone-300",              text: "text-stone-400", bg: "bg-stone-100"  },
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function duration(started_at: string | null, completed_at: string | null): string {
  if (!started_at || !completed_at) return "—"
  const secs = Math.round((new Date(completed_at).getTime() - new Date(started_at).getTime()) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

export default function GlobalRunsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <GlobalRunsWithAuth />
  return <GlobalRunsContent getToken={null} />
}

function GlobalRunsWithAuth() {
  const { getToken } = useAuth()
  return <GlobalRunsContent getToken={getToken} />
}

function GlobalRunsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [runs, setRuns] = useState<RunWithWorkflow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const workspaceId = getCookie("delegator_project_id")
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/runs`, { headers })
        if (res.ok) setRuns(await res.json())
      } finally {
        setLoading(false)
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-5">
          <h1 className="text-xl font-semibold text-stone-900">Runs</h1>
          <span className="text-xs text-stone-400">{runs.length} run{runs.length !== 1 ? "s" : ""}</span>
        </div>

        {loading ? (
          <p className="text-stone-400 text-sm">Loading…</p>
        ) : runs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
            <p className="text-stone-800 font-medium mb-1">No runs yet</p>
            <p className="text-stone-400 text-sm">Run an agent to see activity here.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-100 text-left">
                  <th className="px-4 py-3 text-xs font-medium text-stone-500">Agent</th>
                  <th className="px-4 py-3 text-xs font-medium text-stone-500">Status</th>
                  <th className="px-4 py-3 text-xs font-medium text-stone-500">Triggered by</th>
                  <th className="px-4 py-3 text-xs font-medium text-stone-500">Started</th>
                  <th className="px-4 py-3 text-xs font-medium text-stone-500">Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const style = STATUS_STYLES[run.status] ?? STATUS_STYLES.pending
                  return (
                    <tr
                      key={run.id}
                      onClick={() => window.location.href = `/workflows/${run.workflow_id}/runs/${run.id}`}
                      className="border-b border-stone-100 last:border-0 hover:bg-stone-50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/workflows/${run.workflow_id}`}
                          onClick={e => e.stopPropagation()}
                          className="font-medium text-stone-900 hover:text-indigo-600 transition-colors"
                        >
                          {run.workflow_name}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${style.bg} ${style.text}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-stone-500">
                        {run.triggered_by ?? <span className="text-stone-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-stone-500">
                        {run.started_at ? timeAgo(run.started_at) : timeAgo(run.created_at)}
                      </td>
                      <td className="px-4 py-3 text-stone-500">
                        {duration(run.started_at, run.completed_at)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  )
}
