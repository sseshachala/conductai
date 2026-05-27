"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { statusStyle, formatTrigger } from "@/lib/runUtils"

interface OutcomeStats {
  prs_opened: number
  issues_triaged: number
  reviews_completed: number
  incidents_investigated: number
  successful_automations: number
  failed_automations: number
}

interface AgentHealth {
  workflow_id: string
  name: string
  playbook_slug: string | null
  run_count: number
  succeeded_count: number
  failed_count: number
  success_rate: number
  last_run_status: string | null
  last_run_at: string | null
}

interface AttentionRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  created_at: string
}

interface RecentRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  started_at: string | null
  created_at: string
}

interface DashboardData {
  outcomes: OutcomeStats
  needs_attention: AttentionRun[]
  agent_health: AgentHealth[]
  recent_activity: RecentRun[]
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
          <div className="space-y-6">
            <div className="h-24 rounded-xl bg-stone-100 animate-pulse" />
            <div className="grid grid-cols-3 gap-3">
              {[1,2,3,4,5,6].map(i => <div key={i} className="h-20 rounded-xl bg-stone-100 animate-pulse" />)}
            </div>
            <div className="h-48 rounded-xl bg-stone-100 animate-pulse" />
          </div>
        ) : !data ? (
          <p className="text-stone-400 text-sm">Could not load dashboard.</p>
        ) : data.agent_health.length === 0 ? (
          <EmptyChecklist />
        ) : (
          <div className="space-y-10">

            {/* 1 — Needs Attention */}
            {data.needs_attention.length > 0 && (
              <section>
                <SectionHeader label="Needs Attention" href="/runs?view=needs-attention" linkLabel="View all →" />
                <AttentionList runs={data.needs_attention} />
              </section>
            )}

            {/* 2 — Outcomes This Week */}
            <section>
              <SectionHeader label="Outcomes" sub="Last 7 days" />
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <OutcomeCard label="PRs opened"             value={data.outcomes.prs_opened}             />
                <OutcomeCard label="Issues triaged"         value={data.outcomes.issues_triaged}         />
                <OutcomeCard label="Reviews completed"      value={data.outcomes.reviews_completed}      />
                <OutcomeCard label="Incidents investigated" value={data.outcomes.incidents_investigated}  />
                <OutcomeCard
                  label="Successful automations"
                  value={data.outcomes.successful_automations}
                  highlight="green"
                />
                <OutcomeCard
                  label="Failed automations"
                  value={data.outcomes.failed_automations}
                  highlight={data.outcomes.failed_automations > 0 ? "red" : undefined}
                  href={data.outcomes.failed_automations > 0 ? "/runs" : undefined}
                />
              </div>
            </section>

            {/* 3 — Agent Health */}
            <section>
              <SectionHeader label="Agent Health" sub="All time" />
              {data.agent_health.length === 0 ? (
                <div className="rounded-xl border border-dashed border-stone-300 p-10 text-center">
                  <p className="text-stone-400 text-sm">
                    <Link href="/workflows/new" className="underline hover:text-stone-700">Create your first agent</Link> to see health here.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-stone-200 bg-white overflow-hidden divide-y divide-stone-100">
                  {data.agent_health.map(agent => {
                    const rateColor =
                      agent.run_count === 0 ? "text-stone-300"
                      : agent.success_rate >= 80 ? "text-emerald-600"
                      : agent.success_rate >= 50 ? "text-amber-600"
                      : "text-red-600"
                    const dot = agent.last_run_status
                      ? statusStyle(agent.last_run_status).dot
                      : "bg-stone-200"
                    return (
                      <div key={agent.workflow_id} className="flex items-center justify-between px-4 py-3 hover:bg-stone-50 transition-colors">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
                          <Link
                            href={`/workflows/${agent.workflow_id}`}
                            className="text-sm font-medium text-stone-900 hover:text-indigo-600 truncate transition-colors"
                          >
                            {agent.name}
                          </Link>
                        </div>
                        <div className="flex items-center gap-5 ml-4 shrink-0 text-xs text-stone-400">
                          <span className={`font-semibold text-sm ${rateColor}`}>
                            {agent.run_count === 0 ? "—" : `${agent.success_rate}%`}
                          </span>
                          {agent.failed_count > 0 && (
                            <span className="text-red-500">{agent.failed_count} failed</span>
                          )}
                          <span>{agent.run_count} run{agent.run_count !== 1 ? "s" : ""}</span>
                          {agent.last_run_at
                            ? <span>{timeAgo(agent.last_run_at)}</span>
                            : <span className="italic">never run</span>}
                          <Link href={`/workflows/${agent.workflow_id}/runs`} className="text-stone-400 hover:text-stone-700 transition-colors">History →</Link>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </section>

            {/* 4 — Recent Activity */}
            <section>
              <SectionHeader label="Recent Activity" href="/runs" linkLabel="View all runs →" />
              {data.recent_activity.length === 0 ? (
                <div className="rounded-xl border border-dashed border-stone-300 p-10 text-center">
                  <p className="text-stone-400 text-sm">
                    No runs yet — <Link href="/workflows" className="underline hover:text-stone-700">open an agent</Link> and hit Run.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-stone-200 bg-white overflow-hidden divide-y divide-stone-100">
                  {data.recent_activity.map(run => {
                    const s = statusStyle(run.status)
                    return (
                      <Link
                        key={run.run_id}
                        href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
                        className="flex items-center justify-between px-4 py-3 hover:bg-stone-50 transition-colors"
                      >
                        <div>
                          <span className="text-sm font-medium text-stone-900">{run.workflow_name}</span>
                          <span className="text-xs text-stone-400 ml-2">{formatTrigger(run.triggered_by)}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                            {s.label}
                          </span>
                          <span className="text-xs text-stone-400">{timeAgo(run.started_at ?? run.created_at)}</span>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              )}
            </section>

          </div>
        )}
      </div>
    </AppShell>
  )
}

function AttentionList({ runs }: { runs: AttentionRun[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Group by agent_name + status
  const groups: { key: string; name: string; wfId: string; status: string; runs: AttentionRun[] }[] = []
  const seen = new Map<string, number>()
  for (const run of runs) {
    const key = `${run.workflow_id}::${run.status}`
    if (seen.has(key)) {
      groups[seen.get(key)!].runs.push(run)
    } else {
      seen.set(key, groups.length)
      groups.push({ key, name: run.workflow_name, wfId: run.workflow_id, status: run.status, runs: [run] })
    }
  }

  function toggle(key: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  return (
    <div className="rounded-xl border border-red-100 bg-red-50 overflow-hidden divide-y divide-red-100">
      {groups.map(group => {
        const s = statusStyle(group.status)
        const isOpen = expanded.has(group.key)
        const singular = group.runs.length === 1

        if (singular) {
          const run = group.runs[0]
          return (
            <Link
              key={group.key}
              href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-red-100/60 transition-colors"
            >
              <span className="text-sm font-medium text-stone-900">{group.name}</span>
              <div className="flex items-center gap-3">
                <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                  {s.label}
                </span>
                <span className="text-xs text-stone-400">{timeAgo(run.created_at)}</span>
              </div>
            </Link>
          )
        }

        return (
          <div key={group.key}>
            {/* Group header — click to expand */}
            <button
              onClick={() => toggle(group.key)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-red-100/60 transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-stone-900">{group.name}</span>
                <span className="text-[10px] font-semibold bg-red-200/70 text-red-700 px-1.5 py-0.5 rounded-full">
                  {group.runs.length}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                  {s.label}
                </span>
                <span className="text-xs text-stone-400">
                  {timeAgo(group.runs[0].created_at)} – {timeAgo(group.runs[group.runs.length - 1].created_at)}
                </span>
                <svg
                  className={`w-3.5 h-3.5 text-stone-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>

            {/* Expanded individual runs */}
            {isOpen && (
              <div className="divide-y divide-red-100/70 border-t border-red-100">
                {group.runs.map(run => (
                  <Link
                    key={run.run_id}
                    href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
                    className="flex items-center justify-between pl-8 pr-4 py-2.5 hover:bg-red-100/40 transition-colors"
                  >
                    <span className="text-xs text-stone-500">{formatTrigger(run.triggered_by)}</span>
                    <span className="text-xs text-stone-400">{timeAgo(run.created_at)}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SectionHeader({ label, sub, href, linkLabel }: {
  label: string
  sub?: string
  href?: string
  linkLabel?: string
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <p className="text-xs font-semibold text-stone-500 uppercase tracking-widest">{label}</p>
        {sub && <p className="text-xs text-stone-300">{sub}</p>}
      </div>
      {href && linkLabel && (
        <Link href={href} className="text-xs text-stone-400 hover:text-stone-700 transition-colors">{linkLabel}</Link>
      )}
    </div>
  )
}

function EmptyChecklist() {
  const steps = [
    { label: "Install a starter playbook", href: "/marketplace", cta: "Browse playbooks →" },
    { label: "Add credentials (GitHub token, Slack)", href: "/settings/integrations", cta: "Open integrations →" },
    { label: "Run a test trigger", href: "/runs", cta: "Go to Runs →" },
    { label: "Review the AI trace", href: "/runs", cta: "Open a run →" },
  ]
  return (
    <div className="rounded-xl border border-stone-200 bg-white px-8 py-10 max-w-lg mx-auto mt-8">
      <h2 className="text-sm font-semibold text-stone-900 mb-1">Get started with Conduct</h2>
      <p className="text-xs text-stone-400 mb-6">No agents yet. Follow these steps to automate your first engineering task.</p>
      <ol className="space-y-4">
        {steps.map((s, i) => (
          <li key={i} className="flex items-center gap-4">
            <span className="w-6 h-6 rounded-full bg-stone-100 text-stone-400 text-xs font-bold flex items-center justify-center shrink-0">
              {i + 1}
            </span>
            <div className="flex-1">
              <p className="text-sm text-stone-700">{s.label}</p>
            </div>
            <Link href={s.href} className="text-xs text-stone-500 hover:text-stone-900 transition-colors shrink-0">{s.cta}</Link>
          </li>
        ))}
      </ol>
    </div>
  )
}

function OutcomeCard({ label, value, highlight, href }: {
  label: string
  value: number
  highlight?: "green" | "red"
  href?: string
}) {
  const valueClass =
    highlight === "green" ? "text-emerald-700"
    : highlight === "red" ? "text-red-600"
    : "text-stone-900"

  const card = (
    <div className="rounded-xl border border-stone-200 bg-white px-4 py-4 hover:border-stone-300 transition-colors">
      <p className="text-xs text-stone-400 mb-1.5">{label}</p>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
    </div>
  )
  return href ? <Link href={href}>{card}</Link> : card
}
