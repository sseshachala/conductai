"use client"

import Link from "next/link"

const displayEmail = (v: string | null | undefined): string => {
  if (!v) return "—"
  // Strip synthetic prefixes from legacy rows
  if (v.startsWith("agt:")) v = v.slice(4).split("@")[0]
  if (v.startsWith("api:")) v = v.slice(4).split("@")[0]
  if (v.startsWith("user_")) return "unknown user"
  return v
}
import { useEffect, useState, useCallback, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import ToolActivityTable from "@/components/guard/ToolActivityTable"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { GuardShell } from "@/components/guard/GuardShell"
import { ActivityRow, ActivityHeader, ToolBadge, DecisionBadge, BlastRadiusBadge, formatTs, type AuditEvent } from "@/components/guard/ActivityRow"

// ─── Types ────────────────────────────────────────────────────────────────────

// AuditEvent shape lives in the shared component — keep one definition.

interface SessionReport {
  id: string
  developer_email: string
  archetype: string | null
  autonomy_score: number | null
  sessions: number
  commits: number
  lines_per_hour: number | null
  created_at: string
  report_md: string | null
}

function formatReportDate(ts: string) {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

interface GuardSession {
  id: string
  user_email: string | null
  ai_tool: string
  started_at: string | null
  ended_at: string | null
  event_count: number
  violations_count: number
  total_cost_usd: number
  total_saved_usd: number
  client_ip: string | null
  os_info: string | null
  hostname: string | null
  intent: string | null
  session_parse_status: string | null
}


function exportCsv(events: AuditEvent[]) {
  const header = "timestamp,developer,ai_tool,tool_call,input_summary,decision,rule_id\n"
  const rows = events.map(e => {
    const cols = [
      e.ts, e.user_email ?? "", e.ai_tool, e.tool_call,
      `"${(e.input_summary ?? "").replace(/"/g, '""')}"`,
      e.decision, e.rule_id ?? "",
    ]
    return cols.join(",")
  })
  const csv = header + rows.join("\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `conduct-guard-activity-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a); a.click(); document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const PAGE_SIZE = 50

// ─── Shared select style ──────────────────────────────────────────────────────

const selectStyle: React.CSSProperties = {
  fontSize: 12,
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "5px 10px",
  color: "var(--text-2)",
  background: "var(--surface)",
  outline: "none",
  cursor: "pointer",
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ActivityPage() {
  return <AppShell><ActivityContent /></AppShell>
}

function ActivityContent() {
  const { getToken } = useAuth()
  const { authFetch } = useAuthFetch()
  const { user } = useUser()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [activeView, setActiveView] = useState<"events" | "sessions" | "tools" | "session_reports">("events")
  const [reports, setReports] = useState<SessionReport[]>([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState<string | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [sessions, setSessions] = useState<GuardSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [sessionsError, setSessionsError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const offsetRef = useRef(0)
  const esRef = useRef<EventSource | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [chainStatus, setChainStatus] = useState<{ valid: boolean; total: number; verified_from: string | null } | null>(null)
  const [advisoryMode, setAdvisoryMode] = useState(false)

  // View mode — grouped is default
  const [groupByGoal, setGroupByGoal] = useState(true)
  // Collapsed state for workflow groups: key = workflow name (or "adhoc")
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})

  // Filters
  const [filterDecision, setFilterDecision] = useState("")
  const [filterDeveloper, setFilterDeveloper] = useState("")
  const [filterTool, setFilterTool] = useState("")
  const [filterSince, setFilterSince] = useState("")
  const [filterUntil, setFilterUntil] = useState("")
  const [filterRuleId, setFilterRuleId] = useState("")

  // Fetch audit chain status + advisory mode on load
  useEffect(() => {
    if (!teamId) return
    authFetch(`${API}/guard/events/audit/verify?workspace_id=${teamId}`)
      .then((r: Response) => r.ok ? r.json() : null)
      .then((d: unknown) => d && setChainStatus(d as Parameters<typeof setChainStatus>[0]))
      .catch(() => {})
    authFetch(`${API}/guard/config?workspace_id=${teamId}`)
      .then((r: Response) => r.ok ? r.json() : null)
      .then((d: Record<string, unknown> | null) => d && setAdvisoryMode(d.advisory_mode as boolean ?? false))
      .catch(() => {})
  }, [teamId])

  // Hydrate filters from URL on first load — lets callers like the governance
  // dashboard deep-link with ?rule_id=foo or ?decision=blocked.
  const searchParams = useSearchParams()
  useEffect(() => {
    if (!searchParams) return
    const d = searchParams.get("decision")
    if (d) setFilterDecision(d)
    const t = searchParams.get("ai_tool")
    if (t) setFilterTool(t)
    const r = searchParams.get("rule_id")
    if (r) setFilterRuleId(r)
    const s = searchParams.get("since")
    if (s) setFilterSince(s)
    const u = searchParams.get("until")
    if (u) setFilterUntil(u)
    // dev override left out — admins viewing all is the default; per-user
    // restriction kicks in via effectiveDeveloperFilter below.
  }, [searchParams])

  const currentUserEmail = user?.primaryEmailAddress?.emailAddress ?? null

  const developers = Array.from(new Set(events.map(e => e.user_email).filter(Boolean) as string[])).sort()
  const tools = Array.from(new Set(events.map(e => e.ai_tool).filter(Boolean) as string[])).sort()

  const effectiveDeveloperFilter = !permissions.canViewAllActivity && currentUserEmail
    ? currentUserEmail
    : filterDeveloper

  function buildParams(offset: number) {
    const p = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
    if (teamId) p.set("workspace_id", teamId)
    if (effectiveDeveloperFilter) p.set("user_email", effectiveDeveloperFilter)
    if (filterTool) p.set("ai_tool", filterTool)
    if (filterDecision) p.set("decision", filterDecision)
    if (filterRuleId) p.set("rule_id", filterRuleId)
    if (filterSince) p.set("since", filterSince)
    if (filterUntil) p.set("until", filterUntil)
    return p.toString()
  }

  useEffect(() => {
    if (!teamLoading && !teamId) setLoading(false)
  }, [teamLoading, teamId])

  const load = useCallback(async () => {
    if (!teamId) return
    setLoading(true)
    setError(null)
    offsetRef.current = 0
    try {
      const res = await authFetch(`${API}/guard/events?${buildParams(0)}`)
      if (!res.ok) throw new Error("Failed to load activity events")
      const rows: AuditEvent[] = await res.json()
      setEvents(rows)
      setHasMore(rows.length === PAGE_SIZE)
      offsetRef.current = rows.length
      setLive(true)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setLive(false)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch, teamId, effectiveDeveloperFilter, filterTool, filterDecision, filterSince, filterUntil, filterRuleId])

  const loadSessions = useCallback(async () => {
    if (!teamId) return
    setSessionsLoading(true)
    setSessionsError(null)
    try {
      const p = new URLSearchParams({ limit: "100", offset: "0" })
      if (teamId) p.set("workspace_id", teamId)
      const res = await authFetch(`${API}/guard/spend/sessions?${p}`)
      if (!res.ok) throw new Error("Failed to load sessions")
      setSessions(await res.json())
    } catch (err) {
      setSessionsError(err instanceof Error ? err.message : "Failed to load sessions")
    } finally {
      setSessionsLoading(false)
    }
  }, [authFetch, teamId])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  // SSE real-time feed — only active when streaming=true (user clicked Go Live)
  const LIVE_EVENT_CAP = 500
  useEffect(() => {
    if (!streaming || !teamId) return
    let es: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const connect = async (forceRefresh = false) => {
      const token = await getToken({ skipCache: forceRefresh } as Parameters<typeof getToken>[0])
      if (!token) return
      const url = `${API}/guard/events/stream?workspace_id=${teamId}&token=${encodeURIComponent(token)}`
      es = new EventSource(url)
      esRef.current = es
      es.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.kind === "stream_timeout") {
            es?.close()
            // planned reconnect — refresh token in case it aged during the 5min stream
            reconnectTimer = setTimeout(() => connect(true), 1000)
            return
          }
          if (Array.isArray(msg.events) && msg.events.length > 0) {
            setEvents(prev => {
              const ids = new Set(prev.map(ev => ev.id))
              const fresh = (msg.events as AuditEvent[]).filter(ev => !ids.has(ev.id))
              if (!fresh.length) return prev
              return [...fresh.reverse(), ...prev].slice(0, LIVE_EVENT_CAP)
            })
            setLastUpdated(new Date())
          }
        } catch { /* ignore parse errors */ }
      }
      es.onerror = () => {
        es?.close()
        // force-refresh token on error — stale token is the most common cause of 403 on reconnect
        reconnectTimer = setTimeout(() => connect(true), 5000)
      }
    }

    connect()
    return () => {
      es?.close()
      esRef.current = null
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [streaming, teamId, getToken])

  const loadReports = useCallback(async () => {
    if (!teamId) return
    setReportsLoading(true)
    setReportsError(null)
    try {
      const res = await authFetch(`${API}/guard/session-reports?workspace_id=${teamId}`)
      if (!res.ok) throw new Error(`Failed to load session reports (${res.status})`)
      const data: SessionReport[] = await res.json()
      data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      setReports(data)
    } catch (err) {
      setReportsError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setReportsLoading(false)
    }
  }, [authFetch, teamId])

  useEffect(() => {
    if (activeView !== "sessions") return
    loadSessions()
    const t = setInterval(loadSessions, 60_000)
    return () => clearInterval(t)
  }, [activeView, loadSessions])

  useEffect(() => {
    if (activeView !== "session_reports") return
    loadReports()
  }, [activeView, loadReports])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const res = await authFetch(`${API}/guard/events?${buildParams(offsetRef.current)}`)
      if (!res.ok) throw new Error("Failed to load more events")
      const rows: AuditEvent[] = await res.json()
      setEvents(prev => [...prev, ...rows])
      setHasMore(rows.length === PAGE_SIZE)
      offsetRef.current += rows.length
    } catch {
      // non-fatal
    } finally {
      setLoadingMore(false)
    }
  }

  // ─── Grouping helpers ──────────────────────────────────────────────────────

  type RunGroup = { runId: string | null; events: AuditEvent[] }
  type WorkflowGroup = { workflowName: string; workflowId: string | null; runs: RunGroup[] }

  function buildGoalGroups(evts: AuditEvent[]): { named: WorkflowGroup[]; adhoc: AuditEvent[] } {
    const wfMap = new Map<string, WorkflowGroup>()
    const adhoc: AuditEvent[] = []

    for (const ev of evts) {
      const wfName = ev.conductai_workflow ?? ev.goal_name ?? null
      if (!wfName) {
        adhoc.push(ev)
        continue
      }
      if (!wfMap.has(wfName)) {
        wfMap.set(wfName, { workflowName: wfName, workflowId: ev.conductai_workflow_id ?? null, runs: [] })
      }
      const wfGroup = wfMap.get(wfName)!
      const runId = ev.conductai_run_id ?? null
      let runGroup = wfGroup.runs.find(r => r.runId === runId)
      if (!runGroup) {
        runGroup = { runId, events: [] }
        wfGroup.runs.push(runGroup)
      }
      runGroup.events.push(ev)
    }

    return { named: Array.from(wfMap.values()), adhoc }
  }

  function toggleGroup(key: string) {
    setCollapsedGroups(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <GuardShell live={live} lastFetched={lastUpdated} advisory={advisoryMode}>
      {/* Viewer-scoped notice */}
      {!permissionsLoading && !permissions.canViewAllActivity && (
        <div
          style={{
            borderRadius: 8,
            border: "1px solid var(--warn-bd)",
            background: "var(--warn-bg)",
            padding: "8px 16px",
            fontSize: 12,
            color: "var(--warn)",
            marginBottom: 16,
          }}
        >
          You can view your own activity only. Contact your admin to request broader access.
        </div>
      )}

      {/* Audit chain badge */}
      {chainStatus && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
          <span style={{
            fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20,
            background: chainStatus.valid ? "var(--ok-bg)" : "var(--block-bg)",
            color: chainStatus.valid ? "var(--ok)" : "var(--block)",
            border: `1px solid ${chainStatus.valid ? "var(--ok-bd)" : "var(--block-bd)"}`,
          }}>
            {chainStatus.valid ? "Chain verified" : "Chain broken"}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {chainStatus.total} chained {chainStatus.total === 1 ? "event" : "events"}
            {chainStatus.verified_from && ` from ${new Date(chainStatus.verified_from).toLocaleDateString()}`}
          </span>
        </div>
      )}

      {/* View toggle */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {(["events", "sessions", "tools", "session_reports"] as const).map(v => (
          <button
            key={v}
            onClick={() => setActiveView(v)}
            style={{
              fontSize: 12, fontWeight: 600, padding: "5px 14px", borderRadius: 20,
              border: "1px solid",
              borderColor: activeView === v ? "var(--accent-ring)" : "var(--border)",
              background: activeView === v ? "var(--accent-weak)" : "var(--surface)",
              color: activeView === v ? "var(--accent-text)" : "var(--text-2)",
              cursor: "pointer",
            }}
          >
            {v === "events" ? "Flight Recorder" : v === "sessions" ? "Sessions & Machines" : v === "tools" ? "Tool Errors & Warnings" : "Session Reports"}
          </button>
        ))}
      </div>

      {/* Filter chips + realtime indicator */}
      {activeView === "events" && (<div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16, flexWrap: "wrap" }}>
        {/* Decision filter chips */}
        {["", "blocked", "warned", "allowed"].map(d => {
          const label = d === "" ? "All" : d.charAt(0).toUpperCase() + d.slice(1)
          const active = filterDecision === d
          return (
            <button
              key={d}
              onClick={() => setFilterDecision(d)}
              className="chip"
              style={{
                height: 30,
                fontWeight: 600,
                background: active ? "var(--accent-weak)" : "var(--surface)",
                borderColor: active ? "var(--accent-ring)" : "var(--border)",
                color: active ? "var(--accent-text)" : "var(--text-2)",
              }}
            >
              {label}
            </button>
          )
        })}

        {/* More filters */}
        {!permissionsLoading && permissions.canViewAllActivity && (
          <select
            value={filterDeveloper}
            onChange={e => setFilterDeveloper(e.target.value)}
            style={selectStyle}
          >
            <option value="">All developers</option>
            {developers.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}

        <select
          value={filterTool}
          onChange={e => setFilterTool(e.target.value)}
          style={selectStyle}
        >
          <option value="">All tools</option>
          {tools.map(t => {
            const TOOL_NAMES: Record<string, string> = {
              "claude-code": "Claude Code", "claude_code": "Claude Code",
              "claude_chat": "Claude.ai", "claude-chat": "Claude.ai",
              "claude_desktop": "Claude Desktop", "claude-desktop": "Claude Desktop",
              "claude_work": "Claude Work", "claude-work": "Claude Work",
              "codex": "Codex", "codex_cli": "Codex CLI", "codex_chat": "Codex Chat",
              "cursor": "Cursor", "windsurf": "Windsurf", "copilot": "Copilot", "gemini": "Gemini",
            }
            return <option key={t} value={t}>{TOOL_NAMES[t] ?? t}</option>
          })}
        </select>

        <input
          type="date"
          value={filterSince}
          onChange={e => setFilterSince(e.target.value)}
          style={selectStyle}
          aria-label="From date"
        />
        <input
          type="date"
          value={filterUntil}
          onChange={e => setFilterUntil(e.target.value)}
          style={selectStyle}
          aria-label="To date"
        />

        {filterRuleId && (
          <span style={{
            fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 12,
            background: "var(--accent-weak)", color: "var(--accent-text)",
            display: "inline-flex", alignItems: "center", gap: 6,
          }}>
            rule: <span style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)" }}>{filterRuleId}</span>
            <button onClick={() => setFilterRuleId("")} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", padding: 0, lineHeight: 1 }} aria-label="Clear rule filter">×</button>
          </span>
        )}

        {(filterDeveloper || filterTool || filterSince || filterUntil || filterRuleId) && (
          <button
            onClick={() => {
              if (permissions.canViewAllActivity) setFilterDeveloper("")
              setFilterTool(""); setFilterSince(""); setFilterUntil(""); setFilterRuleId("")
            }}
            style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}
          >
            Clear filters
          </button>
        )}

        {/* Realtime indicator */}
        <span style={{ marginLeft: "auto", fontSize: 12.5, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="conduct-pulse-dot" style={{ background: "var(--ok)" }} />
          Realtime · every tool call logged
        </span>

        {/* Group by goal toggle */}
        <button
          onClick={() => setGroupByGoal(g => !g)}
          className="btn btn-ghost btn-sm"
          style={{ fontSize: 11, fontWeight: groupByGoal ? 700 : 400 }}
          title={groupByGoal ? "Switch to flat event list" : "Group events by workflow goal"}
        >
          {groupByGoal ? "All events" : "Group by goal"}
        </button>

        {/* Go Live toggle */}
        <button
          onClick={() => setStreaming(s => !s)}
          className={`btn btn-sm ${streaming ? "btn-ghost" : ""}`}
          style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 5 }}
        >
          {streaming && <span className="conduct-pulse-dot" style={{ background: "var(--ok)" }} />}
          {streaming ? "Stop" : "Go Live"}
        </button>

        {/* Export CSV */}
        {permissions.canExportActivity && (
          <button
            onClick={() => exportCsv(events)}
            disabled={events.length === 0}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 11 }}
          >
            Export CSV
          </button>
        )}

        {/* SOC 2 PDF Report */}
        {permissions.canExportActivity && (
          <a
            href="/theguard/reports/soc2"
            target="_blank"
            rel="noopener"
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 11, textDecoration: "none" }}
          >
            SOC 2 Report →
          </a>
        )}
      </div>)}

      {/* Sessions & Machines view */}
      {activeView === "sessions" && sessionsError && (
        <div
          style={{
            borderRadius: 8,
            border: "1px solid var(--err-bd)",
            background: "var(--err-bg)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--err)",
            marginBottom: 16,
          }}
        >
          {sessionsError}
        </div>
      )}
      {activeView === "sessions" && (
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr 0.9fr 0.8fr 0.8fr 0.7fr 0.7fr 1.2fr 1.4fr",
            gap: 12, padding: "10px 18px",
            borderBottom: "1px solid var(--border)", background: "var(--surface-2)",
          }}>
            {["Developer", "Tool", "Started", "Events", "Violations", "Cost", "Saved", "Machine / IP", "OS"].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
            ))}
          </div>
          {sessionsLoading ? (
            [...Array(4)].map((_, i) => (
              <div key={i} style={{ height: 44, background: "var(--surface-2)", borderRadius: 0, opacity: 0.5, borderBottom: "1px solid var(--border)" }} />
            ))
          ) : sessions.length === 0 ? (
            <div style={{ padding: "32px 18px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
              No sessions found.
            </div>
          ) : sessions.map((s, i) => (
            <div key={s.id} style={{
              display: "grid",
              gridTemplateColumns: "1.4fr 1fr 0.9fr 0.8fr 0.8fr 0.7fr 0.7fr 1.2fr 1.4fr",
              gap: 12, padding: "11px 18px", alignItems: "center",
              borderBottom: i < sessions.length - 1 ? "1px solid var(--border)" : "none",
            }}>
              <div style={{ overflow: "hidden" }}>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{displayEmail(s.user_email)}</div>
                {s.intent && s.session_parse_status !== "failed" && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 2 }}>{s.intent}</div>
                )}
              </div>
              <div><ToolBadge tool={s.ai_tool} /></div>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {s.started_at ? formatTs(s.started_at) : "—"}
              </div>
              <div style={{ fontSize: 12 }}>{s.event_count}</div>
              <div style={{ fontSize: 12, color: s.violations_count > 0 ? "var(--err)" : "var(--text-muted)", fontWeight: s.violations_count > 0 ? 600 : 400 }}>
                {s.violations_count}
              </div>
              <div className="mono" style={{ fontSize: 11.5 }}>${s.total_cost_usd.toFixed(4)}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--ok)" }}>${s.total_saved_usd.toFixed(4)}</div>
              <div style={{ fontSize: 11, color: "var(--text-3)" }}>
                <div className="mono" style={{ fontWeight: 600, color: "var(--text-2)" }}>{s.hostname ?? "—"}</div>
                <div style={{ marginTop: 2, color: "var(--text-muted)" }}>{s.client_ip ?? ""}</div>
              </div>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.os_info ?? "—"}
              </div>
            </div>
          ))}
          {sessions.length > 0 && (
            <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
              {sessions.length} session{sessions.length !== 1 ? "s" : ""}
            </div>
          )}
          {sessions.length >= 100 && (
            <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", fontSize: 12, color: "var(--warn)", textAlign: "center" }}>
              Showing 100 sessions — older sessions may not be visible.
            </div>
          )}
        </div>
      )}

      {activeView === "tools" && (
        <ToolActivityTable workspaceId={teamId} />
      )}

      {activeView === "session_reports" && (
        reportsError ? (
          <div style={{ borderRadius: 8, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>
            {reportsError}
          </div>
        ) : reportsLoading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[...Array(4)].map((_, i) => <div key={i} style={{ height: 44, background: "var(--surface-2)", borderRadius: 8, opacity: 0.6 }} />)}
          </div>
        ) : reports.length === 0 ? (
          <div className="card" style={{ padding: "40px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No session reports yet. Developers run <code style={{ fontSize: 12 }}>conduct session-report</code> to push data here.
          </div>
        ) : (
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1.2fr 0.6fr 0.6fr 0.7fr 0.6fr 0.9fr 0.5fr", gap: 12, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
              {["Developer", "Archetype", "Sessions", "Commits", "Autonomy", "Lines/hr", "Date", "Report"].map(h => (
                <div key={h} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
              ))}
            </div>
            {reports.map((r, i) => (
              <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1.8fr 1.2fr 0.6fr 0.6fr 0.7fr 0.6fr 0.9fr 0.5fr", gap: 12, padding: "11px 18px", borderBottom: i < reports.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center" }}>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.developer_email}</div>
                <div>{r.archetype ? <span style={{ fontSize: 11, fontWeight: 500, color: "var(--accent-text)", background: "var(--accent-weak)", borderRadius: 6, padding: "2px 8px" }}>{r.archetype}</span> : <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>}</div>
                <div style={{ fontSize: 12.5 }}>{r.sessions}</div>
                <div style={{ fontSize: 12.5 }}>{r.commits}</div>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: r.autonomy_score != null ? (r.autonomy_score >= 70 ? "var(--ok)" : r.autonomy_score >= 40 ? "var(--warn)" : "var(--text-2)") : "var(--text-muted)" }}>
                  {r.autonomy_score != null ? r.autonomy_score.toFixed(1) : "—"}
                </div>
                <div style={{ fontSize: 12.5 }}>{r.lines_per_hour != null ? Math.round(r.lines_per_hour) : <span style={{ color: "var(--text-muted)" }}>—</span>}</div>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{formatReportDate(r.created_at)}</div>
                <div><Link href={`/theguard/session-reports/${r.id}`} style={{ fontSize: 12, color: "var(--accent-text)", textDecoration: "none", fontWeight: 500 }}>View →</Link></div>
              </div>
            ))}
            <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
              {reports.length} {reports.length === 1 ? "report" : "reports"}
            </div>
          </div>
        )
      )}

      {activeView === "events" && error && (
        <div
          style={{
            borderRadius: 8,
            border: "1px solid var(--err-bd)",
            background: "var(--err-bg)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--err)",
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {/* Events table */}
      {activeView === "events" && (loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              style={{
                height: 44,
                background: "var(--surface-2)",
                borderRadius: 8,
                opacity: 0.6,
              }}
            />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="card" style={{ padding: "40px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          No activity events found for the selected filters.
        </div>
      ) : groupByGoal ? (
        /* ── Grouped view ─────────────────────────────────────────────────── */
        (() => {
          const { named, adhoc } = buildGoalGroups(events)
          const tableHeader = (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr 0.9fr",
                gap: 12,
                padding: "10px 18px",
                borderBottom: "1px solid var(--border)",
                background: "var(--surface-2)",
              }}
            >
              {["Time", "Developer", "Tool", "Call", "Input", "Decision", "Rule", "Blast Radius"].map((h, i) => (
                <div
                  key={i}
                  className="eyebrow"
                  style={{ fontSize: 9.5 }}
                  title={h === "Blast Radius" ? "Risk tier (CRITICAL/HIGH/MEDIUM/LOW) + affected files count (f)" : undefined}
                >
                  {h}
                </div>
              ))}
            </div>
          )

          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Named workflow groups */}
              {named.map(wfGroup => {
                const wfKey = wfGroup.workflowName
                const isCollapsed = collapsedGroups[wfKey] ?? false
                const totalEvents = wfGroup.runs.reduce((s, r) => s + r.events.length, 0)
                const blockedCount = wfGroup.runs.reduce((s, r) => s + r.events.filter(e => e.decision === "blocked").length, 0)
                const warnedCount = wfGroup.runs.reduce((s, r) => s + r.events.filter(e => e.decision === "warned").length, 0)

                return (
                  <div key={wfKey} className="card" style={{ overflow: "hidden" }}>
                    {/* Workflow group header */}
                    <button
                      onClick={() => toggleGroup(wfKey)}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        width: "100%", textAlign: "left",
                        padding: "12px 18px",
                        background: "var(--surface-2)",
                        border: "none",
                        borderBottom: isCollapsed ? "none" : "1px solid var(--border)",
                        cursor: "pointer",
                      }}
                    >
                      <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1 }}>
                        {isCollapsed ? "▶" : "▼"}
                      </span>
                      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", color: "var(--text-muted)" }}>
                        Goal
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                        {wfGroup.workflowName}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 4 }}>
                        {totalEvents} event{totalEvents !== 1 ? "s" : ""} · {wfGroup.runs.length} run{wfGroup.runs.length !== 1 ? "s" : ""}
                      </span>
                      {blockedCount > 0 && (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                          background: "var(--block-bg)", color: "var(--block)", border: "1px solid var(--block-bd)",
                        }}>
                          {blockedCount} blocked
                        </span>
                      )}
                      {warnedCount > 0 && (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                          background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)",
                        }}>
                          {warnedCount} warned
                        </span>
                      )}
                    </button>

                    {!isCollapsed && wfGroup.runs.map((runGroup, ri) => {
                      const runKey = `${wfKey}::${runGroup.runId ?? `adhoc-${ri}`}`
                      const isRunCollapsed = collapsedGroups[runKey] ?? false

                      return (
                        <div key={runKey} style={{ borderBottom: ri < wfGroup.runs.length - 1 ? "1px solid var(--border)" : "none" }}>
                          {/* Run sub-header */}
                          <button
                            onClick={() => toggleGroup(runKey)}
                            style={{
                              display: "flex", alignItems: "center", gap: 8,
                              width: "100%", textAlign: "left",
                              padding: "9px 18px 9px 36px",
                              background: "transparent",
                              border: "none",
                              borderBottom: isRunCollapsed ? "none" : "1px solid var(--border)",
                              cursor: "pointer",
                            }}
                          >
                            <span style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1 }}>
                              {isRunCollapsed ? "▶" : "▼"}
                            </span>
                            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: "var(--text-muted)" }}>
                              Run
                            </span>
                            {runGroup.runId ? (
                              <Link
                                href={`/runs/${runGroup.runId}`}
                                onClick={e => e.stopPropagation()}
                                style={{ fontSize: 11.5, fontFamily: "var(--font-mono, ui-monospace, monospace)", color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}
                              >
                                {runGroup.runId}
                              </Link>
                            ) : (
                              <span style={{ fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>no run id</span>
                            )}
                            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                              {runGroup.events.length} event{runGroup.events.length !== 1 ? "s" : ""}
                            </span>
                          </button>

                          {!isRunCollapsed && (
                            <div>
                              {tableHeader}
                              {runGroup.events.map((ev, i) => (
                                <ActivityRow key={ev.id} ev={ev} isLast={i === runGroup.events.length - 1} />
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )
              })}

              {/* Ad-hoc events (no workflow) */}
              {adhoc.length > 0 && (() => {
                const adhocKey = "__adhoc__"
                const isCollapsed = collapsedGroups[adhocKey] ?? false
                const blockedCount = adhoc.filter(e => e.decision === "blocked").length
                const warnedCount = adhoc.filter(e => e.decision === "warned").length
                return (
                  <div className="card" style={{ overflow: "hidden" }}>
                    <button
                      onClick={() => toggleGroup(adhocKey)}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        width: "100%", textAlign: "left",
                        padding: "12px 18px",
                        background: "var(--surface-2)",
                        border: "none",
                        borderBottom: isCollapsed ? "none" : "1px solid var(--border)",
                        cursor: "pointer",
                      }}
                    >
                      <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1 }}>
                        {isCollapsed ? "▶" : "▼"}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-2)" }}>
                        Ad-hoc sessions
                      </span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {adhoc.length} event{adhoc.length !== 1 ? "s" : ""} · no workflow attached
                      </span>
                      {blockedCount > 0 && (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                          background: "var(--block-bg)", color: "var(--block)", border: "1px solid var(--block-bd)",
                        }}>
                          {blockedCount} blocked
                        </span>
                      )}
                      {warnedCount > 0 && (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                          background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)",
                        }}>
                          {warnedCount} warned
                        </span>
                      )}
                    </button>
                    {!isCollapsed && (
                      <div>
                        {tableHeader}
                        {adhoc.map((ev, i) => (
                          <ActivityRow key={ev.id} ev={ev} isLast={i === adhoc.length - 1} />
                        ))}
                      </div>
                    )}
                  </div>
                )
              })()}

              {/* Load more */}
              {hasMore && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 0" }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Showing {events.length} events</span>
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    style={{ fontSize: 12, color: "var(--accent-text)", background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}
                  >
                    {loadingMore ? "Loading…" : "Load more"}
                  </button>
                </div>
              )}
              {!hasMore && events.length > 0 && (
                <div style={{ textAlign: "center", fontSize: 12, color: "var(--text-muted)", padding: "4px 0" }}>
                  {events.length} event{events.length !== 1 ? "s" : ""} total
                </div>
              )}
            </div>
          )
        })()
      ) : (
        /* ── Flat view ────────────────────────────────────────────────────── */
        <div className="card" style={{ overflow: "hidden" }}>
          {/* Table header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr 0.9fr",
              gap: 12,
              padding: "10px 18px",
              borderBottom: "1px solid var(--border)",
              background: "var(--surface-2)",
            }}
          >
            {["Time", "Developer", "Tool", "Call", "Input", "Decision", "Rule", "Blast Radius"].map((h, i) => (
              <div
                key={i}
                className="eyebrow"
                style={{ fontSize: 9.5 }}
                title={h === "Blast Radius" ? "Risk tier (CRITICAL/HIGH/MEDIUM/LOW) + affected files count (f)" : undefined}
              >
                {h}
              </div>
            ))}
          </div>

          {/* Table rows */}
          {events.map((ev, i) => (
            <ActivityRow key={ev.id} ev={ev} isLast={i === events.length - 1} />
          ))}

          {/* Load more / count */}
          {hasMore && (
            <div style={{ borderTop: "1px solid var(--border)", padding: "12px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Showing {events.length} events</span>
              <button
                onClick={loadMore}
                disabled={loadingMore}
                style={{ fontSize: 12, color: "var(--accent-text)", background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
          {!hasMore && events.length > 0 && (
            <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
              {events.length} event{events.length !== 1 ? "s" : ""} total
            </div>
          )}
        </div>
      ))}
    </GuardShell>
  )
}
