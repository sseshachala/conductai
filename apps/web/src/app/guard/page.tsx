"use client"

import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from "recharts"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useGuardSavings, type GuardSavingsSummary } from "@/hooks/useGuardSavings"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface GuardEvent {
  id: string
  user_email: string | null
  ai_tool: string
  tool_call: string
  input_summary: string | null
  decision: "allowed" | "blocked" | "warned" | "approval"
  rule_id: string | null
  rule_message: string | null
  tokens_before: number | null
  tokens_after: number | null
  tokens_saved: number | null
  tokens_input: number | null
  tokens_output: number | null
  cost_usd_after: number | null
  ts: string
}

interface SpendStats {
  active_developers: number
  events_today: number
  blocked_today: number
  tokens_saved_today: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const AI_TOOL_BADGES: Record<string, { label: string; bg: string; color: string }> = {
  claude_code: { label: "Claude Code", bg: "var(--accent-weak)",                color: "var(--accent-text)"       },
  codex:       { label: "Codex",       bg: "var(--ok-bg)",                      color: "var(--ok)"                },
  cursor:      { label: "Cursor",      bg: "rgba(147,51,234,0.10)",             color: "rgb(126,34,206)"          },
  windsurf:    { label: "Windsurf",    bg: "rgba(14,165,233,0.10)",             color: "rgb(2,132,199)"           },
  gemini:      { label: "Gemini",      bg: "rgba(249,115,22,0.10)",             color: "rgb(234,88,12)"           },
}

const DECISION_CONFIG: Record<
  string,
  { label: string; dotColor?: string; bg?: string; color?: string }
> = {
  allowed:  { label: "allowed",          dotColor: "var(--ok)"                                    },
  blocked:  { label: "blocked",          bg: "var(--err-bg)",   color: "var(--err)"               },
  warned:   { label: "warned",           bg: "var(--warn-bg)",  color: "var(--warn)"              },
  approval: { label: "approval pending", bg: "var(--info-bg)",  color: "var(--info)"              },
}

const ALL_TOOLS     = ["claude_code", "codex", "cursor", "windsurf", "gemini"]
const ALL_DECISIONS = ["allowed", "blocked", "warned", "approval"]

// ─── Guard Shell ──────────────────────────────────────────────────────────────

const GUARD_TABS = [
  { href: "/guard",          label: "Overview"  },
  { href: "/guard/spend",    label: "Spend"     },
  { href: "/guard/policies", label: "Policies"  },
  { href: "/guard/activity", label: "Activity"  },
  { href: "/guard/settings", label: "Settings"  },
]

function GuardShell({
  children,
  live,
  lastUpdated,
}: {
  children: React.ReactNode
  live?: boolean
  lastUpdated?: Date | null
}) {
  const pathname = usePathname()

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      {/* Page head */}
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
          {lastUpdated
            ? <>last updated: {timeAgo(lastUpdated.toISOString())}</>
            : live !== undefined
              ? (live ? "last updated: just now" : "connecting…")
              : null
          }
        </div>
      </div>

      {/* Tab nav */}
      <div className="guard-tab-nav">
        {GUARD_TABS.map(tab => {
          const isActive = tab.href === "/guard"
            ? pathname === "/guard"
            : pathname?.startsWith(tab.href)
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`guard-tab${isActive ? " active" : ""}`}
            >
              {tab.label}
            </Link>
          )
        })}
      </div>

      {children}
    </div>
  )
}

// ─── Helper components ────────────────────────────────────────────────────────

const normTool = (t: string) => t.replace(/-/g, "_")

function AiToolBadge({ tool }: { tool: string }) {
  const cfg = AI_TOOL_BADGES[normTool(tool)]
  if (!cfg) {
    return (
      <span style={{
        display: "inline-flex",
        alignItems: "center",
        fontSize: 12,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: 999,
        background: "var(--surface-3)",
        color: "var(--text-2)",
      }}>
        {tool}
      </span>
    )
  }
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      fontSize: 12,
      fontWeight: 500,
      padding: "2px 8px",
      borderRadius: 999,
      background: cfg.bg,
      color: cfg.color,
    }}>
      {cfg.label}
    </span>
  )
}

