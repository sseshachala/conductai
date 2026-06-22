"use client"

import Link from "next/link"
import { useEffect, useState, useCallback, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { GuardShell } from "@/components/guard/GuardShell"
import { ActivityRow, ActivityHeader, ToolBadge, DecisionBadge, BlastRadiusBadge, formatTs, type AuditEvent } from "@/components/guard/ActivityRow"

// ─── Types ────────────────────────────────────────────────────────────────────

// AuditEvent shape lives in the shared component — keep one definition.

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

const PAGE_SIZE = 100

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
  const { user } = useUser()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [activeView, setActiveView] = useState<"events" | "sessions">("events")
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

  // Filters
  const [filterDecision, setFilterDecision] = useState("")
  const [filterDeveloper, setFilterDeveloper] = useState("")
  const [filterTool, setFilterTool] = useState("")
  const [filterSince, setFilterSince] = useState("")
  const [filterUntil, setFilterUntil] = useState("")
  const [filterRuleId, setFilterRuleId] = useState("")

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
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`

    try {
      const res = await fetch(`${base}/guard/events?${buildParams(0)}`, { headers })
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
  }, [getToken, teamId, effectiveDeveloperFilter, filterTool, filterDecision, filterSince, filterUntil, filterRuleId])

  const loadSessions = useCallback(async () => {
    if (!teamId) return
    setSessionsLoading(true)
    setSessionsError(null)
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    try {
      const p = new URLSearchParams({ limit: "100", offset: "0" })
      if (teamId) p.set("workspace_id", teamId)
      const res = await fetch(`${base}/guard/spend/sessions?${p}`, { headers })
      if (!res.ok) throw new Error("Failed to load sessions")
      setSessions(await res.json())
    } catch (err) {
      setSessionsError(err instanceof Error ? err.message : "Failed to load sessions")
    } finally {
      setSessionsLoading(false)
    }
  }, [getToken, teamId])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    if (activeView !== "sessions") return
    loadSessions()
    const t = setInterval(loadSessions, 60_000)
    return () => clearInterval(t)
  }, [activeView, loadSessions])

  async function loadMore() {
    setLoadingMore(true)
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    try {
      const res = await fetch(`${base}/guard/events?${buildParams(offsetRef.current)}`, { headers })
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

  return (
    <GuardShell live={live} lastFetched={lastUpdated}>
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

      {/* View toggle */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {(["events", "sessions"] as const).map(v => (
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
            {v === "events" ? "Audit Events" : "Sessions & Machines"}
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
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.user_email ?? "—"}
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
      ) : (
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
