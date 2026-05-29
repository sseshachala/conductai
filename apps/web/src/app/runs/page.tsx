"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import { useSearchParams } from "next/navigation"
import AppShell from "@/components/AppShell"
import { statusStyle, needsAttention, isActive, formatTrigger, timeAgo, duration } from "@/lib/runUtils"

interface Run {
  id: string
  workflow_id: string
  workflow_name: string
  project_id: string | null
  project_name: string | null
  status: string
  triggered_by: string | null
  trigger_summary: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  created_at: string
}

type View = "all" | "by-agent" | "needs-attention"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

function StatusBadge({ status }: { status: string }) {
  const s = statusStyle(status)
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.dot}`} />
      {s.label}
    </span>
  )
}

function RunRow({ run }: { run: Run }) {
  const ts = run.started_at ?? run.created_at
  return (
    <tr
      onClick={() => window.location.href = `/workflows/${run.workflow_id}/runs/${run.id}`}
      className="border-b border-stone-100 last:border-0 hover:bg-stone-50 cursor-pointer transition-colors group"
    >
      <td className="px-4 py-3">
        <div className="font-medium text-stone-900 text-sm group-hover:text-indigo-600 transition-colors">
          {run.workflow_name}
        </div>
        {run.project_name && (
          <div className="text-[11px] text-stone-400 mt-0.5">{run.project_name}</div>
        )}
      </td>
      <td className="px-4 py-3"><StatusBadge status={run.status} /></td>
      <td className="px-4 py-3">
        <div className="text-xs text-stone-600">{formatTrigger(run.triggered_by)}</div>
        {run.trigger_summary && (
          <div className="text-[11px] text-stone-400 mt-0.5 truncate max-w-[180px]">{run.trigger_summary}</div>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-stone-500 whitespace-nowrap">{timeAgo(ts)}</td>
      <td className="px-4 py-3 text-xs text-stone-500 whitespace-nowrap">
        {duration(run.started_at, run.completed_at)}
      </td>
    </tr>
  )
}

function RunTable({ runs }: { runs: Run[] }) {
  if (runs.length === 0) return (
    <div className="rounded-xl border border-dashed border-stone-300 py-16 text-center">
      <p className="text-stone-500 font-medium">No runs</p>
      <p className="text-stone-400 text-sm mt-1">Nothing to show here yet.</p>
    </div>
  )
  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-100 text-left">
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Agent · Project</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Status</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Trigger</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Started</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Duration</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(run => <RunRow key={run.id} run={run} />)}
        </tbody>
      </table>
    </div>
  )
}

function ByAgentView({ runs }: { runs: Run[] }) {
  // Group by workflow_id to avoid merging agents with identical names across projects
  const grouped = runs.reduce<Record<string, { name: string; projectName: string | null; runs: Run[] }>>((acc, r) => {
    if (!acc[r.workflow_id]) acc[r.workflow_id] = { name: r.workflow_name, projectName: r.project_name, runs: [] }
    acc[r.workflow_id].runs.push(r)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([wfId, { name, projectName, runs: agentRuns }]) => {
        const latest = agentRuns[0]
        const s = statusStyle(latest.status)
        return (
          <div key={wfId} className="rounded-xl border border-stone-200 bg-white overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100 bg-stone-50">
              <div className="flex items-center gap-2">
                <Link href={`/workflows/${wfId}`} onClick={e => e.stopPropagation()}
                  className="font-medium text-stone-900 hover:text-indigo-600 transition-colors text-sm">
                  {name}
                </Link>
                {projectName && (
                  <span className="text-[10px] text-stone-400 bg-stone-100 px-1.5 py-0.5 rounded-full">{projectName}</span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-medium ${s.text}`}>{agentRuns.length} run{agentRuns.length !== 1 ? "s" : ""}</span>
                <StatusBadge status={latest.status} />
              </div>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {agentRuns.slice(0, 5).map(run => (
                  <tr key={run.id}
                    onClick={() => window.location.href = `/workflows/${run.workflow_id}/runs/${run.id}`}
                    className="border-b border-stone-100 last:border-0 hover:bg-stone-50 cursor-pointer transition-colors">
                    <td className="px-4 py-2.5"><StatusBadge status={run.status} /></td>
                    <td className="px-4 py-2.5 text-xs text-stone-500">{formatTrigger(run.triggered_by)}</td>
                    <td className="px-4 py-2.5 text-xs text-stone-400">{timeAgo(run.started_at ?? run.created_at)}</td>
                    <td className="px-4 py-2.5 text-xs text-stone-400">{duration(run.started_at, run.completed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}

export default function RunsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <RunsWithAuth />
  return <RunsContent getToken={null} />
}

function RunsWithAuth() {
  const { getToken } = useAuth()
  return <RunsContent getToken={getToken} />
}

const PAGE_SIZE = 50

function RunsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const searchParams = useSearchParams()
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const initialView = (searchParams.get("view") as View | null) ?? "all"
  const [view, setView] = useState<View>(initialView)
  const [filterProject, setFilterProject] = useState("")
  const [filterStatus, setFilterStatus] = useState("")

  async function buildHeaders() {
    const headers: Record<string, string> = {}
    if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
    const wsId = getCookie("delegator_project_id")
    if (wsId) headers["X-Workspace-Id"] = wsId
    return headers
  }

  useEffect(() => {
    async function load() {
      const headers = await buildHeaders()
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/runs?limit=${PAGE_SIZE}&offset=0`, { headers })
        if (res.ok) {
          const data: Run[] = await res.json()
          setRuns(data)
          setHasMore(data.length === PAGE_SIZE)
          setOffset(PAGE_SIZE)
        }
      } finally { setLoading(false) }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/runs?limit=${PAGE_SIZE}&offset=${offset}`, { headers })
      if (res.ok) {
        const data: Run[] = await res.json()
        setRuns(prev => [...prev, ...data])
        setHasMore(data.length === PAGE_SIZE)
        setOffset(o => o + PAGE_SIZE)
      }
    } finally { setLoadingMore(false) }
  }

  const projects = Array.from(new Set(runs.map(r => r.project_name).filter(Boolean))) as string[]

  const filtered = runs.filter(r => {
    if (filterProject && r.project_name !== filterProject) return false
    if (filterStatus && r.status !== filterStatus) return false
    return true
  })

  const running     = runs.filter(r => r.status === "running").length
  const waiting     = runs.filter(r => r.status === "paused").length
  const today       = new Date(); today.setHours(0, 0, 0, 0)
  const todayRuns   = runs.filter(r => new Date(r.created_at) >= today)
  const failedToday = todayRuns.filter(r => r.status === "failed").length
  const needsReview = runs.filter(r => needsAttention(r.status)).length

  const attentionRuns = filtered.filter(r => needsAttention(r.status))
  const activeRuns    = filtered.filter(r => isActive(r.status))
  const recentRuns    = filtered.filter(r => !needsAttention(r.status) && !isActive(r.status))

  const viewRuns: Record<View, Run[]> = {
    "all":            filtered,
    "by-agent":       filtered,
    "needs-attention": attentionRuns,
  }

  const VIEWS: { id: View; label: string; count?: number; urgent?: boolean }[] = [
    { id: "all",             label: "All",             count: filtered.length },
    { id: "by-agent",        label: "By Agent" },
    { id: "needs-attention", label: "Needs Attention", count: attentionRuns.length, urgent: attentionRuns.length > 0 },
  ]

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="text-xl font-semibold text-stone-900 mb-6">Runs</h1>

        {/* Top strip */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          {[
            { label: "Running",      value: running,     color: "text-blue-600",  bg: "bg-blue-50",   border: "border-blue-100" },
            { label: "Waiting",      value: waiting,     color: "text-amber-600", bg: "bg-amber-50",  border: "border-amber-100" },
            { label: "Failed today", value: failedToday, color: "text-red-600",   bg: "bg-red-50",    border: "border-red-100" },
            { label: "Needs review", value: needsReview, color: "text-orange-600",bg: "bg-orange-50", border: "border-orange-100" },
          ].map(({ label, value, color, bg, border }) => (
            <div key={label} className={`rounded-xl border ${border} ${bg} px-4 py-3`}>
              <div className={`text-2xl font-bold ${color}`}>{loading ? "—" : value}</div>
              <div className="text-xs text-stone-500 mt-0.5">{label}</div>
            </div>
          ))}
        </div>

        {/* View tabs + filters */}
        <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
          <div className="flex gap-1 border-b border-stone-200">
            {VIEWS.map(v => (
              <button key={v.id} onClick={() => setView(v.id)}
                className={`px-4 py-2 text-sm font-medium transition-colors rounded-t-lg flex items-center gap-1.5 ${
                  view === v.id
                    ? "bg-white border border-b-white border-stone-200 text-stone-900 -mb-px"
                    : v.urgent
                      ? "text-amber-600 hover:text-amber-800"
                      : "text-stone-400 hover:text-stone-700"
                }`}>
                {v.label}
                {v.count !== undefined && v.count > 0 && (
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                    view === v.id
                      ? (v.urgent ? "bg-amber-100 text-amber-700" : "bg-stone-100 text-stone-600")
                      : (v.urgent ? "bg-amber-100 text-amber-700" : "bg-stone-100 text-stone-400")
                  }`}>{v.count}</span>
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {projects.length > 1 && (
              <select value={filterProject} onChange={e => setFilterProject(e.target.value)}
                className="text-xs border border-stone-200 rounded-lg px-2 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-2 focus:ring-stone-200">
                <option value="">All projects</option>
                {projects.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            )}
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
              className="text-xs border border-stone-200 rounded-lg px-2 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-2 focus:ring-stone-200">
              <option value="">All statuses</option>
              {["running","paused","succeeded","failed","cancelled"].map(s => (
                <option key={s} value={s}>{statusStyle(s).label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="space-y-2">
            {[1,2,3,4].map(i => <div key={i} className="h-14 rounded-xl border border-stone-200 bg-white animate-pulse" />)}
          </div>
        ) : view === "by-agent" ? (
          <ByAgentView runs={filtered} />
        ) : view === "needs-attention" ? (
          <div className="space-y-6">
            {activeRuns.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Active</p>
                <RunTable runs={activeRuns} />
              </div>
            )}
            <div>
              {attentionRuns.length === 0
                ? <div className="rounded-xl border border-dashed border-stone-300 py-16 text-center">
                    <p className="text-stone-500 font-medium">All clear</p>
                    <p className="text-stone-400 text-sm mt-1">No failed, paused, or cancelled runs.</p>
                  </div>
                : <>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Needs attention</p>
                    <RunTable runs={attentionRuns} />
                  </>
              }
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {activeRuns.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Active</p>
                <RunTable runs={activeRuns} />
              </div>
            )}
            {attentionRuns.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Needs attention</p>
                <RunTable runs={attentionRuns} />
              </div>
            )}
            {recentRuns.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Recent</p>
                <RunTable runs={recentRuns} />
              </div>
            )}
            {runs.length === 0 && (
              <div className="rounded-xl border border-dashed border-stone-300 py-20 text-center">
                <p className="text-stone-800 font-medium mb-1">No runs yet</p>
                <p className="text-stone-400 text-sm">Runs are executions of installed agents. Open an agent and trigger a test run.</p>
              </div>
            )}
          </div>
        )}

        {/* Pagination */}
        {!loading && hasMore && (
          <div className="mt-4 text-center">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="text-sm text-stone-500 hover:text-stone-800 border border-stone-200 rounded-lg px-5 py-2 transition-colors hover:bg-stone-50 disabled:opacity-50"
            >
              {loadingMore ? "Loading…" : `Load more`}
            </button>
          </div>
        )}
      </div>
    </AppShell>
  )
}
