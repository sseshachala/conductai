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
import { useEffect, useState, useCallback, useRef, type MouseEvent as ReactMouseEvent } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
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
import {
  GuardFilterBar,
  GuardPageHeader,
  GuardToolbar,
  ALL_COLUMNS,
  DEFAULT_VISIBLE_COLUMNS,
  loadVisibleColumns,
  saveVisibleColumns,
  type ColumnKey,
  type FilterPill,
} from "@/components/guard/common"

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
  const [activeView, _setActiveView] = useState<"events" | "sessions" | "tools" | "session_reports">("events")
  const [reports, setReports] = useState<SessionReport[]>([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState<string | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  // #1990 item D — drift between server clock and browser clock. When a
  // SSE payload carries server_time, we recompute (client_now - server_now).
  // LifecyclePill uses this to correct client-side 'expired' detection so
  // a badly-skewed browser doesn't render rows as ∅ that aren't expired
  // server-side. 0 = no drift / not yet initialized.
  const [serverTimeDrift, setServerTimeDrift] = useState<number>(0)
  // #1959 Phase 3 — count of currently-in-flight durable rows. Derived
  // client-side so the badge stays in sync with the same event stream
  // that drives the table, no extra endpoint needed.
  const inFlightCount = events.filter(ev => ev.lifecycle_state === "accepted").length
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

  // #1982 — visible columns for the Flight Recorder table. Default matches
  // the acceptance criteria; localStorage restore happens after mount so
  // SSR/CSR match.
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(DEFAULT_VISIBLE_COLUMNS)
  useEffect(() => { setVisibleColumns(loadVisibleColumns()) }, [])
  const applyVisibleColumns = useCallback((cols: ColumnKey[]) => {
    setVisibleColumns(cols)
    saveVisibleColumns(cols)
  }, [])

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

  // Hydrate filters + active view from URL on first load — lets callers like
  // the governance dashboard deep-link with ?rule_id=foo or ?decision=blocked,
  // and lets the Session Reports redirect land on ?view=session_reports.
  const searchParams = useSearchParams()
  const filterHookSession = searchParams?.get("hook_session_id") || ""
  const filterAgentIdentity = searchParams?.get("agent_identity_id") || ""
  const _router = useRouter()
  const _pathname = usePathname()

  // Setter used by view-toggle buttons: writes the new view to the URL so
  // deep links (/logs/guard?view=session_reports) round-trip cleanly.
  // Uses replace so tab-switching doesn't stack history entries.
  const setActiveView = useCallback((v: "events" | "sessions" | "tools" | "session_reports") => {
    _setActiveView(v)
    const params = new URLSearchParams(searchParams?.toString() ?? "")
    if (v === "events") params.delete("view")
    else params.set("view", v)
    const qs = params.toString()
    _router.replace(qs ? `${_pathname}?${qs}` : (_pathname ?? "/logs/guard"))
  }, [_pathname, _router, searchParams])
  useEffect(() => {
    if (!searchParams) return
    const v = searchParams.get("view")
    if (v === "events" || v === "sessions" || v === "tools" || v === "session_reports") {
      _setActiveView(v)
    }
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
    if (filterHookSession) p.set("hook_session_id", filterHookSession)
    if (filterAgentIdentity) p.set("agent_identity_id", filterAgentIdentity)
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
  }, [authFetch, teamId, effectiveDeveloperFilter, filterTool, filterDecision, filterSince, filterUntil, filterRuleId, filterHookSession, filterAgentIdentity])

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
          // #1990 item D — reset drift on every payload. Server_time
          // is an ISO string emitted by /guard/events/stream.
          if (typeof msg.server_time === "string") {
            const serverMs = Date.parse(msg.server_time)
            if (!Number.isNaN(serverMs)) {
              setServerTimeDrift(Date.now() - serverMs)
            }
          }
          if (Array.isArray(msg.events) && msg.events.length > 0) {
            setEvents(prev => {
              // Split incoming into updates (id already in list — durable
              // finalize UPDATE) and fresh rows so the lifecycle pill flips
              // in place (#1959 Phase 3). Fresh rows still prepend as before.
              const byId = new Map(prev.map(ev => [ev.id, ev] as const))
              const incoming = (msg.events as AuditEvent[]).filter(ev =>
                (!filterHookSession || ev.hook_session_id === filterHookSession)
                && (!filterAgentIdentity || ev.agent_identity_id === filterAgentIdentity)
              )
              const fresh: AuditEvent[] = []
              let anyUpdate = false
              for (const ev of incoming) {
                if (byId.has(ev.id)) {
                  byId.set(ev.id, ev)
                  anyUpdate = true
                } else {
                  fresh.push(ev)
                }
              }
              if (!fresh.length && !anyUpdate) return prev
              const merged = prev.map(ev => byId.get(ev.id) ?? ev)
              return [...fresh.reverse(), ...merged].slice(0, LIVE_EVENT_CAP)
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
  }, [streaming, teamId, getToken, filterHookSession, filterAgentIdentity])

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

      <GuardPageHeader
        title="Activity"
        description="Real-time firehose of every AI tool call routed through Guard. Every row is chained and audit-verifiable."
        lastUpdated={lastUpdated}
      />

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
            {inFlightCount > 0 && (
              <span
                title="Durable-audit rows still in the accepted state — waiting for finalize()"
                style={{ marginLeft: 10, padding: "1px 6px", fontSize: 10.5, fontWeight: 700,
                         color: "#7c3aed", background: "#ede9fe", border: "1px solid #c4b5fd",
                         borderRadius: 3 }}
              >
                ⏳ {inFlightCount} in flight
              </span>
            )}
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

      {/* Consolidated toolbar — #1982 */}
      {activeView === "events" && (
        <GuardToolbar<ColumnKey>
          streaming={streaming}
          onStreamingToggle={() => setStreaming(s => !s)}
          status={filterDecision as "" | "blocked" | "warned" | "allowed"}
          onStatusChange={(v: string) => setFilterDecision(v)}
          filters={{
            developer: filterDeveloper,
            onDeveloperChange: setFilterDeveloper,
            developers,
            canViewAllActivity: !permissionsLoading && permissions.canViewAllActivity,
            tool: filterTool,
            onToolChange: setFilterTool,
            tools,
            since: filterSince,
            onSinceChange: setFilterSince,
            until: filterUntil,
            onUntilChange: setFilterUntil,
            ruleId: filterRuleId,
            onClearRule: () => setFilterRuleId(""),
            groupByGoal,
            onGroupByGoalChange: setGroupByGoal,
          }}
          onClearAll={() => {
            if (permissions.canViewAllActivity) setFilterDeveloper("")
            setFilterTool("")
            setFilterSince("")
            setFilterUntil("")
            setFilterRuleId("")
          }}
          canExport={permissions.canExportActivity}
          onExportCsv={() => exportCsv(events)}
          onSocReport={() => window.open("/theguard/reports/soc2", "_blank", "noopener")}
          allColumns={ALL_COLUMNS}
          columns={visibleColumns}
          onColumnsChange={applyVisibleColumns}
        />
      )}

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
            {["Actor", "Tool", "Started", "Events", "Violations", "Cost", "Saved", "Machine / IP", "OS"].map((h, i) => (
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
              {["Actor", "Archetype", "Sessions", "Commits", "Autonomy", "Lines/hr", "Date", "Report"].map(h => (
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
          // Header driven by <ColumnsMenu> selection — #1982.
          const tableHeader = <ActivityHeader visibleColumns={visibleColumns} />

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
                                onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
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
                                <ActivityRow key={ev.id} ev={ev} isLast={i === runGroup.events.length - 1} visibleColumns={visibleColumns} nowOffsetMs={serverTimeDrift} />
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
                          <ActivityRow key={ev.id} ev={ev} isLast={i === adhoc.length - 1} visibleColumns={visibleColumns} nowOffsetMs={serverTimeDrift} />
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
          {/* Header driven by <ColumnsMenu> selection — #1982. */}
          <ActivityHeader visibleColumns={visibleColumns} />

          {/* Table rows */}
          {events.map((ev, i) => (
            <ActivityRow key={ev.id} ev={ev} isLast={i === events.length - 1} visibleColumns={visibleColumns} nowOffsetMs={serverTimeDrift} />
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
