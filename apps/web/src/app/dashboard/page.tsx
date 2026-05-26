"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { statusStyle, formatTrigger } from "@/lib/runUtils"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface WeekStats {
  issues_picked_up: number
  prs_opened: number
  total_runs: number
  succeeded_runs: number
  failed_runs: number
  success_rate: number
}

interface RecentRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  issue_number: number | null
  issue_title: string | null
  pr_url: string | null
  started_at: string | null
  created_at: string
}

interface AgentStatus {
  workflow_id: string
  name: string
  last_run_status: string | null
  last_run_at: string | null
}

interface DashboardData {
  week: WeekStats
  recent_runs: RecentRun[]
  agents: AgentStatus[]
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

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

export default function DashboardPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <DashboardWithAuth />
  return <DashboardContent getToken={null} />
}

function DashboardWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
  if (!isLoaded) return null
  return <DashboardContent getToken={getToken} />
}

function DashboardContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [data, setData] = useState<DashboardData | null>(null)
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
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/dashboard`, { headers })
        if (res.ok) setData(await res.json())
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [getToken])

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Dashboard</h1>
            <p className="text-xs text-stone-400 mt-0.5">Last 7 days</p>
          </div>
          <Link href="/workflows/new" className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 transition-colors">
            + New agent
          </Link>
        </div>

        {loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-4">
              {[1,2,3,4].map(i => <div key={i} className="h-20 rounded-xl bg-stone-100 animate-pulse" />)}
            </div>
            <div className="h-64 rounded-xl bg-stone-100 animate-pulse" />
          </div>
        ) : !data ? (
          <p className="text-stone-400 text-sm">Could not load dashboard.</p>
        ) : (
          <div className="space-y-8">

            {/* Section 1 — This week */}
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">This week</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Issues picked up" value={data.week.issues_picked_up} />
                <StatCard label="PRs opened" value={data.week.prs_opened} />
                <StatCard
                  label="Success rate"
                  value={`${data.week.success_rate}%`}
                  sub={`${data.week.succeeded_runs} of ${data.week.total_runs} runs`}
                  highlight={data.week.success_rate >= 80 ? "green" : data.week.success_rate >= 50 ? "amber" : "red"}
                />
                <StatCard
                  label="Failed runs"
                  value={data.week.failed_runs}
                  sub={data.week.failed_runs > 0 ? "View traces →" : "All clear"}
                  highlight={data.week.failed_runs > 0 ? "red" : "green"}
                  href={data.week.failed_runs > 0 ? "/runs" : undefined}
                />
              </div>
            </div>

            {/* Section 2 — Recent runs */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">Recent runs</p>
                <Link href="/runs" className="text-xs text-stone-400 hover:text-stone-700 transition-colors">View all →</Link>
              </div>
              {data.recent_runs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-stone-300 p-10 text-center">
                  <p className="text-stone-400 text-sm">No runs yet — <Link href="/workflows" className="underline hover:text-stone-700">open an agent</Link> and hit Run.</p>
                </div>
              ) : (
                <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-stone-100 text-left">
                        <th className="px-4 py-3 text-xs font-medium text-stone-500">Agent</th>
                        <th className="px-4 py-3 text-xs font-medium text-stone-500">Status</th>
                        <th className="px-4 py-3 text-xs font-medium text-stone-500">Issue</th>
                        <th className="px-4 py-3 text-xs font-medium text-stone-500">PR</th>
                        <th className="px-4 py-3 text-xs font-medium text-stone-500">When</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_runs.map(run => {
                        const s = statusStyle(run.status)
                        return (
                          <tr
                            key={run.run_id}
                            onClick={() => window.location.href = `/workflows/${run.workflow_id}/runs/${run.run_id}`}
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
                              <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                                {s.label}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-stone-500 text-xs">
                              {run.issue_number
                                ? <span>#{run.issue_number}{run.issue_title ? ` — ${run.issue_title}` : ""}</span>
                                : <span className="text-stone-300">—</span>}
                            </td>
                            <td className="px-4 py-3">
                              {run.pr_url
                                ? <a href={run.pr_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="text-xs text-indigo-600 hover:underline">View PR →</a>
                                : <span className="text-stone-300 text-xs">—</span>}
                            </td>
                            <td className="px-4 py-3 text-stone-400 text-xs">
                              {timeAgo(run.started_at ?? run.created_at)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Section 3 — Agent statuses */}
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Agents</p>
              {data.agents.length === 0 ? (
                <div className="rounded-xl border border-dashed border-stone-300 p-10 text-center">
                  <p className="text-stone-400 text-sm"><Link href="/workflows/new" className="underline hover:text-stone-700">Create your first agent</Link> to see it here.</p>
                </div>
              ) : (
                <div className="grid gap-2">
                  {data.agents.map(agent => {
                    const dot = agent.last_run_status ? statusStyle(agent.last_run_status).dot : "bg-stone-200"
                    return (
                      <div key={agent.workflow_id} className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 hover:border-stone-300 transition-colors">
                        <div className="flex items-center gap-3">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
                          <span className="text-sm font-medium text-stone-900">{agent.name}</span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-stone-400">
                          {agent.last_run_at
                            ? <span>last run {timeAgo(agent.last_run_at)}</span>
                            : <span className="italic">never run</span>}
                          <Link href={`/workflows/${agent.workflow_id}`} className="text-stone-500 hover:text-stone-900 transition-colors">Canvas →</Link>
                          <Link href={`/workflows/${agent.workflow_id}/runs`} className="text-stone-500 hover:text-stone-900 transition-colors">History →</Link>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

          </div>
        )}
      </div>
    </AppShell>
  )
}

function StatCard({ label, value, sub, highlight, href }: {
  label: string
  value: string | number
  sub?: string
  highlight?: "green" | "amber" | "red"
  href?: string
}) {
  const colors = {
    green: "text-emerald-700",
    amber: "text-amber-600",
    red:   "text-red-600",
  }
  const valueClass = highlight ? colors[highlight] : "text-stone-900"
  const card = (
    <div className="rounded-xl border border-stone-200 bg-white px-4 py-4 hover:border-stone-300 transition-colors">
      <p className="text-xs text-stone-400 mb-1.5">{label}</p>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="text-xs text-stone-400 mt-0.5">{sub}</p>}
    </div>
  )
  if (href) return <Link href={href}>{card}</Link>
  return card
}
