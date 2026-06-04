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
  decision: "allowed" | "blocked" | "approval"
  rule_id: string | null
  conductai_run_id: string | null
}

// ─── Guard Shell ──────────────────────────────────────────────────────────────

const GUARD_TABS = [
  { href: "/guard",          label: "Overview"  },
  { href: "/guard/spend",    label: "Spend"     },
  { href: "/guard/policies", label: "Policies"  },
  { href: "/guard/activity", label: "Activity"  },
  { href: "/guard/settings", label: "Settings"  },
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
  "claude-code":  "var(--accent)",
  "claude_code":  "var(--accent)",
  "codex":        "var(--ok)",
  "cursor":       "#7c3aed",
  "windsurf":     "#0284c7",
  "gemini":       "#ea580c",
}

function ToolBadge({ tool }: { tool: string }) {
  const color = TOOL_COLORS[tool] ?? TOOL_COLORS[tool.replace(/-/g, "_")] ?? "var(--text-3)"
  const LABELS: Record<string, string> = {
    claude_code: "Claude Code", claude: "Claude", codex: "Codex",
    cursor: "Cursor", windsurf: "Windsurf", gemini: "Gemini",
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
  const [events, setEvents] = useState<AuditEvent[]>([])
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
  const tools = Array.from(new Set(events.map(e => e.ai_tool))).sort()

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

  useEffect(() => { load() }, [load])

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
    <GuardShell>
      {/* Viewer-scoped notice */}
      {!permissions.canViewAllActivity && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800 mb-4">
          You can view your own activity only. Contact your admin to request broader access.
        </div>
      )}

      {/* Filter chips + realtime indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16, flexWrap: "wrap" }}>
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
            className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none"
          >
            <option value="">All developers</option>
            {developers.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}

        <select
          value={filterTool}
          onChange={e => setFilterTool(e.target.value)}
          className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none"
        >
          <option value="">All tools</option>
          {tools.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        <input
          type="date"
          value={filterSince}
          onChange={e => setFilterSince(e.target.value)}
          className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none"
          aria-label="From date"
        />
        <input
          type="date"
          value={filterUntil}
          onChange={e => setFilterUntil(e.target.value)}
          className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none"
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
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 mb-4">{error}</div>
      )}

      {/* Events table */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} className="animate-pulse" style={{ height: 44, background: "var(--surface-2)", borderRadius: 8 }} />
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
              gridTemplateColumns: "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr",
              gap: 12,
              padding: "10px 18px",
              borderBottom: "1px solid var(--border)",
              background: "var(--surface-2)",
            }}
          >
            {["Time", "Developer", "Tool", "Call", "Input", "Decision", "Rule"].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
            ))}
          </div>

          {/* Table rows */}
          {events.map((ev, i) => (
            <div
              key={ev.id}
              style={{
                display: "grid",
                gridTemplateColumns: "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr",
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
                  <Link href={`/runs/${ev.conductai_run_id}`} className="hover:opacity-80 transition-opacity">
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
      )}
    </GuardShell>
  )
}
