"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"
import { buildWorkspaceHeaders } from "@/lib/workspaceHeaders"
import { useWorkspace } from "@/lib/WorkspaceContext"

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

interface PlaybookStat {
  playbook_slug: string
  run_count: number
  succeeded: number
  failed: number
  success_rate: number
  avg_cost_usd: number | null
  total_cost_usd: number
  total_input_tokens: number
  total_output_tokens: number
}

interface AnalyticsSummary {
  total_runs: number
  succeeded: number
  failed: number
  total_cost_usd: number
  total_input_tokens: number
  total_output_tokens: number
  avg_duration_ms: number | null
  top_playbooks: PlaybookStat[]
}

interface DoraMetrics {
  window_days: number
  total_runs: number
  deployment_frequency: number
  change_failure_rate: number
  avg_duration_ms: number | null
  by_trigger: Record<string, { runs: number; succeeded: number; failed: number; failure_rate: number }>
}

interface PlaybookScorecard {
  playbook_slug: string
  run_count: number
  avg_pct: number
  grade: string
  grade_dist: Record<string, number>
  avg_mechanical: number
  avg_judge: number
}

function fmt_duration(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function gradeColor(grade: string): [string, string] {
  if (grade === "A") return ["var(--ok)", "var(--ok-bg)"]
  if (grade === "B") return ["var(--info)", "#e8f4fd"]
  if (grade === "C") return ["var(--warn)", "var(--warn-bg)"]
  return ["var(--err)", "var(--err-bg)"]
}

const HEALTH_BADGE: Record<string, [string, string, string]> = {
  healthy:  ["Healthy",  "var(--ok)",     "var(--ok-bg)"],
  degraded: ["Degraded", "var(--warn)",   "var(--warn-bg)"],
  stale:    ["Stale",    "var(--err)",    "var(--err-bg)"],
  idle:     ["Idle",     "var(--text-3)", "var(--surface-3)"],
}

const EVENT_LABELS: Record<string, string> = {
  stale_worker:      "Stale worker detected",
  approval_timeout:  "Approval timeout",
  repeated_failure:  "Repeated failures",
  credential_expiry: "Credential expired (401)",
  queue_backup:      "Queue backup",
  silent_playbook:   "Silent playbook",
}

function fmt(n: number, decimals = 0): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return n.toFixed(decimals)
}

