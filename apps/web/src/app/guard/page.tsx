"use client"

import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface GuardEvent {
  id: string
  user_email: string | null
  ai_tool: string
  tool_call: string
  input_summary: string | null
  decision: "allowed" | "blocked" | "warned" | "approval"
  tokens_saved: number | null
  rule_message: string | null
  ts: string
}

interface SpendStats {
  active_developers: number
  events_today: number
  blocked_today: number
  tokens_saved_today: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const AI_TOOL_BADGES: Record<string, { label: string; bg: string; text: string }> = {
  claude_code: { label: "Claude Code", bg: "bg-indigo-100", text: "text-indigo-700" },
  codex:       { label: "Codex",       bg: "bg-green-100",  text: "text-green-700"  },
  cursor:      { label: "Cursor",      bg: "bg-purple-100", text: "text-purple-700" },
  windsurf:    { label: "Windsurf",    bg: "bg-sky-100",    text: "text-sky-700"    },
  gemini:      { label: "Gemini",      bg: "bg-orange-100", text: "text-orange-700" },
}

const DECISION_CONFIG: Record<
  string,
  { label: string; dot?: string; bg?: string; text?: string; icon?: string }
> = {
  allowed:  { label: "allowed",         dot: "bg-green-400"                                        },
  blocked:  { label: "blocked",         bg: "bg-red-100",   text: "text-red-700"                   },
  warned:   { label: "warned",          bg: "bg-amber-100", text: "text-amber-700"                 },
  approval: { label: "approval pending", bg: "bg-blue-100",  text: "text-blue-700"                 },
}

const ALL_TOOLS    = ["claude_code", "codex", "cursor", "windsurf", "gemini"]
const ALL_DECISIONS = ["allowed", "blocked", "warned", "approval"]

// ─── Helper components ────────────────────────────────────────────────────────

function AiToolBadge({ tool }: { tool: string }) {
  const cfg = AI_TOOL_BADGES[tool]
  if (!cfg) {
    return (
      <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-stone-100 text-stone-600">
        {tool}
      </span>
    )
  }
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  )
}

function DecisionBadge({ decision }: { decision: string }) {
  const cfg = DECISION_CONFIG[decision]
  if (!cfg) return <span className="text-xs text-stone-400">{decision}</span>

  if (decision === "allowed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-700">
        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      </span>
    )
  }
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  )
}

function StatCard({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-5 py-4 flex flex-col gap-1">
      <div className={`text-2xl font-bold ${accent ?? "text-stone-900"}`}>{value}</div>
      <div className="text-xs font-medium text-stone-500 uppercase tracking-wide">{label}</div>
    </div>
  )
}

function formatTokensSaved(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n === 0)   return "—"
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return `${n}`
}

function formatTokensSavedPct(saved: number | null): string {
  if (saved == null) return "—"
  return `−${saved}% tokens`
}

