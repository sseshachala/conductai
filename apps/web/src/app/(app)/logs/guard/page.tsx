"use client"

import Link from "next/link"

import { useEffect, useState, useCallback } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useUser } from "@/lib/auth/client"
import AppShell from "@/components/AppShell"
import ToolActivityTable from "@/components/guard/ToolActivityTable"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { GuardShell } from "@/components/guard/GuardShell"
import { ActivityRow, ActivityHeader, DecisionBadge, BlastRadiusBadge, type AuditEvent } from "@/components/guard/ActivityRow"
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
import { SessionsTable, type GuardSession } from "./_components/SessionsTable"
import { SessionReportsView, type SessionReport } from "./_components/SessionReportsView"
import { GroupedEvents } from "./_components/GroupedEvents"
import { exportCsv } from "./_components/exportCsv"
import { useGuardEventsFeed } from "./useGuardEventsFeed"

// ─── Types ────────────────────────────────────────────────────────────────────

// AuditEvent shape lives in the shared component — keep one definition.

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
  const { authFetch } = useAuthFetch()
  const { user } = useUser()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [activeView, _setActiveView] = useState<"events" | "sessions" | "tools" | "session_reports">("events")
  const [reports, setReports] = useState<SessionReport[]>([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState<string | null>(null)
  // #1990 item D — drift between server clock and browser clock. When a
  // SSE payload carries server_time, we recompute (client_now - server_now).
  // LifecyclePill uses this to correct client-side 'expired' detection so
  // a badly-skewed browser doesn't render rows as ∅ that aren't expired
  // server-side. 0 = no drift / not yet initialized.
  const [sessions, setSessions] = useState<GuardSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [sessionsError, setSessionsError] = useState<string | null>(null)
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
  const filterEventId = searchParams?.get("id") || ""
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

  const effectiveDeveloperFilter = !permissions.canViewAllActivity && currentUserEmail
    ? currentUserEmail
    : filterDeveloper

  const {
    events, loading, loadingMore, hasMore, error, live, lastUpdated, streaming, setStreaming,
    serverTimeDrift, loadMore,
  } = useGuardEventsFeed({
    teamId, teamLoading, activeView, effectiveDeveloperFilter,
    filterTool, filterDecision, filterSince, filterUntil, filterRuleId,
    filterHookSession, filterAgentIdentity, filterEventId,
  })

  // #1959 Phase 3 — count of currently-in-flight durable rows. Derived
  // client-side so the badge stays in sync with the same event stream
  // that drives the table, no extra endpoint needed.
  const inFlightCount = events.filter(ev => ev.lifecycle_state === "accepted").length
  const developers = Array.from(new Set(events.map(e => e.user_email).filter(Boolean) as string[])).sort()
  const tools = Array.from(new Set(events.map(e => e.ai_tool).filter(Boolean) as string[])).sort()

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
  }, [activeView, loadSessions])

  useEffect(() => {
    if (activeView !== "session_reports") return
    loadReports()
  }, [activeView, loadReports])

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
      {activeView === "events" && filterEventId && (
        <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "12px 0" }}>
          <span>Cited event</span>
          <Link href="/logs/guard">All activity</Link>
        </div>
      )}
      {activeView === "events" && !filterEventId && (
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
        <SessionsTable sessions={sessions} sessionsLoading={sessionsLoading} />
      )}

      {activeView === "tools" && (
        <ToolActivityTable workspaceId={teamId} />
      )}

      {activeView === "session_reports" && (
        <SessionReportsView reports={reports} reportsLoading={reportsLoading} reportsError={reportsError} />
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
        <GroupedEvents
          events={events}
          collapsedGroups={collapsedGroups}
          toggleGroup={toggleGroup}
          visibleColumns={visibleColumns}
          serverTimeDrift={serverTimeDrift}
          hasMore={hasMore}
          loadingMore={loadingMore}
          loadMore={loadMore}
        />
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
