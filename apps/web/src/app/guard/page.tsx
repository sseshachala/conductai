"use client"

import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useGuardSavings, type GuardSavingsSummary } from "@/hooks/useGuardSavings"
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
  tokens_before: number | null
  tokens_after: number | null
  tokens_saved: number | null
  cost_usd_after: number | null
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

const normTool = (t: string) => t.replace(/-/g, "_")

function AiToolBadge({ tool }: { tool: string }) {
  const cfg = AI_TOOL_BADGES[normTool(tool)]
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

type TrendPeriod = "daily" | "weekly" | "monthly"
interface TrendPoint { date: string; claude: number; codex: number; other: number }

function CostTrendChart({ apiBase, workspaceId, token }: { apiBase: string; workspaceId: string; token: string | null }) {
  const [period, setPeriod] = useState<TrendPeriod>("daily")
  const [data, setData] = useState<TrendPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    const tzOffset = new Date().getTimezoneOffset()
    fetch(`${apiBase}/guard/events/cost-trend?period=${period}&workspace_id=${workspaceId}&tz_offset=${tzOffset}`, { headers })
      .then(r => r.json())
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [period, apiBase, workspaceId, token])

  const hasData = data.some(d => d.claude > 0 || d.codex > 0 || d.other > 0)

  return (
    <div className="bg-white rounded-xl border border-stone-200 px-5 py-4">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-stone-700">Est. cost trend</span>
        <div className="flex gap-1">
          {(["daily", "weekly", "monthly"] as TrendPeriod[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
                period === p
                  ? "bg-stone-900 text-white"
                  : "text-stone-500 hover:text-stone-700"
              }`}
            >
              {p[0].toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="h-40 bg-stone-50 rounded-lg animate-pulse" />
      ) : !hasData ? (
        <div className="h-40 flex items-center justify-center text-sm text-stone-400">No cost data yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={false}
              tickFormatter={v => period === "monthly" ? v.slice(0, 7) : v.slice(5)} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false}
              tickFormatter={v => `$${v}`} />
            <Tooltip
              formatter={(val, name) => [`$${Number(val ?? 0).toFixed(4)}`, String(name)]}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e7e5e4" }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="claude" name="Claude" stackId="a" fill="#6366f1" radius={[0, 0, 0, 0]} />
            <Bar dataKey="codex"  name="Codex"  stackId="a" fill="#10b981" radius={[3, 3, 0, 0]} />
            {data.some(d => d.other > 0) && (
              <Bar dataKey="other" name="Other" stackId="a" fill="#a8a29e" radius={[3, 3, 0, 0]} />
            )}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

function StatCard({ label, value, accent, sub, onClick, active }: { label: string; value: number | string; accent?: string; sub?: React.ReactNode; onClick?: () => void; active?: boolean }) {
  return (
    <div
      className={`bg-white rounded-xl border px-5 py-4 flex flex-col gap-1 ${onClick ? "cursor-pointer hover:border-stone-400 transition-colors" : ""} ${active ? "border-stone-900 ring-1 ring-stone-900" : "border-stone-200"}`}
      onClick={onClick}
    >
      <div className={`text-2xl font-bold ${accent ?? "text-stone-900"}`}>{value}</div>
      <div className="text-xs font-medium text-stone-500 uppercase tracking-wide">{label}</div>
      {sub && <div className="text-xs text-stone-400 mt-0.5">{sub}</div>}
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

function formatTotalTokensSaved(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return `${n}`
}

function formatTokensUsed(input: number | null, output: number | null): string | null {
  if (input == null && output == null) return null
  const fmt = (n: number) => n >= 1_000 ? `${(n / 1_000).toFixed(0)}k` : `${n}`
  const parts = []
  if (input)  parts.push(`${fmt(input)} in`)
  if (output) parts.push(`${fmt(output)} out`)
  return parts.join(" / ") || null
}

function SavingsStatCard({
  savings,
  loading,
}: {
  savings: GuardSavingsSummary | null
  loading: boolean
}) {
  if (loading) {
    return <div className="bg-stone-100 rounded-xl h-24 animate-pulse" />
  }

  const hasSavings =
    savings !== null &&
    (savings.team_total.rtk_saved_tokens > 0 || savings.team_total.booster_saved_tokens > 0)

  if (hasSavings && savings !== null) {
    const totalTokens =
      savings.team_total.rtk_saved_tokens + savings.team_total.booster_saved_tokens
    const totalUsd =
      savings.team_total.rtk_saved_usd + savings.team_total.booster_saved_usd

    const TOOL_LINKS: Record<string, { label: string; href: string }> = {
      rtk:     { label: "RTK",          href: "https://pypi.org/project/rtk/" },
      booster: { label: "Agent Booster", href: "https://pypi.org/project/agent-booster/" },
    }

    const installed = savings.tools_installed?.length > 0
      ? savings.tools_installed
      : ["rtk", "booster"]

    const toolLinks = installed.map((t, i) => {
      const info = TOOL_LINKS[t] ?? { label: t.toUpperCase(), href: `https://pypi.org/project/${t}/` }
      return (
        <span key={t}>
          {i > 0 && " + "}
          <a href={info.href} target="_blank" rel="noopener noreferrer"
             className="underline underline-offset-2 hover:text-emerald-700">
            {info.label}
          </a>
        </span>
      )
    })

    return (
      <StatCard
        label="Est. savings"
        value={formatTotalTokensSaved(totalTokens) + " tokens"}
        accent="text-emerald-700"
        sub={<>${totalUsd.toFixed(2)} saved · {toolLinks}</>}
      />
    )
  }

  // Empty state — no savings data yet
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-5 py-4 flex flex-col gap-1">
      <div className="text-2xl font-bold text-stone-300">—</div>
      <div className="text-xs font-medium text-stone-500 uppercase tracking-wide">Est. savings</div>
      <div className="mt-1 text-[11px] text-stone-400 leading-relaxed space-y-0.5">
        <div className="font-medium text-stone-500">Save 60–99% on tokens with:</div>
        <div>· <a href="https://pypi.org/project/rtk/" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-stone-600">RTK</a> <span className="font-mono">pip install rtk</span></div>
        <div>· <a href="https://pypi.org/project/agent-booster/" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-stone-600">Agent Booster</a> <span className="font-mono">pip install agent-booster</span></div>
        <div className="mt-1 text-stone-400">Run <span className="font-mono">conduct guard sync</span> to start tracking.</div>
      </div>
    </div>
  )
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
  const { savings, loading: savingsLoading } = useGuardSavings(teamId)

  const [events, setEvents]           = useState<GuardEvent[]>([])
  const [stats, setStats]             = useState<SpendStats | null>(null)
  const [loading, setLoading]         = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore]         = useState(true)
  const [live, setLive]               = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [chartToken, setChartToken]   = useState<string | null>(null)

  const PAGE_SIZE = 100

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

  const loadEvents = useCallback(async (decision?: string) => {
    if (!teamId) return
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams({ limit: String(PAGE_SIZE), offset: "0" })
    params.set("workspace_id", teamId)
    if (decision && decision !== "all") params.set("decision", decision)
    try {
      const res = await fetch(`${base}/guard/events?${params}`, { headers })
      if (res.ok) {
        const data: GuardEvent[] = await res.json()
        setEvents(data)
        setHasMore(data.length === PAGE_SIZE)
        setLastUpdated(new Date())
      }
    } catch {
      // non-fatal — keep last known state
    } finally {
      setLoading(false)
    }
  }, [buildHeaders, teamId, PAGE_SIZE])

  const loadMore = useCallback(async () => {
    if (!teamId || loadingMore) return
    setLoadingMore(true)
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(events.length) })
    params.set("workspace_id", teamId)
    try {
      const res = await fetch(`${base}/guard/events?${params}`, { headers })
      if (res.ok) {
        const data: GuardEvent[] = await res.json()
        setEvents(prev => [...prev, ...data])
        setHasMore(data.length === PAGE_SIZE)
      }
    } catch {
      // non-fatal
    } finally {
      setLoadingMore(false)
    }
  }, [buildHeaders, teamId, events.length, loadingMore, PAGE_SIZE])

  const loadStats = useCallback(async () => {
    if (!teamId) return
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams()
    params.set("workspace_id", teamId)
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
    params.set("workspace_id", teamId)
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

  // Periodic merge of recent events — picks up PostToolUse token backfills
  const refreshRecent = useCallback(async () => {
    if (!teamId) return
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams({ limit: "20", offset: "0" })
    params.set("workspace_id", teamId)
    try {
      const res = await fetch(`${base}/guard/events?${params}`, { headers })
      if (!res.ok) return
      const fresh: GuardEvent[] = await res.json()
      setEvents(prev => {
        const byId = new Map(prev.map(e => [e.id, e]))
        fresh.forEach(e => byId.set(e.id, e))
        const freshIds = new Set(fresh.map(e => e.id))
        return [...fresh, ...prev.filter(e => !freshIds.has(e.id))]
      })
    } catch { /* non-fatal */ }
  }, [buildHeaders, teamId])

  useEffect(() => {
    connectSSE()
    loadEvents()
    loadStats()
    const statsInterval  = setInterval(() => { loadStats() }, 60_000)
    const refreshInterval = setInterval(() => { refreshRecent() }, 10_000)
    return () => {
      clearInterval(statsInterval)
      clearInterval(refreshInterval)
      esRef.current?.close()
    }
  }, [connectSSE, loadEvents, loadStats, refreshRecent])

  useEffect(() => {
    loadEvents(filterDecision !== "all" ? filterDecision : undefined)
  }, [filterDecision]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch chart token once when teamId resolves
  useEffect(() => {
    if (!teamId) return
    getToken().then(t => { if (t) setChartToken(t) })
  }, [teamId, getToken])

  // ── Derived data ─────────────────────────────────────────────────────────────

  const developerEmails = useMemo(
    () => Array.from(new Set(events.map(e => e.user_email).filter(Boolean) as string[])).sort(),
    [events]
  )

  const derivedStats = useMemo(() => {
    // Use local date so "today" matches the user's timezone, not UTC
    const localToday = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    const todayStr = localToday(new Date())
    const todayEvents = events.filter(e => localToday(new Date(e.ts)) === todayStr)
    const distinctDevs = new Set(events.map(e => e.user_email).filter(Boolean)).size
    return {
      active_developers: distinctDevs > 0 ? distinctDevs : events.length > 0 ? 1 : 0,
      events_today: todayEvents.length,
      blocked_today: todayEvents.filter(e => e.decision === "blocked").length,
      tokens_saved_today: todayEvents.reduce((s, e) => s + Math.max(0, (e.tokens_before ?? 0) - (e.tokens_after ?? 0)), 0),
      est_cost_today: todayEvents.reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
      claude_cost_today: todayEvents.filter(e => normTool(e.ai_tool).includes("claude")).reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
      codex_cost_today: todayEvents.filter(e => normTool(e.ai_tool).includes("codex")).reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
    }
  }, [events])

  const currentUserEmail = user?.primaryEmailAddress?.emailAddress ?? null

  const filteredEvents = useMemo(() => {
    return events.filter(ev => {
      // Viewers can only see their own events
      if (!permissions.canViewAllActivity && ev.user_email !== currentUserEmail) return false
      if (filterTool !== "all"     && normTool(ev.ai_tool) !== filterTool) return false
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
        {!loading && !permissionsLoading && !permissions.canViewAllActivity && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
            You can view your own activity only. Contact your admin to request broader access.
          </div>
        )}

        {/* Stats cards */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 animate-pulse">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-stone-100 rounded-xl h-24" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard
              label="Active developers"
              value={stats?.active_developers || derivedStats.active_developers}
              accent="text-indigo-700"
            />
            <StatCard
              label="Events today"
              value={stats?.events_today || derivedStats.events_today}
            />
            <StatCard
              label="Blocked today"
              value={stats?.blocked_today || derivedStats.blocked_today}
              accent={(stats?.blocked_today || derivedStats.blocked_today) > 0 ? "text-red-600" : undefined}
              onClick={() => setFilterDecision(prev => prev === "blocked" ? "all" : "blocked")}
              active={filterDecision === "blocked"}
            />
            <StatCard
              label="Tokens used today (est.)"
              value={formatTotalTokensSaved(stats?.tokens_saved_today || derivedStats.tokens_saved_today)}
              accent="text-green-700"
            />
            <StatCard
              label="Est. cost today"
              value={`$${derivedStats.est_cost_today.toFixed(2)}`}
              accent="text-stone-700"
              sub={<>Claude ${derivedStats.claude_cost_today.toFixed(2)} · Codex ${derivedStats.codex_cost_today.toFixed(2)}</>}
            />
            <SavingsStatCard savings={savings} loading={savingsLoading} />
          </div>
        )}

        {/* Cost trend chart */}
        {!loading && teamId && (
          <CostTrendChart
            apiBase={process.env.NEXT_PUBLIC_API_URL ?? ""}
            workspaceId={teamId}
            token={chartToken}
          />
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
            <>
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide">
                    <th className="px-4 py-3 text-left font-medium w-20">Time</th>
                    <th className="px-4 py-3 text-left font-medium">User</th>
                    <th className="px-4 py-3 text-left font-medium">AI tool</th>
                    <th className="px-4 py-3 text-left font-medium">Call</th>
                    <th className="px-4 py-3 text-left font-medium">Input</th>
                    <th className="px-4 py-3 text-left font-medium">Decision</th>
                    <th className="px-4 py-3 text-right font-medium">Tokens</th>
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
                      <td className="px-4 py-3 max-w-[160px]">
                        {ev.user_email ? (
                          <>
                            <div className="text-xs font-medium text-stone-700 truncate">
                              {ev.user_email.split("@")[0]}
                            </div>
                            <div className="text-[11px] text-stone-400 truncate" title={ev.user_email}>
                              {ev.user_email}
                            </div>
                          </>
                        ) : (
                          <span className="text-xs text-stone-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <AiToolBadge tool={ev.ai_tool} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-stone-600 whitespace-nowrap">
                        {ev.tool_call}
                      </td>
                      <td
                        className="px-4 py-3 text-xs text-stone-500 max-w-[200px] truncate cursor-copy select-none"
                        title={ev.input_summary ? "Double-click to copy" : undefined}
                        onDoubleClick={() => {
                          if (!ev.input_summary) return
                          navigator.clipboard.writeText(ev.input_summary)
                            .then(() => {
                              const el = document.activeElement as HTMLElement
                              el?.blur()
                            })
                            .catch(() => {})
                        }}
                      >
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
                      <td className="px-4 py-3 text-right text-xs tabular-nums whitespace-nowrap">
                        {(() => {
                          const used = formatTokensUsed(ev.tokens_before, ev.tokens_after)
                          if (used) return <span className="text-stone-500">{used}</span>
                          if (ev.tokens_saved && ev.tokens_saved > 0)
                            return <span className="text-green-700">{formatTokensSaved(ev.tokens_saved)} saved</span>
                          return <span className="text-stone-300">—</span>
                        })()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasMore && (
              <div className="flex justify-center pt-4 pb-2">
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="text-sm text-indigo-600 hover:text-indigo-800 disabled:text-stone-400 font-medium"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
            </>
          )}
        </div>

      </div>
  )
}
