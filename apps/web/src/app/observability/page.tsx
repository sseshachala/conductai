"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface HealthSummary {
  active_runs: number
  pending_approvals: number
  stale_workers: number
  succeeded_last_24h: number
  failed_last_24h: number
  total_last_24h: number
  error_rate_24h: number
}

interface RecentEvent {
  id: string
  event_type: string
  severity: string
  run_id: string | null
  workflow_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

interface ObservabilitySummary {
  health: HealthSummary
  recent_events: RecentEvent[]
}

interface AgentStatus {
  workflow_id: string
  name: string
  playbook_slug: string | null
  health: "healthy" | "degraded" | "stale" | "idle"
  active_runs: number
  pending_approvals: number
  stale_runs: number
  success_rate_24h: number
  succeeded_24h: number
  failed_24h: number
  last_run_at: string | null
  last_run_status: string | null
}

const HEALTH_STYLES: Record<string, { label: string; dot: string; text: string; bg: string; border: string }> = {
  healthy:  { label: "Healthy",  dot: "bg-green-400", text: "text-green-700", bg: "bg-green-50",  border: "border-green-200" },
  degraded: { label: "Degraded", dot: "bg-amber-400", text: "text-amber-700", bg: "bg-amber-50",  border: "border-amber-200" },
  stale:    { label: "Stale",    dot: "bg-red-400",   text: "text-red-700",   bg: "bg-red-50",    border: "border-red-200"   },
  idle:     { label: "Idle",     dot: "bg-stone-300", text: "text-stone-500", bg: "bg-stone-100", border: "border-stone-200" },
}

const SEVERITY_STYLES: Record<string, string> = {
  info:    "text-blue-700 bg-blue-50",
  warning: "text-amber-700 bg-amber-50",
  error:   "text-red-700 bg-red-50",
}

const EVENT_LABELS: Record<string, string> = {
  stale_worker:       "Stale worker detected",
  approval_timeout:   "Approval timeout",
  repeated_failure:   "Repeated failures",
  credential_expiry:  "Credential expired (401)",
  run_failed:         "Run failed",
  run_recovered:      "Run recovered",
}

function HealthBadge({ health }: { health: string }) {
  const s = HEALTH_STYLES[health] ?? HEALTH_STYLES.idle
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${s.bg} ${s.text} border ${s.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

function StatCard({ label, value, sub, accent }: { label: string; value: number | string; sub?: string; accent?: string }) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-5 py-4 flex flex-col gap-1">
      <div className={`text-2xl font-bold ${accent ?? "text-stone-900"}`}>{value}</div>
      <div className="text-xs font-medium text-stone-500 uppercase tracking-wide">{label}</div>
      {sub && <div className="text-xs text-stone-400">{sub}</div>}
    </div>
  )
}

export default function ObservabilityPage() {
  const { getToken } = useAuth()
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null)
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const loadAgents = useCallback(async () => {
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id") ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    if (workspaceId) headers["x-workspace-id"] = workspaceId
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    try {
      const res = await fetch(`${base}/observability/agents`, { headers })
      if (!res.ok) throw new Error("Failed to load agent data")
      setAgents(await res.json())
    } catch {
      // non-fatal — agents grid keeps last known state
    }
  }, [getToken])

