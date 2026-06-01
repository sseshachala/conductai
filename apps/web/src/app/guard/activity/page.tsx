"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import { getGuardTeamId } from "@/lib/guardStorage"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface AuditEvent {
  id: string
  timestamp: string
  developer: string
  ai_tool: string
  tool_call: string
  input_summary: string
  decision: "allowed" | "blocked" | "approval"
  rule_id: string | null
  conductai_run_id: string | null
}

const DECISION_STYLES: Record<string, string> = {
  allowed:  "text-green-700 bg-green-50 border-green-200",
  blocked:  "text-red-700 bg-red-50 border-red-200",
  approval: "text-amber-700 bg-amber-50 border-amber-200",
}

function DecisionBadge({ decision }: { decision: string }) {
  const cls = DECISION_STYLES[decision] ?? "text-stone-600 bg-stone-100 border-stone-200"
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border ${cls}`}>
      {decision}
    </span>
  )
}

function formatTs(ts: string): string {
  // Full timestamp for compliance — no relative time
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
  const rows = events.map((e) => {
    const cols = [
      e.timestamp,
      e.developer,
      e.ai_tool,
      e.tool_call,
      `"${e.input_summary.replace(/"/g, '""')}"`,
      e.decision,
      e.rule_id ?? "",
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

export default function ActivityPage() {
  const { getToken } = useAuth()
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const offsetRef = useRef(0)

  // Filters
  const [filterDeveloper, setFilterDeveloper] = useState("")
  const [filterTool, setFilterTool] = useState("")
  const [filterDecision, setFilterDecision] = useState("")
  const [filterSince, setFilterSince] = useState("")
  const [filterUntil, setFilterUntil] = useState("")

  // Unique values from loaded events for filter dropdowns
  const developers = Array.from(new Set(events.map((e) => e.developer))).sort()
  const tools = Array.from(new Set(events.map((e) => e.ai_tool))).sort()

  function buildParams(offset: number) {
    const teamId = getGuardTeamId()
    const p = new URLSearchParams({ team_id: teamId, limit: String(PAGE_SIZE), offset: String(offset) })
    if (filterDeveloper) p.set("user_email", filterDeveloper)
    if (filterTool) p.set("ai_tool", filterTool)
    if (filterDecision) p.set("decision", filterDecision)
    if (filterSince) p.set("since", filterSince)
    if (filterUntil) p.set("until", filterUntil)
    return p.toString()
  }

  const load = useCallback(async () => {
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
  }, [getToken, filterDeveloper, filterTool, filterDecision, filterSince, filterUntil])

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
      setEvents((prev) => [...prev, ...rows])
      setHasMore(rows.length === PAGE_SIZE)
      offsetRef.current += rows.length
    } catch {
      // non-fatal — user can retry
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-stone-900 mb-1">Activity log</h1>
            <p className="text-sm text-stone-500">Complete log of all AI tool actions across your team.</p>
          </div>
          <button
            onClick={() => exportCsv(events)}
            disabled={events.length === 0}
            className="shrink-0 text-xs text-stone-600 hover:text-stone-800 border border-stone-200 rounded-lg px-3 py-1.5 hover:bg-stone-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Export CSV
          </button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Developer */}
          <select
            value={filterDeveloper}
            onChange={(e) => setFilterDeveloper(e.target.value)}
            className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All developers</option>
            {developers.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>

          {/* Tool */}
          <select
            value={filterTool}
            onChange={(e) => setFilterTool(e.target.value)}
            className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All tools</option>
            {tools.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          {/* Decision */}
          <select
            value={filterDecision}
            onChange={(e) => setFilterDecision(e.target.value)}
            className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All decisions</option>
            <option value="allowed">Allowed</option>
            <option value="blocked">Blocked</option>
            <option value="approval">Approval</option>
          </select>

          {/* Since */}
          <input
            type="date"
            value={filterSince}
            onChange={(e) => setFilterSince(e.target.value)}
            className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="From date"
            aria-label="From date"
          />

          {/* Until */}
          <input
            type="date"
            value={filterUntil}
            onChange={(e) => setFilterUntil(e.target.value)}
            className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="To date"
            aria-label="To date"
          />

          {/* Clear filters */}
          {(filterDeveloper || filterTool || filterDecision || filterSince || filterUntil) && (
            <button
              onClick={() => {
                setFilterDeveloper("")
                setFilterTool("")
                setFilterDecision("")
                setFilterSince("")
                setFilterUntil("")
              }}
              className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {/* Events table */}
        {loading ? (
          <div className="space-y-2 animate-pulse">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-stone-100 rounded-xl h-12" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="rounded-xl border border-stone-200 bg-white px-6 py-16 text-center text-sm text-stone-400">
            No activity events found for the selected filters.
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide bg-stone-50">
                    <th className="px-4 py-3 text-left font-medium whitespace-nowrap">Timestamp</th>
                    <th className="px-4 py-3 text-left font-medium">Developer</th>
                    <th className="px-4 py-3 text-left font-medium">Tool</th>
                    <th className="px-4 py-3 text-left font-medium">Action</th>
                    <th className="px-4 py-3 text-left font-medium">Input</th>
                    <th className="px-4 py-3 text-left font-medium">Decision</th>
                    <th className="px-4 py-3 text-left font-medium">Rule</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr
                      key={ev.id}
                      className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors"
                    >
                      <td className="px-4 py-3 text-xs text-stone-500 font-mono whitespace-nowrap">
                        {formatTs(ev.timestamp)}
                      </td>
                      <td className="px-4 py-3 text-xs text-stone-700 max-w-[180px] truncate">
                        {ev.developer}
                      </td>
                      <td className="px-4 py-3 text-xs text-stone-600 whitespace-nowrap">
                        {ev.ai_tool}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-stone-600 whitespace-nowrap">
                        {ev.tool_call}
                      </td>
                      <td className="px-4 py-3 text-xs text-stone-500 max-w-[220px] truncate font-mono">
                        {ev.input_summary}
                      </td>
                      <td className="px-4 py-3">
                        {ev.conductai_run_id ? (
                          <Link href={`/runs/${ev.conductai_run_id}`} className="hover:opacity-80 transition-opacity">
                            <DecisionBadge decision={ev.decision} />
                          </Link>
                        ) : (
                          <DecisionBadge decision={ev.decision} />
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-stone-400 font-mono">
                        {ev.rule_id ? (
                          <span className="text-stone-600">{ev.rule_id}</span>
                        ) : (
                          <span className="text-stone-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Load more */}
            {hasMore && (
              <div className="border-t border-stone-100 px-4 py-3 flex items-center justify-between">
                <span className="text-xs text-stone-400">Showing {events.length} events</span>
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50 font-medium transition-colors"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}

            {!hasMore && events.length > 0 && (
              <div className="border-t border-stone-100 px-4 py-2 text-xs text-stone-400 text-center">
                {events.length} event{events.length !== 1 ? "s" : ""} total
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  )
}