function DecisionBadge({ decision }: { decision: string }) {
  const cfg = DECISION_CONFIG[decision]
  if (!cfg) return <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{decision}</span>

  if (decision === "allowed") {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--ok)" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.dotColor, display: "inline-block" }} />
      </span>
    )
  }
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      fontSize: 12,
      fontWeight: 500,
      padding: "2px 8px",
      borderRadius: 999,
      background: cfg.bg,
      color: cfg.color,
    }}>
      {cfg.label}
    </span>
  )
}

type TrendPeriod = "Daily" | "Weekly" | "Monthly"
interface TrendPoint { date: string; claude: number; codex: number; other: number }

function CostTrendChart({
  apiBase,
  workspaceId,
  token,
}: {
  apiBase: string
  workspaceId: string
  token: string | null
}) {
  const [scale, setScale] = useState<TrendPeriod>("Daily")
  const [data, setData] = useState<TrendPoint[]>([])
  const [loading, setLoading] = useState(true)

  const periodParam = scale.toLowerCase() as "daily" | "weekly" | "monthly"

  useEffect(() => {
    setLoading(true)
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    const tzOffset = new Date().getTimezoneOffset()
    fetch(
      `${apiBase}/guard/events/cost-trend?period=${periodParam}&workspace_id=${workspaceId}&tz_offset=${tzOffset}`,
      { headers }
    )
      .then(r => r.json())
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [periodParam, apiBase, workspaceId, token])

  const hasData = data.some(d => d.claude > 0 || d.codex > 0 || d.other > 0)

  return (
    <div className="card" style={{ padding: "20px 22px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 22 }}>
        <div style={{ fontWeight: 650, fontSize: 15 }}>Est. cost trend</div>
        <div style={{ marginLeft: "auto", display: "flex", background: "var(--surface-3)", borderRadius: 8, padding: 3 }}>
          {(["Daily", "Weekly", "Monthly"] as TrendPeriod[]).map(s => (
            <button
              key={s}
              onClick={() => setScale(s)}
              style={{
                border: "none",
                background: scale === s ? "var(--inverse)" : "transparent",
                color: scale === s ? "var(--on-inverse)" : "var(--text-3)",
                fontSize: 12,
                fontWeight: 600,
                padding: "5px 12px",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ height: 160, background: "var(--surface-2)", borderRadius: 8 }} />
      ) : !hasData ? (
        <div style={{ height: 160, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, color: "var(--text-muted)" }}>
          No cost data yet
        </div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => periodParam === "monthly" ? v.slice(0, 7) : v.slice(5)}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${v}`}
              />
              <Tooltip
                formatter={(val, name) => [`$${Number(val ?? 0).toFixed(4)}`, String(name)]}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid var(--border)" }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="claude" name="Claude" stackId="a" fill="var(--accent)" radius={[0, 0, 0, 0]} />
              <Bar dataKey="codex"  name="Codex"  stackId="a" fill="var(--ok)"     radius={[3, 3, 0, 0]} />
              {data.some(d => d.other > 0) && (
                <Bar dataKey="other" name="Other" stackId="a" fill="var(--text-muted)" radius={[3, 3, 0, 0]} />
              )}
            </BarChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", gap: 18, justifyContent: "center", marginTop: 14, fontSize: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--accent)", display: "inline-block" }} />
              <span style={{ color: "var(--text-2)" }}>Claude</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--ok)", display: "inline-block" }} />
              <span style={{ color: "var(--text-2)" }}>Codex</span>
            </span>
          </div>
        </>
      )}
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

// ─── Stat card ────────────────────────────────────────────────────────────────

type StatTone = "ok" | "err" | "accent" | "plain"

function GuardStatCard({
  label,
  value,
  sub,
  tone = "plain",
  onClick,
  active,
}: {
  label: string
  value: number | string
  sub?: React.ReactNode
  tone?: StatTone
  onClick?: () => void
  active?: boolean
}) {
  const toneColor: Record<StatTone, string> = {
    accent: "var(--accent-text)",
    ok:     "var(--ok)",
    err:    "var(--err)",
    plain:  "var(--text)",
  }
  return (
    <div
      className="card card-pad"
      style={{
        cursor: onClick ? "pointer" : undefined,
        outline: active ? "2px solid var(--accent)" : undefined,
      }}
      onClick={onClick}
    >
      <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", color: toneColor[tone], lineHeight: 1.1 }}>
        {value}
      </div>
      <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>{label}</div>
      {sub && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

function SavingsStatCard({
  savings,
  loading,
}: {
  savings: GuardSavingsSummary | null
  loading: boolean
}) {
  if (loading) {
    return <div className="card card-pad" style={{ height: 80 }} />
  }

  const hasSavings =
    savings !== null &&
    (savings.team_total.rtk_saved_tokens > 0 || savings.team_total.booster_saved_tokens > 0)

  if (hasSavings && savings !== null) {
    const totalTokens = savings.team_total.rtk_saved_tokens + savings.team_total.booster_saved_tokens
    const totalUsd    = savings.team_total.rtk_saved_usd + savings.team_total.booster_saved_usd
    return (
      <GuardStatCard
        label="Est. savings"
        value={formatTotalTokensSaved(totalTokens) + " tokens"}
        tone="accent"
        sub={<>${totalUsd.toFixed(2)} saved</>}
      />
    )
  }

  return (
    <div className="card card-pad">
      <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-muted)", lineHeight: 1.1 }}>—</div>
      <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>Est. savings</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
        <a href="https://pypi.org/project/rtk/" target="_blank" rel="noopener noreferrer"
           style={{ color: "var(--accent-text)", textDecoration: "underline" }}>RTK</a>
        {" + "}
        <a href="https://pypi.org/project/agent-booster/" target="_blank" rel="noopener noreferrer"
           style={{ color: "var(--accent-text)", textDecoration: "underline" }}>Agent Booster</a>
      </div>
    </div>
  )
}

// ─── By AI tool table ─────────────────────────────────────────────────────────

function ByToolTable({ events }: { events: GuardEvent[] }) {
  const byTool = useMemo(() => {
    const map = new Map<string, { tokens: number; cost: number }>()
    for (const ev of events) {
      const key = ev.ai_tool || "unknown"
      const prev = map.get(key) ?? { tokens: 0, cost: 0 }
      map.set(key, {
        tokens: prev.tokens + ((ev.tokens_after ?? ev.tokens_input ?? 0)),
        cost:   prev.cost   + (ev.cost_usd_after ?? 0),
      })
    }
    const total = Array.from(map.values()).reduce((s, v) => s + v.tokens, 0)
    return Array.from(map.entries())
      .map(([tool, { tokens, cost }]) => ({
        tool,
        tokens,
        cost,
        pct: total > 0 ? Math.round((tokens / total) * 100) : 0,
      }))
      .sort((a, b) => b.tokens - a.tokens)
  }, [events])

  const fmtTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
    return String(n)
  }

  if (byTool.length === 0) return null

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "15px 20px 13px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14.5 }}>
        By AI tool
      </div>
      {/* Header */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1.6fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
        {["Tool", "Tokens used", "Est. cost", "% of total"].map((h, i) => (
          <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
        ))}
      </div>
      {byTool.map(t => (
        <div
          key={t.tool}
          style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1.6fr", gap: 14, padding: "13px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}
        >
          <div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{t.tool}</div>
          <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>{fmtTokens(t.tokens)}</div>
          <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>${t.cost.toFixed(4)}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <div style={{ flex: 1, height: 8, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
              <div style={{ width: `${t.pct}%`, height: "100%", background: "var(--accent)", borderRadius: 6 }} />
            </div>
            <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", width: 34, textAlign: "right" }}>{t.pct}%</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Select style helper ──────────────────────────────────────────────────────

const selectStyle: React.CSSProperties = {
  fontSize: 13,
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "6px 12px",
  background: "var(--surface)",
  color: "var(--text-2)",
  outline: "none",
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
  const [filterTool, setFilterTool]           = useState("all")
  const [filterDecision, setFilterDecision]   = useState("all")
  const [filterDev, setFilterDev]             = useState("all")
  const [filterDateRange, setFilterDateRange] = useState("7d")
  const [filterSearch, setFilterSearch]       = useState("")

  const esRef = useRef<EventSource | null>(null)

  // ── API helpers ─────────────────────────────────────────────────────────────

  const buildHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }, [getToken])

  useEffect(() => {
    if (!teamLoading && !teamId) setLoading(false)
  }, [teamLoading, teamId])

  const dateRangeToSince = useCallback((range: string): string | null => {
    const now = new Date()
    if (range === "today") {
      const start = new Date(now); start.setHours(0, 0, 0, 0)
      return start.toISOString()
    }
    if (range === "7d")  { const d = new Date(now); d.setDate(d.getDate() - 7);  return d.toISOString() }
    if (range === "30d") { const d = new Date(now); d.setDate(d.getDate() - 30); return d.toISOString() }
    return null
  }, [])

  const loadEvents = useCallback(async (decision?: string, dateRange?: string) => {
    if (!teamId) return
    const headers = await buildHeaders()
    const base    = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params  = new URLSearchParams({ limit: String(PAGE_SIZE), offset: "0" })
    params.set("workspace_id", teamId)
    if (decision && decision !== "all") params.set("decision", decision)
    const since = dateRangeToSince(dateRange ?? filterDateRange)
    if (since) params.set("since", since)
    try {
      const res = await fetch(`${base}/guard/events?${params}`, { headers })
      if (res.ok) {
        const data: GuardEvent[] = await res.json()
        setEvents(data)
        setHasMore(data.length === PAGE_SIZE)
        setLastUpdated(new Date())
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [buildHeaders, teamId, PAGE_SIZE, filterDateRange, dateRangeToSince])

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

    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${base}/guard/events/stream?${params}`)
    esRef.current = es

    es.onopen    = () => setLive(true)
    es.onerror   = () => setLive(false)
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.kind === "stream_timeout") return
        if (data.id && data.decision) {
          setEvents(prev => {
            const merged = [data as GuardEvent, ...prev.filter(e => e.id !== data.id)]
            return merged.slice(0, 200)
          })
          setLastUpdated(new Date())
        }
      } catch { /* malformed frame */ }
    }
  }, [getToken, teamId])

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
    const statsInterval   = setInterval(() => { loadStats() }, 60_000)
    const refreshInterval = setInterval(() => { refreshRecent() }, 10_000)
    return () => {
      clearInterval(statsInterval)
      clearInterval(refreshInterval)
      esRef.current?.close()
    }
  }, [connectSSE, loadEvents, loadStats, refreshRecent])

  useEffect(() => {
    loadEvents(filterDecision !== "all" ? filterDecision : undefined, filterDateRange)
  }, [filterDecision, filterDateRange, loadEvents])

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
    const localToday = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
    const todayStr    = localToday(new Date())
    const todayEvents = events.filter(e => localToday(new Date(e.ts)) === todayStr)
    const distinctDevs = new Set(events.map(e => e.user_email).filter(Boolean)).size
    return {
      active_developers: distinctDevs > 0 ? distinctDevs : events.length > 0 ? 1 : 0,
      events_today:      todayEvents.length,
      blocked_today:     todayEvents.filter(e => e.decision === "blocked").length,
      tokens_saved_today: todayEvents.reduce(
        (s, e) => s + Math.max(0, (e.tokens_before ?? 0) - (e.tokens_after ?? 0)), 0
      ),
      est_cost_today:     todayEvents.reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
      claude_cost_today:  todayEvents
        .filter(e => normTool(e.ai_tool).includes("claude"))
        .reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
      codex_cost_today:   todayEvents
        .filter(e => normTool(e.ai_tool).includes("codex"))
        .reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
    }
  }, [events])

  const currentUserEmail = user?.primaryEmailAddress?.emailAddress ?? null

  const filteredEvents = useMemo(() => {
    const q = filterSearch.toLowerCase()
    return events.filter(ev => {
      if (!permissions.canViewAllActivity && ev.user_email !== currentUserEmail) return false
      if (filterTool !== "all"     && normTool(ev.ai_tool) !== filterTool) return false
      if (filterDecision !== "all" && ev.decision   !== filterDecision)    return false
      if (filterDev !== "all"      && ev.user_email !== filterDev)         return false
      if (q && !ev.user_email?.toLowerCase().includes(q) && !ev.rule_id?.toLowerCase().includes(q)) return false
      return true
    })
  }, [events, filterTool, filterDecision, filterDev, filterSearch, permissions.canViewAllActivity, currentUserEmail])

  const exportCSV = useCallback(() => {
    const header = "timestamp,developer,tool,decision,rule_id,rule_message,tokens_input,tokens_output,cost_usd"
    const rows = filteredEvents.map(ev => [
      ev.ts, ev.user_email ?? "", ev.ai_tool ?? "", ev.decision,
      ev.rule_id ?? "", (ev.rule_message ?? "").replace(/,/g, ";"),
      ev.tokens_input ?? 0, ev.tokens_output ?? 0, ev.cost_usd_after ?? 0,
    ].join(","))
    const blob = new Blob([header + "\n" + rows.join("\n")], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a"); a.href = url; a.download = "guard-activity.csv"; a.click()
    URL.revokeObjectURL(url)
  }, [filteredEvents])

  // ── Render ───────────────────────────────────────────────────────────────────

  const blockedToday = stats?.blocked_today || derivedStats.blocked_today

  return (
    <GuardShell live={live} lastUpdated={lastUpdated}>

      {/* Viewer-scoped notice */}
      {!loading && !permissionsLoading && !permissions.canViewAllActivity && (
        <div style={{
          borderRadius: 8,
          border: "1px solid var(--warn-bd)",
          background: "var(--warn-bg)",
          padding: "10px 16px",
          fontSize: 12,
          color: "var(--warn)",
          marginBottom: 16,
        }}>
          You can view your own activity only. Contact your admin to request broader access.
        </div>
      )}

      {/* 5 stat cards */}
      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 16 }}>
          {[...Array(5)].map((_, i) => (
            <div key={i} className="card card-pad" style={{ height: 80 }} />
          ))}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 16 }}>
          <GuardStatCard
            label="Active developers"
            value={stats?.active_developers || derivedStats.active_developers}
            tone="ok"
            sub="sessions in range"
          />
          <GuardStatCard
            label="Events today"
            value={stats?.events_today || derivedStats.events_today}
            tone="plain"
            sub="tool calls logged"
          />
          <GuardStatCard
            label="Blocked today"
            value={blockedToday}
            tone={blockedToday > 0 ? "err" : "plain"}
            onClick={() => setFilterDecision(prev => prev === "blocked" ? "all" : "blocked")}
            active={filterDecision === "blocked"}
            sub={blockedToday > 0 ? "click to filter" : "none blocked"}
          />
          <GuardStatCard
            label="Tokens saved"
            value={formatTotalTokensSaved(stats?.tokens_saved_today || derivedStats.tokens_saved_today)}
            tone="accent"
            sub="vs unguarded calls"
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

      {/* By AI tool table */}
      {!loading && events.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <ByToolTable events={events} />
        </div>
      )}

      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <select
          value={filterDateRange}
          onChange={e => setFilterDateRange(e.target.value)}
          style={selectStyle}
        >
          <option value="today">Today</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="all">All time</option>
        </select>

        <select
          value={filterTool}
          onChange={e => setFilterTool(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All tools</option>
          {ALL_TOOLS.map(t => (
            <option key={t} value={t}>{AI_TOOL_BADGES[t]?.label ?? t}</option>
          ))}
        </select>

        <select
          value={filterDecision}
          onChange={e => setFilterDecision(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All decisions</option>
          {ALL_DECISIONS.map(d => (
            <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
          ))}
        </select>

        <select
          value={filterDev}
          onChange={e => setFilterDev(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All developers</option>
          {developerEmails.map(email => (
            <option key={email} value={email}>{email}</option>
          ))}
        </select>

        <div style={{ position: "relative" }}>
          <input
            type="text"
            value={filterSearch}
            onChange={e => setFilterSearch(e.target.value)}
            placeholder="Search rule or email…"
            style={{
              ...selectStyle,
              paddingRight: 28,
              width: 192,
            }}
          />
          {filterSearch && (
            <button
              onClick={() => setFilterSearch("")}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                color: "var(--text-muted)",
                fontSize: 12,
                cursor: "pointer",
                padding: 0,
                lineHeight: 1,
              }}
            >✕</button>
          )}
        </div>

        {(filterTool !== "all" || filterDecision !== "all" || filterDev !== "all" || filterSearch) && (
          <button
            onClick={() => { setFilterTool("all"); setFilterDecision("all"); setFilterDev("all"); setFilterSearch("") }}
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "6px 12px",
              background: "var(--surface)",
              cursor: "pointer",
            }}
          >
            Clear filters
          </button>
        )}

        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
          {filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}
        </span>

        {filteredEvents.length > 0 && (
          <button
            onClick={exportCSV}
            style={{
              fontSize: 12,
              color: "var(--text-2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "6px 12px",
              background: "var(--surface)",
              cursor: "pointer",
            }}
          >
            Export CSV
          </button>
        )}
      </div>

      {/* Activity feed */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{ background: "var(--surface-3)", borderRadius: 12, height: 48 }} />
          ))}
        </div>
      ) : filteredEvents.length === 0 ? (
        <div style={{
          borderRadius: 12,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          padding: "40px 24px",
          textAlign: "center",
          fontSize: 13,
          color: "var(--text-muted)",
        }}>
          No events match the current filters.
        </div>
      ) : (
        <>
          <div style={{ background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)", overflow: "hidden" }}>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {[
                    { label: "Time",     w: 80,   align: "left"  as const },
                    { label: "User",     w: undefined, align: "left"  as const },
                    { label: "AI tool",  w: undefined, align: "left"  as const },
                    { label: "Call",     w: undefined, align: "left"  as const },
                    { label: "Input",    w: undefined, align: "left"  as const },
                    { label: "Decision", w: undefined, align: "left"  as const },
                    { label: "Tokens",   w: undefined, align: "right" as const },
                  ].map(col => (
                    <th
                      key={col.label}
                      style={{
                        padding: "12px 16px",
                        textAlign: col.align,
                        fontWeight: 500,
                        fontSize: 11,
                        color: "var(--text-muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        width: col.w,
                      }}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredEvents.map((ev, idx) => (
                  <tr
                    key={ev.id}
                    style={{
                      borderBottom: idx < filteredEvents.length - 1 ? "1px solid var(--border)" : undefined,
                      background: ev.decision === "blocked" ? "var(--err-bg)" : undefined,
                    }}
                  >
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                      {timeAgo(ev.ts)}
                    </td>
                    <td style={{ padding: "12px 16px", maxWidth: 160 }}>
                      {ev.user_email ? (
                        <>
                          <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {ev.user_email.split("@")[0]}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={ev.user_email}>
                            {ev.user_email}
                          </div>
                        </>
                      ) : (
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <AiToolBadge tool={ev.ai_tool} />
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "var(--text-2)", whiteSpace: "nowrap" }}>
                      {ev.tool_call}
                    </td>
                    <td
                      style={{ padding: "12px 16px", fontSize: 12, color: "var(--text-3)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "copy", userSelect: "none" }}
                      title={ev.input_summary ? "Double-click to copy" : undefined}
                      onDoubleClick={() => {
                        if (!ev.input_summary) return
                        navigator.clipboard.writeText(ev.input_summary).catch(() => {})
                      }}
                    >
                      {ev.input_summary ?? "—"}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <DecisionBadge decision={ev.decision} />
                      {ev.rule_message && ev.decision !== "allowed" && (
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 120 }} title={ev.rule_message}>
                          {ev.rule_message}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", fontSize: 12, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                      {(() => {
                        const used = formatTokensUsed(ev.tokens_before, ev.tokens_after)
                        if (used) return <span style={{ color: "var(--text-2)" }}>{used}</span>
                        if (ev.tokens_saved && ev.tokens_saved > 0)
                          return <span style={{ color: "var(--ok)" }}>{formatTokensSaved(ev.tokens_saved)} saved</span>
                        return <span style={{ color: "var(--border)" }}>—</span>
                      })()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasMore && (
            <div style={{ display: "flex", justifyContent: "center", paddingTop: 16, paddingBottom: 8 }}>
              <button
                onClick={loadMore}
                disabled={loadingMore}
                style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: loadingMore ? "var(--text-muted)" : "var(--accent-text)",
                  background: "none",
                  border: "none",
                  cursor: loadingMore ? "default" : "pointer",
                  padding: 0,
                }}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </GuardShell>
  )
}