  const connectSSE = useCallback(async () => {
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id") ?? ""
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params = new URLSearchParams()
    if (token) params.set("token", token)
    if (workspaceId) params.set("workspace_id", workspaceId)
    const url = `${base}/observability/stream?${params.toString()}`

    if (esRef.current) esRef.current.close()
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setLive(true)
    es.onerror = () => {
      setLive(false)
      // EventSource auto-reconnects; nothing extra needed
    }
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.kind === "stream_timeout") {
          // Server closed — EventSource will reconnect
          return
        }
        if (data.health) {
          setSummary(data as ObservabilitySummary)
          setLoading(false)
          setError(null)
        }
      } catch {
        // malformed frame — ignore
      }
    }
  }, [getToken])

  useEffect(() => {
    connectSSE()
    loadAgents()
    // Refresh agent grid every 30s (agents endpoint is not streamed)
    const agentInterval = setInterval(loadAgents, 30_000)
    return () => {
      agentInterval && clearInterval(agentInterval)
      esRef.current?.close()
    }
  }, [connectSSE, loadAgents])

  const refresh = useCallback(async () => {
    setLoading(true)
    await Promise.all([connectSSE(), loadAgents()])
  }, [connectSSE, loadAgents])

  const h = summary?.health

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Observability</h1>
            <p className="text-sm text-stone-500 mt-1">
              Live health of all agents and runs in this workspace.
              {live && <span className="ml-2 text-green-600 text-xs">● live</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/observability/alerts" className="text-xs text-stone-500 hover:text-stone-700 border border-stone-200 rounded-lg px-3 py-1.5 hover:bg-stone-50 transition-colors">
              Alert History
            </Link>
            <button
              onClick={refresh}
              className="text-xs text-stone-500 hover:text-stone-700 border border-stone-200 rounded-lg px-3 py-1.5 hover:bg-stone-50 transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {/* Health strip */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-stone-100 rounded-xl h-24" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Active runs"
              value={h?.active_runs ?? 0}
              accent={h && h.active_runs > 0 ? "text-blue-700" : undefined}
            />
            <StatCard
              label="Pending approval"
              value={h?.pending_approvals ?? 0}
              accent={h && h.pending_approvals > 0 ? "text-amber-600" : undefined}
            />
            <StatCard
              label="Stale workers"
              value={h?.stale_workers ?? 0}
              sub="Running >15 min without heartbeat"
              accent={h && h.stale_workers > 0 ? "text-red-600" : undefined}
            />
            <StatCard
              label="Error rate (24h)"
              value={h ? `${Math.round(h.error_rate_24h * 100)}%` : "—"}
              sub={h ? `${h.failed_last_24h} failed / ${h.total_last_24h} total` : undefined}
              accent={h && h.error_rate_24h > 0.2 ? "text-red-600" : h && h.error_rate_24h > 0.1 ? "text-amber-600" : undefined}
            />
          </div>
        )}

        {/* Agent status grid */}
        <div>
          <h2 className="text-sm font-semibold text-stone-700 mb-3">Agent Status</h2>
          {loading ? (
            <div className="space-y-2 animate-pulse">
              {[...Array(4)].map((_, i) => <div key={i} className="bg-stone-100 rounded-xl h-14" />)}
            </div>
          ) : agents.length === 0 ? (
            <div className="rounded-xl border border-stone-200 bg-white px-6 py-10 text-center text-sm text-stone-400">
              No agents configured yet.{" "}
              <Link href="/workflows" className="text-indigo-600 hover:underline">Create a workflow</Link> to get started.
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide">
                    <th className="px-4 py-3 text-left font-medium">Agent</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Active</th>
                    <th className="px-4 py-3 text-right font-medium">Approvals</th>
                    <th className="px-4 py-3 text-right font-medium">Success 24h</th>
                    <th className="px-4 py-3 text-left font-medium">Last run</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((a) => (
                    <tr
                      key={a.workflow_id}
                      className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors cursor-pointer"
                      onClick={() => window.location.href = `/workflows/${a.workflow_id}`}
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-stone-900">{a.name}</div>
                        {a.playbook_slug && (
                          <div className="text-[11px] text-stone-400 mt-0.5">{a.playbook_slug}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <HealthBadge health={a.health} />
                        {a.stale_runs > 0 && (
                          <div className="text-[11px] text-red-500 mt-0.5">{a.stale_runs} stale</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={a.active_runs > 0 ? "text-blue-700 font-medium" : "text-stone-400"}>
                          {a.active_runs}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={a.pending_approvals > 0 ? "text-amber-600 font-medium" : "text-stone-400"}>
                          {a.pending_approvals}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {a.succeeded_24h + a.failed_24h === 0 ? (
                          <span className="text-stone-300">—</span>
                        ) : (
                          <span className={a.success_rate_24h >= 0.8 ? "text-green-700" : "text-red-600"}>
                            {Math.round(a.success_rate_24h * 100)}%
                            <span className="text-stone-400 font-normal"> ({a.succeeded_24h}/{a.succeeded_24h + a.failed_24h})</span>
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {a.last_run_at ? (
                          <div>
                            <span className="text-stone-600">{timeAgo(a.last_run_at)}</span>
                            {a.last_run_status && (
                              <span className={`ml-2 text-[11px] ${a.last_run_status === "succeeded" ? "text-green-600" : a.last_run_status === "failed" ? "text-red-500" : "text-stone-400"}`}>
                                {a.last_run_status}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-stone-300">Never</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Watchdog events */}
        {summary && summary.recent_events.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-stone-700 mb-3">Recent Events</h2>
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              {summary.recent_events.map((ev) => (
                <div key={ev.id} className="flex items-start gap-3 px-4 py-3 border-b border-stone-100 last:border-0">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 mt-0.5 ${SEVERITY_STYLES[ev.severity] ?? "text-stone-500 bg-stone-100"}`}>
                    {ev.severity}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-stone-800">{EVENT_LABELS[ev.event_type] ?? ev.event_type}</div>
                    {ev.run_id && (
                      <div className="text-[11px] text-stone-400 mt-0.5 font-mono truncate">run {ev.run_id}</div>
                    )}
                  </div>
                  <div className="text-xs text-stone-400 shrink-0">{timeAgo(ev.created_at)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}