export default function ObservabilityPage() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const router = useRouter()
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null)
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [agentError, setAgentError] = useState(false)
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null)
  const [dora, setDora] = useState<DoraMetrics | null>(null)
  const [scorecards, setScorecards] = useState<Map<string, PlaybookScorecard>>(new Map())
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [live, setLive] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [filterSearch, setFilterSearch] = useState("")
  const [filterHealth, setFilterHealth] = useState("all")
  const PAGE_SIZE = 10
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  const loadAgents = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/observability/agents`)
      if (!res.ok) throw new Error("Failed to load agent data")
      setAgents(await res.json())
      setAgentError(false)
      setVisibleCount(PAGE_SIZE)
    } catch {
      setAgentError(true)
    } finally {
      setAgentsLoading(false)
    }
  }, [authFetch])

  const loadAnalytics = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/analytics/summary?days=30`)
      if (res.ok) setAnalytics(await res.json())
    } catch {
      // non-fatal — keep last known state
    }
  }, [authFetch])

  const loadDora = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/analytics/dora?days=30`)
      if (res.ok) setDora(await res.json())
    } catch { }
  }, [authFetch])

  const loadScorecards = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/analytics/scorecards?days=30`)
      if (res.ok) {
        const list: PlaybookScorecard[] = await res.json()
        setScorecards(new Map(list.map(s => [s.playbook_slug, s])))
      }
    } catch { }
  }, [authFetch])

  const { getToken } = useAuth()
  const connectSSE = useCallback(async (attempt = 0) => {
    const token = await getToken()
    const workspaceId = activeWorkspace?.id ?? ""
    const params = new URLSearchParams()
    if (token) params.set("token", token)
    if (workspaceId) params.set("workspace_id", workspaceId)
    const url = `${API}/observability/stream?${params.toString()}`

    if (esRef.current) esRef.current.close()
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setLive(true)
    es.onerror = () => {
      setLive(false)
      const delay = Math.min(1000 * 2 ** attempt, 30_000)
      reconnectTimer.current = setTimeout(() => connectSSE(attempt + 1), delay)
    }
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.kind === "stream_timeout") return
        if (data.health) setSummary(data as ObservabilitySummary)
      } catch {
        // malformed frame — ignore
      }
    }
  }, [getToken, activeWorkspace])

  useEffect(() => {
    connectSSE()
    loadAgents()
    loadAnalytics()
    loadDora()
    loadScorecards()
    const agentInterval     = setInterval(loadAgents,    30_000)
    const analyticsInterval = setInterval(() => { loadAnalytics(); loadDora(); loadScorecards() }, 60_000)
    return () => {
      clearInterval(agentInterval)
      clearInterval(analyticsInterval)
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      esRef.current?.close()
    }
  }, [connectSSE, loadAgents, loadAnalytics, loadDora, loadScorecards])

  const refresh = useCallback(() => {
    connectSSE()
    loadAgents()
    loadAnalytics()
    loadDora()
    loadScorecards()
  }, [connectSSE, loadAgents, loadAnalytics, loadDora, loadScorecards])

  const selectStyle: React.CSSProperties = {
    fontSize: 13,
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "6px 12px",
    background: "var(--surface)",
    color: "var(--text-2)",
    cursor: "pointer",
  }

  const filteredAgents = [...agents]
    .sort((a, b) => {
      if (!a.last_run_at && !b.last_run_at) return 0
      if (!a.last_run_at) return 1
      if (!b.last_run_at) return -1
      return new Date(b.last_run_at).getTime() - new Date(a.last_run_at).getTime()
    })
    .filter(a => {
      if (filterHealth !== "all" && a.health !== filterHealth) return false
      if (filterSearch) {
        const q = filterSearch.toLowerCase()
        if (!a.name.toLowerCase().includes(q) && !(a.playbook_slug ?? "").toLowerCase().includes(q)) return false
      }
      return true
    })
  const visibleAgents = filteredAgents.slice(0, visibleCount)
  const hasMore = filteredAgents.length > visibleCount
  const anyFilter = filterSearch !== "" || filterHealth !== "all"

  const h = summary?.health

  const healthCards = [
    { k: "Active runs",     v: h ? h.active_runs : "—",   tone: h && h.active_runs > 0 ? "var(--info)" : "var(--text)", sub: null },
    { k: "Pending approval",v: h ? h.pending_approvals : "—", tone: h && h.pending_approvals > 0 ? "var(--warn)" : "var(--text)", sub: null },
    { k: "Stale workers",   v: h ? h.stale_workers : "—", tone: h && h.stale_workers > 0 ? "var(--err)" : "var(--text)", sub: "Running >15 min without heartbeat" },
    { k: "Error rate 24h",  v: h ? `${Math.round(h.error_rate_24h * 100)}%` : "—", tone: h && h.error_rate_24h > 0.2 ? "var(--err)" : h && h.error_rate_24h > 0.1 ? "var(--warn)" : "var(--text)", sub: h ? `${h.failed_last_24h} failed · ${h.total_last_24h} total` : null },
  ]

  return (
    <AppShell>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "30px 34px 80px" }}>
        {/* Header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-start" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
              <h1 className="page-title">Observability</h1>
              {live ? (
                <span className="sbadge ok" style={{ marginTop: 3, display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span className="dot pulse" style={{ background: "var(--ok)" }} />live
                </span>
              ) : summary !== null && (
                <span className="sbadge warn" style={{ marginTop: 3, display: "inline-flex", alignItems: "center", gap: 6 }}>
                  reconnecting…
                </span>
              )}
            </div>
            <p className="page-sub">Live health of every agent and run in this workspace.</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 9 }}>
            <Link href="/observability/alerts" className="btn btn-ghost" style={{ fontSize: 13 }}>Alert history</Link>
            <button className="btn btn-ghost" onClick={refresh}>Refresh</button>
          </div>
        </div>

        {/* Health strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 24 }}>
          {healthCards.map((s) => (
            <div key={s.k} className="card" style={{ padding: "16px 18px" }}>
              <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", color: s.tone, lineHeight: 1.1 }}>{String(s.v)}</div>
              <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>{s.k}</div>
              {s.sub && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>{s.sub}</div>}
            </div>
          ))}
        </div>

        {/* DORA-lite */}
        <div className="eyebrow" style={{ marginBottom: 11 }}>
          DORA-lite <span style={{ textTransform: "none", letterSpacing: 0, color: "var(--text-muted)", fontWeight: 500 }}>· last 30 days</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 24 }}>
          {[
            {
              v: dora ? `${dora.deployment_frequency.toFixed(1)}/day` : "—",
              k: "Deploys / day",
              tone: dora ? (dora.deployment_frequency >= 1 ? "var(--ok)" : dora.deployment_frequency >= 0.5 ? "var(--warn)" : "var(--text-muted)") : "var(--text-muted)",
            },
            {
              v: dora ? `${Math.round(dora.change_failure_rate * 100)}%` : "—",
              k: "Failure rate",
              tone: dora ? (dora.change_failure_rate < 0.1 ? "var(--ok)" : dora.change_failure_rate < 0.2 ? "var(--warn)" : "var(--err)") : "var(--text-muted)",
            },
            {
              v: dora?.avg_duration_ms ? fmt_duration(dora.avg_duration_ms) : "—",
              k: "Avg run time",
              tone: "var(--text)",
            },
            {
              v: dora ? dora.total_runs : "—",
              k: "Deployments",
              tone: "var(--text)",
            },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: "16px 18px" }}>
              <div style={{ fontSize: 23, fontWeight: 700, letterSpacing: "-.02em", color: s.tone, lineHeight: 1.1 }}>{String(s.v)}</div>
              <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>{s.k}</div>
            </div>
          ))}
        </div>

        {/* Cost summary */}
        <div className="eyebrow" style={{ marginBottom: 11 }}>
          Cost summary <span style={{ textTransform: "none", letterSpacing: 0, color: "var(--text-muted)", fontWeight: 500 }}>· last 30 days</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 24 }}>
          {(analytics ? [
            [`$${analytics.total_cost_usd.toFixed(4)}`, "Total cost", null],
            [analytics.total_runs, "Total runs", `${analytics.succeeded} ok · ${analytics.failed} failed`],
            [fmt(analytics.total_input_tokens), "Input tokens", null],
            [fmt(analytics.total_output_tokens), "Output tokens", null],
          ] as [string | number, string, string | null][] : [
            ["—", "Total cost", null],
            ["—", "Total runs", null],
            ["—", "Input tokens", null],
            ["—", "Output tokens", null],
          ] as [string, string, null][]).map(([v, k, sub], i) => (
            <div key={i} className="card" style={{ padding: "16px 18px" }}>
              <div style={{ fontSize: 23, fontWeight: 700, letterSpacing: "-.02em" }}>{String(v)}</div>
              <div className="eyebrow" style={{ marginTop: 7, fontSize: 9.5 }}>{k}</div>
              {sub && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>{sub}</div>}
            </div>
          ))}
        </div>

        {/* Agent status */}
        <div className="eyebrow" style={{ marginBottom: 11 }}>Agent status</div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <div style={{ position: "relative" }}>
            <input
              type="text"
              placeholder="Search agent or slug…"
              value={filterSearch}
              onChange={e => { setFilterSearch(e.target.value); setVisibleCount(PAGE_SIZE) }}
              style={{ ...selectStyle, paddingRight: filterSearch ? 28 : 12, width: 200 }}
            />
            {filterSearch && (
              <button onClick={() => { setFilterSearch(""); setVisibleCount(PAGE_SIZE) }}
                style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 14, padding: 0 }}>
                ×
              </button>
            )}
          </div>
          <select value={filterHealth} onChange={e => { setFilterHealth(e.target.value); setVisibleCount(PAGE_SIZE) }} style={selectStyle}>
            <option value="all">All health</option>
            <option value="healthy">Healthy</option>
            <option value="degraded">Degraded</option>
            <option value="stale">Stale</option>
            <option value="idle">Idle</option>
          </select>
          {anyFilter && (
            <button onClick={() => { setFilterSearch(""); setFilterHealth("all"); setVisibleCount(PAGE_SIZE) }}
              className="btn btn-ghost" style={{ fontSize: 12 }}>
              Clear filters
            </button>
          )}
          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
            {filteredAgents.length} agent{filteredAgents.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="card" style={{ overflow: "hidden", marginBottom: 26 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 0.7fr 0.9fr 1.1fr 1fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
            {["Agent", "Status", "Active", "Approvals", "Success 24h", "Last run"].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 10, textAlign: i >= 2 && i <= 4 ? "right" : "left" }}>{h}</div>
            ))}
          </div>
          {agentsLoading ? (
            <div>
              {[...Array(4)].map((_, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 0.7fr 0.9fr 1.1fr 1fr", gap: 14, padding: "14px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                  <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite", width: "70%" }} />
                  <div style={{ height: 20, borderRadius: 10, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite", width: 64 }} />
                  <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite", marginLeft: "auto", width: 24 }} />
                  <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite", marginLeft: "auto", width: 24 }} />
                  <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite", marginLeft: "auto", width: 36 }} />
                  <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite", width: 56 }} />
                </div>
              ))}
            </div>
          ) : agentError ? (
            <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--err)" }}>
              Failed to load agent data.{" "}
              <button onClick={loadAgents} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent)", fontSize: 13, padding: 0 }}>Retry</button>
            </div>
          ) : agents.length === 0 ? (
            <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
              No agents configured yet.{" "}
              <Link href="/workflows" style={{ color: "var(--accent)" }}>Create a workflow</Link> to get started.
            </div>
          ) : visibleAgents.length === 0 ? (
            <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
              No agents match this filter.{" "}
              <button onClick={() => { setFilterSearch(""); setFilterHealth("all") }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent)", fontSize: 13, padding: 0 }}>Clear filters</button>
            </div>
          ) : (
            visibleAgents.map((a) => {
              const [lbl, c, bg] = HEALTH_BADGE[a.health] ?? ["Idle", "var(--text-3)", "var(--surface-3)"]
              return (
                <div
                  key={a.workflow_id}
                  onClick={() => router.push(`/workflows/${a.workflow_id}`)}
                  style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 0.7fr 0.9fr 1.1fr 1fr", gap: 14, padding: "12px 20px", borderBottom: "1px solid var(--border)", alignItems: "center", cursor: "pointer" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "")}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>{a.name}</div>
                    {a.playbook_slug && <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{a.playbook_slug}</div>}
                  </div>
                  <div>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 22, padding: "0 9px", borderRadius: 20, fontSize: 11.5, fontWeight: 600, color: c, background: bg }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c }} />{lbl}
                    </span>
                    {a.stale_runs > 0 && <div style={{ fontSize: 10.5, color: "var(--err)", marginTop: 3 }}>{a.stale_runs} stale</div>}
                  </div>
                  <div className="mono" style={{ fontSize: 13, textAlign: "right", color: a.active_runs > 0 ? "var(--info)" : "var(--text-muted)", fontWeight: a.active_runs > 0 ? 700 : 400 }}>{a.active_runs}</div>
                  <div className="mono" style={{ fontSize: 13, textAlign: "right", color: a.pending_approvals > 0 ? "var(--warn)" : "var(--text-muted)", fontWeight: a.pending_approvals > 0 ? 700 : 400 }}>{a.pending_approvals}</div>
                  <div style={{ textAlign: "right" }}>
                    {a.succeeded_24h + a.failed_24h === 0
                      ? <span style={{ color: "var(--text-muted)" }}>—</span>
                      : <span className="mono" style={{ fontSize: 12.5, color: a.success_rate_24h >= 0.8 ? "var(--ok)" : "var(--err)" }}>{Math.round(a.success_rate_24h * 100)}%</span>
                    }
                  </div>
                  <div style={{ fontSize: 12 }}>
                    {a.last_run_at
                      ? <span style={{ color: "var(--text-3)" }}>{timeAgo(a.last_run_at)}{a.last_run_status && <span style={{ color: a.last_run_status === "succeeded" ? "var(--ok)" : a.last_run_status === "failed" ? "var(--err)" : "var(--info)", fontSize: 11 }}> · {a.last_run_status}</span>}</span>
                      : <span style={{ color: "var(--text-muted)" }}>Never</span>
                    }
                  </div>
                </div>
              )
            })
          )}
        </div>
        {hasMore && (
          <div style={{ textAlign: "center", marginTop: 8, marginBottom: 16 }}>
            <button className="btn btn-ghost" style={{ fontSize: 13 }} onClick={() => setVisibleCount(v => v + PAGE_SIZE)}>
              Load more ({filteredAgents.length - visibleCount} remaining)
            </button>
          </div>
        )}

        {/* By-agent + events */}
        <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 16 }}>
          {/* By agent */}
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 13.5 }}>By agent</div>
            <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.5fr 0.65fr 0.85fr 0.5fr", gap: 12, padding: "9px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
              {["Agent", "Runs", "Success", "Total cost", "Grade"].map((h, i) => (
                <div key={i} className="eyebrow" style={{ fontSize: 9.5, textAlign: i > 0 ? "right" : "left" }}>{h}</div>
              ))}
            </div>
            {(analytics?.top_playbooks ?? []).length === 0 ? (
              <div style={{ padding: "20px 18px", fontSize: 12, color: "var(--text-muted)" }}>No playbook data yet.</div>
            ) : (
              (analytics?.top_playbooks ?? []).map(p => {
                const sc = scorecards.get(p.playbook_slug)
                const [gc, gbg] = sc ? gradeColor(sc.grade) : ["var(--text-muted)", "var(--surface-3)"]
                return (
                  <div key={p.playbook_slug} style={{ display: "grid", gridTemplateColumns: "1.4fr 0.5fr 0.65fr 0.85fr 0.5fr", gap: 12, padding: "11px 18px", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                    <div className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{p.playbook_slug}</div>
                    <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)", textAlign: "right" }}>{p.run_count}</div>
                    <div className="mono" style={{ fontSize: 12.5, textAlign: "right", color: p.success_rate >= 0.8 ? "var(--ok)" : "var(--err)" }}>{Math.round(p.success_rate * 100)}%</div>
                    <div className="mono" style={{ fontSize: 12.5, fontWeight: 700, textAlign: "right" }}>${p.total_cost_usd.toFixed(4)}</div>
                    <div style={{ textAlign: "right" }}>
                      {sc
                        ? <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 24, height: 24, borderRadius: 6, fontSize: 11, fontWeight: 700, color: gc, background: gbg }}>{sc.grade}</span>
                        : <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
                      }
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {/* Recent events */}
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 13.5, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Recent events</span>
              <Link href="/observability/alerts" style={{ fontSize: 12, color: "var(--accent)", fontWeight: 400 }}>View all</Link>
            </div>
            <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {(summary?.recent_events ?? []).length === 0 ? (
              <div style={{ padding: "20px 18px", fontSize: 12, color: "var(--text-muted)" }}>No recent events.</div>
            ) : (
              (summary?.recent_events ?? []).slice(0, 5).map((ev, i, arr) => (
                <div key={ev.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "11px 18px", borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none" }}>
                  <span className={`sbadge ${ev.severity === "error" ? "err" : ev.severity === "warning" ? "warn" : "run"}`} style={{ height: 18, fontSize: 9.5, textTransform: "capitalize", marginTop: 1 }}>{ev.severity}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, color: "var(--text-2)" }}>{EVENT_LABELS[ev.event_type] ?? ev.event_type}</div>
                    {ev.run_id && <div className="mono" style={{ fontSize: 10.5, color: "var(--text-muted)" }}>run {ev.run_id}</div>}
                  </div>
                  <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>{timeAgo(ev.created_at)}</span>
                </div>
              ))
            )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
