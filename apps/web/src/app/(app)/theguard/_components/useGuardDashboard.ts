"use client"

import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import { useAuth, useUser } from "@/lib/auth/client"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import { API } from "@/lib/api/client"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useGuardSavings } from "@/hooks/useGuardSavings"
import { useTokenGuardrails } from "@/hooks/useTokenGuardrails"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { canonicalTool, type GuardEvent, type SpendStats, type ToolCoverageRow, type GuardSessionRow } from "./widgets"

export function useGuardDashboard() {
  const { getToken } = useAuth()
  const { authFetch } = useAuthFetch()

  // #1567 empty-state banner gate: only show the banner for genuinely
  // eligible first-time workspaces. Session endpoint returns
  // {ineligible: true} for workspaces with any run or vault key.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const r = await authFetch(`${API}/guard/trial/session`)
        if (!r.ok) return
        const data = await r.json()
        if (!cancelled) setTrialSession({
          ineligible: !!data.ineligible,
          expired: !!data.expired,
          cap_used: data.cap_used ?? 0,
        })
      } catch { /* silent — banner just stays hidden on error */ }
    })()
    return () => { cancelled = true }
  }, [authFetch])
  const { user } = useUser()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const { savings, loading: savingsLoading } = useGuardSavings(teamId)
  const { guardrails } = useTokenGuardrails(
    !teamLoading && teamId === activeWorkspace?.id ? teamId : null,
  )

  const [events, setEvents]           = useState<GuardEvent[]>([])
  const [stats, setStats]             = useState<SpendStats | null>(null)
  const [loading, setLoading]         = useState(true)
  const [recentSessions, setRecentSessions] = useState<GuardSessionRow[]>([])
  const [toolCoverage, setToolCoverage] = useState<ToolCoverageRow[]>([])
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore]         = useState(true)
  const [live, setLive]               = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [chartToken, setChartToken]   = useState<string | null>(null)
  const [agentCount, setAgentCount]   = useState<number | null>(null)
  const [proxyCount, setProxyCount]   = useState<number | null>(null)
  const [trialSession, setTrialSession] = useState<{
    setup_required?: boolean
    ineligible: boolean
    expired: boolean
    cap_used: number
  } | null>(null)

  const PAGE_SIZE = 100

  // Filters
  const [filterTool, setFilterTool]           = useState("all")
  const [filterDecision, setFilterDecision]   = useState("all")
  const [filterDev, setFilterDev]             = useState("all")
  const [filterDateRange, setFilterDateRange] = useState("7d")
  const [filterSearch, setFilterSearch]       = useState("")
  const [view, setView]                       = useState<"overview" | "spend_glance">("overview")

  const esRef = useRef<EventSource | null>(null)

  // ── API helpers ─────────────────────────────────────────────────────────────

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
    const params: Record<string, string> = { limit: String(PAGE_SIZE), offset: "0", workspace_id: teamId }
    if (decision && decision !== "all") params.decision = decision
    const since = dateRangeToSince(dateRange ?? filterDateRange)
    if (since) params.since = since
    try {
      const data: GuardEvent[] = await guard.events.list(authFetch, params)
      setEvents(data)
      setHasMore(data.length === PAGE_SIZE)
      setLastUpdated(new Date())
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [authFetch, teamId, PAGE_SIZE, filterDateRange, dateRangeToSince])

  const loadMore = useCallback(async () => {
    if (!teamId || loadingMore) return
    setLoadingMore(true)
    const params: Record<string, string> = { limit: String(PAGE_SIZE), offset: String(events.length), workspace_id: teamId }
    if (filterDecision !== "all") params.decision = filterDecision
    if (filterTool !== "all")     params.ai_tool = filterTool
    if (filterDev !== "all")      params.user_email = filterDev
    const since = dateRangeToSince(filterDateRange)
    if (since) params.since = since
    try {
      const data: GuardEvent[] = await guard.events.list(authFetch, params)
      setEvents(prev => [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
    } catch {
      // non-fatal
    } finally {
      setLoadingMore(false)
    }
  }, [authFetch, teamId, events.length, loadingMore, PAGE_SIZE, filterDecision, filterTool, filterDev, filterDateRange, dateRangeToSince])

  const loadStats = useCallback(async () => {
    if (!teamId) return
    try {
      const data = await guard.spend.get(authFetch, { workspace_id: teamId })
      setStats(data)
    } catch { /* non-fatal */ }
    // Rule counts by persona — non-fatal, best-effort
    try {
      const sd = await guard.policies.list(authFetch, teamId)
      if (Array.isArray(sd)) {
        const active = sd.filter((r: any) => r.enabled && !r.archived_at)
        setAgentCount(active.filter((r: any) => r.persona === "agent").length)
        setProxyCount(active.filter((r: any) => r.persona === "proxy").length)
      }
    } catch { /* non-fatal */ }
  }, [authFetch, teamId])

  const loadToolCoverage = useCallback(async () => {
    if (!teamId) return
    try {
      const data = await guard.developerTools.list(authFetch, teamId)
      setToolCoverage(data)
    } catch { /* non-fatal */ }
  }, [authFetch, teamId])

  const loadRecentSessions = useCallback(async () => {
    if (!teamId) return
    try {
      const data = await guard.spend.sessions(authFetch, { limit: "10", offset: "0", workspace_id: teamId })
      setRecentSessions(data)
    } catch { /* non-fatal */ }
  }, [authFetch, teamId])

  const connectSSE = useCallback(async () => {
    if (!teamId) return
    const token  = await getToken()
    const params = new URLSearchParams()
    if (token) params.set("token", token)
    params.set("workspace_id", teamId)

    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${API}/guard/events/stream?${params}`)
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
    try {
      const fresh: GuardEvent[] = await guard.events.list(authFetch, { limit: "20", offset: "0", workspace_id: teamId })
      setEvents(prev => {
        const byId = new Map(prev.map(e => [e.id, e]))
        fresh.forEach(e => byId.set(e.id, e))
        const freshIds = new Set(fresh.map(e => e.id))
        return [...fresh, ...prev.filter(e => !freshIds.has(e.id))]
      })
    } catch { /* non-fatal */ }
  }, [authFetch, teamId])

  useEffect(() => {
    connectSSE()
    loadEvents()
    loadStats()
    loadToolCoverage()
    loadRecentSessions()
    const statsInterval        = setInterval(() => { loadStats() }, 60_000)
    const coverageInterval     = setInterval(() => { loadToolCoverage() }, 60_000)
    const sessionsInterval     = setInterval(() => { loadRecentSessions() }, 60_000)
    const refreshInterval      = setInterval(() => { refreshRecent() }, 10_000)
    return () => {
      clearInterval(statsInterval)
      clearInterval(coverageInterval)
      clearInterval(sessionsInterval)
      clearInterval(refreshInterval)
      esRef.current?.close()
    }
  }, [connectSSE, loadEvents, loadStats, loadToolCoverage, loadRecentSessions, refreshRecent])

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

  const toolsInData = useMemo(
    () => Array.from(new Set(events.map(e => canonicalTool(e.ai_tool)).filter(Boolean))).sort(),
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
      warned_today:      todayEvents.filter(e => e.decision === "warned").length,
      tokens_saved_today: todayEvents.reduce(
        (s, e) => s + Math.max(0, (e.tokens_before ?? 0) - (e.tokens_after ?? 0)), 0
      ),
      est_cost_today:     todayEvents.reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
      claude_cost_today:  todayEvents
        .filter(e => canonicalTool(e.ai_tool) === "claude_code")
        .reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
      codex_cost_today:   todayEvents
        .filter(e => canonicalTool(e.ai_tool) === "codex")
        .reduce((s, e) => s + (e.cost_usd_after ?? 0), 0),
    }
  }, [events])

  const tokenEfficiencyWarnings = useMemo(() => {
    const TOKEN_RULES = new Set(["warn-large-context-dump", "warn-deterministic-compute"])
    const flagged = events.filter(e => e.rule_id && TOKEN_RULES.has(e.rule_id))
    const flaggedTokens = flagged.reduce((s, e) => s + (e.tokens_before ?? 0), 0)
    return { count: flagged.length, tokens: flaggedTokens }
  }, [events])

  const currentUserEmail = user?.primaryEmailAddress?.emailAddress ?? null

  const filteredEvents = useMemo(() => {
    const q = filterSearch.toLowerCase()
    return events.filter(ev => {
      if (!permissions.canViewAllActivity && ev.user_email !== currentUserEmail) return false
      if (filterTool !== "all"     && canonicalTool(ev.ai_tool) !== filterTool) return false
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

  return {
    getToken,
    authFetch,
    user,
    teamId,
    teamLoading,
    activeWorkspace,
    permissions,
    permissionsLoading,
    savings,
    savingsLoading,
    guardrails,
    events,
    setEvents,
    stats,
    setStats,
    loading,
    setLoading,
    recentSessions,
    setRecentSessions,
    toolCoverage,
    setToolCoverage,
    loadingMore,
    setLoadingMore,
    hasMore,
    setHasMore,
    live,
    setLive,
    lastUpdated,
    setLastUpdated,
    chartToken,
    setChartToken,
    agentCount,
    setAgentCount,
    proxyCount,
    setProxyCount,
    trialSession,
    setTrialSession,
    PAGE_SIZE,
    filterTool,
    setFilterTool,
    filterDecision,
    setFilterDecision,
    filterDev,
    setFilterDev,
    filterDateRange,
    setFilterDateRange,
    filterSearch,
    setFilterSearch,
    view,
    setView,
    esRef,
    dateRangeToSince,
    loadEvents,
    loadMore,
    loadStats,
    loadToolCoverage,
    loadRecentSessions,
    connectSSE,
    refreshRecent,
    developerEmails,
    toolsInData,
    derivedStats,
    tokenEfficiencyWarnings,
    currentUserEmail,
    filteredEvents,
    exportCSV,
    blockedToday,
  }
}

export type GuardDashboardState = ReturnType<typeof useGuardDashboard>
