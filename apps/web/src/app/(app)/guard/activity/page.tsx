"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useAuth, useUser } from "@clerk/nextjs"
import Link from "next/link"
import { usePathname } from "next/navigation"
import AppShell from "@/components/AppShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface AuditEvent {
  id: string
  ts: string
  user_email: string | null
  ai_tool: string
  tool_call: string
  input_summary: string | null
  decision: "allowed" | "blocked" | "warned" | "approval"
  rule_id: string | null
  conductai_run_id: string | null
  blast_radius: { files: number; symbols: number; tier: string } | null
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
}

// ─── Guard Shell ──────────────────────────────────────────────────────────────

const GUARD_TABS = [
  { href: "/guard",             label: "Overview"    },
  { href: "/guard/spend",       label: "Spend"       },
  { href: "/guard/policies",    label: "Policies"    },
  { href: "/guard/activity",    label: "Activity"    },
  { href: "/guard/session-reports", label: "Session Reports" },
  { href: "/guard/team-memory",     label: "Team Memory"     },
  { href: "/guard/settings",        label: "Settings"        },
]

function GuardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
              Guard
            </h1>
            <span className="sbadge ok" style={{ marginTop: 2 }}>
              <span className="conduct-pulse-dot" />
              live
            </span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
            MDM for AI coding tools — policies and spend limits enforced on every Claude Code, Codex, and Cursor call.
          </p>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
          last updated: just now
        </div>
      </div>
      <div className="guard-tab-nav">
        {GUARD_TABS.map(tab => {
          const isActive = tab.href === "/guard"
            ? pathname === "/guard"
            : pathname?.startsWith(tab.href)
          return (
            <Link key={tab.href} href={tab.href} className={`guard-tab${isActive ? " active" : ""}`}>
              {tab.label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}

// ─── Tool badge ───────────────────────────────────────────────────────────────

const TOOL_COLORS: Record<string, string> = {
  "claude-code":     "var(--chart-claude)",
  "claude_code":     "var(--chart-claude)",
  "claude_chat":     "var(--chart-claude)",
  "claude-chat":     "var(--chart-claude)",
  "claude_desktop":  "var(--chart-claude)",
  "claude-desktop":  "var(--chart-claude)",
  "claude_work":     "var(--chart-claude)",
  "claude-work":     "var(--chart-claude)",
  "codex":           "var(--chart-codex)",
  "codex_cli":       "var(--chart-codex)",
  "codex_chat":      "var(--chart-codex)",
  "cursor":          "#7c3aed",
  "windsurf":        "#0284c7",
  "copilot":         "#24292f",
  "gemini":          "#ea580c",
}

function ToolBadge({ tool }: { tool: string }) {
  const color = TOOL_COLORS[tool] ?? TOOL_COLORS[tool.replace(/-/g, "_")] ?? "var(--text-3)"
  const LABELS: Record<string, string> = {
    claude_code: "Claude Code", claude: "Claude",
    claude_chat: "Claude.ai", claude_desktop: "Claude Desktop", claude_work: "Claude Work",
    codex: "Codex", codex_cli: "Codex CLI", codex_chat: "Codex Chat",
    cursor: "Cursor", windsurf: "Windsurf", copilot: "Copilot", gemini: "Gemini",
  }
  const label = LABELS[tool.replace(/-/g, "_")] ?? tool
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        color,
        background: "var(--surface-3)",
        borderRadius: 5,
        padding: "2px 7px",
      }}
    >
      {label}
    </span>
  )
}

// ─── Decision badge ───────────────────────────────────────────────────────────

function DecisionBadge({ decision }: { decision: string }) {
  if (decision === "allowed") {
    return (
      <span className="sbadge ok" style={{ textTransform: "capitalize" }}>
        {decision}
      </span>
    )
  }
  if (decision === "blocked") {
    return (
      <span className="sbadge err" style={{ textTransform: "capitalize" }}>
        {decision}
      </span>
    )
  }
  return (
    <span className="sbadge warn" style={{ textTransform: "capitalize" }}>
      {decision}
    </span>
  )
}

// ─── Blast Radius badge ───────────────────────────────────────────────────────

function BlastRadiusBadge({ br }: { br: { tier: string; files: number } }) {
  const colors: Record<string, { bg: string; text: string }> = {
    LOW:      { bg: "var(--ok-bg)",   text: "var(--ok)"   },
    MEDIUM:   { bg: "var(--warn-bg)", text: "var(--warn)"  },
    HIGH:     { bg: "#fff3e0",        text: "#e65100"      },
    CRITICAL: { bg: "var(--err-bg)",  text: "var(--err)"   },
  }
  const c = colors[br.tier] ?? colors.LOW
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "1px 7px", borderRadius: 20,
      background: c.bg, color: c.text, whiteSpace: "nowrap",
    }}>
      {br.tier} · {br.files}f
    </span>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTs(ts: string): string {
  try {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return ts
  }
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
  a.click()
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
  const { permissions } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [activeView, setActiveView] = useState<"events" | "sessions">("events")
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [sessions, setSessions] = useState<GuardSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const offsetRef = useRef(0)

  // Filters
  const [filterDecision, setFilterDecision] = useState("")
  const [filterDeveloper, setFilterDeveloper] = useState("")
  const [filterTool, setFilterTool] = useState("")
  const [filterSince, setFilterSince] = useState("")
  const [filterUntil, setFilterUntil] = useState("")

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getToken, teamId, effectiveDeveloperFilter, filterTool, filterDecision, filterSince, filterUntil])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

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

  async function loadSessions() {
    if (!teamId) return
    setSessionsLoading(true)
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    try {
      const p = new URLSearchParams({ limit: "100", offset: "0" })
      if (teamId) p.set("workspace_id", teamId)
      const res = await fetch(`${base}/guard/spend/sessions?${p}`, { headers })
      if (res.ok) setSessions(await res.json())
    } catch { /* non-fatal */ } finally {
      setSessionsLoading(false)
    }
  }

  return (
    <GuardShell>
      {/* Viewer-scoped notice */}
      {!permissions.canViewAllActivity && (
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
            onClick={() => { setActiveView(v); if (v === "sessions") loadSessions() }}
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
        {permissions.canViewAllActivity && (
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

        {(filterDeveloper || filterTool || filterSince || filterUntil) && (
          <button
            onClick={() => {
              if (permissions.canViewAllActivity) setFilterDeveloper("")
              setFilterTool(""); setFilterSince(""); setFilterUntil("")
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
              <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
            ))}
          </div>

          {/* Table rows */}
          {events.map((ev, i) => (
            <div
              key={ev.id}
              style={{
                display: "grid",
                gridTemplateColumns: "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr 0.9fr",
                gap: 12,
                padding: "11px 18px",
                borderBottom: i < events.length - 1 ? "1px solid var(--border)" : "none",
                alignItems: "center",
                background: ev.decision === "blocked" ? "var(--err-bg)" : "transparent",
              }}
            >
              {/* Time */}
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                {formatTs(ev.ts)}
              </div>

              {/* Developer */}
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {ev.user_email ?? "—"}
              </div>

              {/* Tool */}
              <div>
                <ToolBadge tool={ev.ai_tool} />
              </div>

              {/* Call */}
              <div className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{ev.tool_call}</div>

              {/* Input */}
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {ev.input_summary ? `{${ev.input_summary}…}` : "—"}
              </div>

              {/* Decision */}
              <div>
                {ev.conductai_run_id ? (
                  <Link href={`/runs/${ev.conductai_run_id}`} style={{ opacity: 1, transition: "opacity 0.15s" }}>
                    <DecisionBadge decision={ev.decision} />
                  </Link>
                ) : (
                  <DecisionBadge decision={ev.decision} />
                )}
              </div>

              {/* Rule */}
              <div className="mono" style={{ fontSize: 11.5, color: ev.rule_id ? "var(--err)" : "var(--text-muted)" }}>
                {ev.rule_id ?? "—"}
              </div>

              {/* Blast Radius */}
              <div>
                {ev.blast_radius ? (
                  <BlastRadiusBadge br={ev.blast_radius} />
                ) : (
                  <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>—</span>
                )}
              </div>
            </div>
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