function formatTotalTokensSaved(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return `${n}`
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function GuardPage() {
  return <AppShell><GuardDashboard /></AppShell>
}

function GuardDashboard() {
  const { getToken } = useAuth()
  const { user } = useUser()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)

  const [events, setEvents]       = useState<GuardEvent[]>([])
  const [stats, setStats]         = useState<SpendStats | null>(null)
  const [loading, setLoading]     = useState(true)
  const [live, setLive]           = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  // Filters
  const [filterTool, setFilterTool]       = useState("all")
  const [filterDecision, setFilterDecision] = useState("all")
  const [filterDev, setFilterDev]         = useState("all")

  const esRef = useRef<EventSource | null>(null)

  // ── API helpers ─────────────────────────────────────────────────────────────

  const buildHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }, [getToken])

  // Clear skeleton when team resolution finishes with no result
  useEffect(() => {
    if (!teamLoading && !teamId) setLoading(false)
  }, [teamLoading, teamId])

  const loadEvents = useCallback(async () => {
    if (!teamId) return
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams({ limit: "100" })
    params.set("team_id", teamId)
    try {
      const res = await fetch(`${base}/guard/events?${params}`, { headers })
      if (res.ok) {
        const data: GuardEvent[] = await res.json()
        setEvents(data)
        setLastUpdated(new Date())
      }
    } catch {
      // non-fatal — keep last known state
    } finally {
      setLoading(false)
    }
  }, [buildHeaders, teamId])

  const loadStats = useCallback(async () => {
    if (!teamId) return
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams()
    params.set("team_id", teamId)
    try {
      const res = await fetch(`${base}/guard/spend?${params}`, { headers })
      if (res.ok) setStats(await res.json())
    } catch {
      // non-fatal
    }
  }, [buildHeaders, teamId])

  const connectSSE = useCallback(async () => {
    if (!teamId) return
    const token  = await getToken()
    const base   = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params = new URLSearchParams()
    if (token) params.set("token", token)
    params.set("team_id", teamId)
    const url = `${base}/guard/events/stream?${params}`

    if (esRef.current) esRef.current.close()
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setLive(true)
    es.onerror = () => setLive(false)
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.kind === "stream_timeout") return
        if (data.id && data.decision) {
          setEvents(prev => {
            // Prepend; deduplicate by id; cap at 200
            const merged = [data as GuardEvent, ...prev.filter(e => e.id !== data.id)]
            return merged.slice(0, 200)
          })
          setLastUpdated(new Date())
        }
      } catch {
        // malformed frame — ignore
      }
    }
  }, [getToken, teamId])

  useEffect(() => {
    connectSSE()
    loadEvents()
    loadStats()
    const interval = setInterval(() => { loadStats() }, 60_000)
    return () => {
      clearInterval(interval)
      esRef.current?.close()
    }
  }, [connectSSE, loadEvents, loadStats])

  // ── Derived data ─────────────────────────────────────────────────────────────

  const developerEmails = useMemo(
    () => Array.from(new Set(events.map(e => e.user_email).filter(Boolean) as string[])).sort(),
    [events]
  )

  const currentUserEmail = user?.primaryEmailAddress?.emailAddress ?? null

  const filteredEvents = useMemo(() => {
    return events.filter(ev => {
      // Viewers can only see their own events
      if (!permissions.canViewAllActivity && ev.user_email !== currentUserEmail) return false
      if (filterTool !== "all"     && ev.ai_tool    !== filterTool)     return false
      if (filterDecision !== "all" && ev.decision   !== filterDecision) return false
      if (filterDev !== "all"      && ev.user_email !== filterDev)      return false
      return true
    })
  }, [events, filterTool, filterDecision, filterDev, permissions.canViewAllActivity, currentUserEmail])

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Guard</h1>
            <p className="text-sm text-stone-500 mt-1">
              AI tool activity across your team.
              {live
                ? <span className="ml-2 text-green-600 text-xs">● live</span>
                : <span className="ml-2 text-stone-400 text-xs">connecting...</span>
              }
            </p>
          </div>
          <div className="text-xs text-stone-400">
            {lastUpdated
              ? <>last updated: {timeAgo(lastUpdated.toISOString())}</>
              : "—"
            }
          </div>
        </div>

        {/* Viewer-scoped notice */}
        {!permissionsLoading && !permissions.canViewAllActivity && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
            You can view your own activity only. Contact your admin to request broader access.
          </div>
        )}

        {/* Stats cards */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-stone-100 rounded-xl h-24" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Active developers"
              value={(() => {
                const fromStats = stats?.active_developers ?? 0
                if (fromStats > 0) return fromStats
                const fromEmails = new Set(events.map(e => e.user_email).filter(Boolean)).size
                if (fromEmails > 0) return fromEmails
                return events.length > 0 ? 1 : 0
              })()}
              accent="text-indigo-700"
            />
            <StatCard
              label="Events today"
              value={stats?.events_today ?? events.length}
            />
            <StatCard
              label="Blocked today"
              value={stats?.blocked_today ?? events.filter(e => e.decision === "blocked").length}
              accent={
                (stats?.blocked_today ?? events.filter(e => e.decision === "blocked").length) > 0
                  ? "text-red-600"
                  : undefined
              }
            />
            <StatCard
              label="Tokens saved today"
              value={
                stats?.tokens_saved_today != null
                  ? formatTotalTokensSaved(stats.tokens_saved_today)
                  : formatTotalTokensSaved(
                      events.reduce((sum, e) => sum + (e.tokens_saved ?? 0), 0)
                    )
              }
              accent="text-green-700"
            />
          </div>
        )}

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={filterTool}
            onChange={e => setFilterTool(e.target.value)}
            className="text-sm border border-stone-200 rounded-lg px-3 py-1.5 bg-white text-stone-700 outline-none focus:ring-2 focus:ring-indigo-200"
          >
            <option value="all">All tools</option>
            {ALL_TOOLS.map(t => (
              <option key={t} value={t}>{AI_TOOL_BADGES[t]?.label ?? t}</option>
            ))}
          </select>

          <select
            value={filterDecision}
            onChange={e => setFilterDecision(e.target.value)}
            className="text-sm border border-stone-200 rounded-lg px-3 py-1.5 bg-white text-stone-700 outline-none focus:ring-2 focus:ring-indigo-200"
          >
            <option value="all">All decisions</option>
            {ALL_DECISIONS.map(d => (
              <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
            ))}
          </select>

          <select
            value={filterDev}
            onChange={e => setFilterDev(e.target.value)}
            className="text-sm border border-stone-200 rounded-lg px-3 py-1.5 bg-white text-stone-700 outline-none focus:ring-2 focus:ring-indigo-200"
          >
            <option value="all">All developers</option>
            {developerEmails.map(email => (
              <option key={email} value={email}>{email}</option>
            ))}
          </select>

          {(filterTool !== "all" || filterDecision !== "all" || filterDev !== "all") && (
            <button
              onClick={() => { setFilterTool("all"); setFilterDecision("all"); setFilterDev("all") }}
              className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 rounded-lg px-3 py-1.5 hover:bg-stone-50 transition-colors"
            >
              Clear filters
            </button>
          )}

          <span className="ml-auto text-xs text-stone-400">
            {filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Activity feed */}
        <div>
          {loading ? (
            <div className="space-y-2 animate-pulse">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="bg-stone-100 rounded-xl h-12" />
              ))}
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="rounded-xl border border-stone-200 bg-white px-6 py-10 text-center text-sm text-stone-400">
              No events match the current filters.
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide">
                    <th className="px-4 py-3 text-left font-medium w-20">Time</th>
                    <th className="px-4 py-3 text-left font-medium">Developer</th>
                    <th className="px-4 py-3 text-left font-medium">AI tool</th>
                    <th className="px-4 py-3 text-left font-medium">Call</th>
                    <th className="px-4 py-3 text-left font-medium">Input</th>
                    <th className="px-4 py-3 text-left font-medium">Decision</th>
                    <th className="px-4 py-3 text-right font-medium">Tokens saved</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.map(ev => (
                    <tr
                      key={ev.id}
                      className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors"
                    >
                      <td className="px-4 py-3 text-stone-400 text-xs tabular-nums whitespace-nowrap">
                        {timeAgo(ev.ts)}
                      </td>
                      <td className="px-4 py-3 text-stone-700 text-xs truncate max-w-[140px]" title={ev.user_email ?? undefined}>
                        {ev.user_email ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <AiToolBadge tool={ev.ai_tool} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-stone-600 whitespace-nowrap">
                        {ev.tool_call}
                      </td>
                      <td className="px-4 py-3 text-xs text-stone-500 max-w-[200px] truncate" title={ev.input_summary ?? undefined}>
                        {ev.input_summary ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <DecisionBadge decision={ev.decision} />
                        {ev.rule_message && ev.decision !== "allowed" && (
                          <div className="text-[11px] text-stone-400 mt-0.5 truncate max-w-[120px]" title={ev.rule_message}>
                            {ev.rule_message}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-stone-500 tabular-nums whitespace-nowrap">
                        {ev.tokens_saved != null && ev.tokens_saved !== 0
                          ? <span className="text-green-700">{formatTokensSavedPct(ev.tokens_saved)}</span>
                          : <span className="text-stone-300">—</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>
  )
}
