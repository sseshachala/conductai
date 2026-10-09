"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useAuth } from "@/lib/auth/client"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { usePolledFetch, useLatestRequest } from "@/hooks/usePolledFetch"
import { API } from "@/lib/api"
import type { AuditEvent } from "@/components/guard/ActivityRow"

const PAGE_SIZE = 50

interface Params {
  teamId: string | null
  teamLoading: boolean
  activeView: string
  effectiveDeveloperFilter: string
  filterTool: string
  filterDecision: string
  filterSince: string
  filterUntil: string
  filterRuleId: string
  filterHookSession: string
  filterAgentIdentity: string
  filterEventId: string
}

/** Flight Recorder feed: paged load, background refresh, SSE "Go Live". */
export function useGuardEventsFeed(params: Params) {
  const {
    teamId, teamLoading, activeView, effectiveDeveloperFilter,
    filterTool, filterDecision, filterSince, filterUntil, filterRuleId,
    filterHookSession, filterAgentIdentity, filterEventId,
  } = params
  const { getToken } = useAuth()
  const { authFetch } = useAuthFetch()
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [streaming, setStreaming] = useState(false)
  // #1990 item D — drift between server clock and browser clock (see page).
  const [serverTimeDrift, setServerTimeDrift] = useState<number>(0)
  // Unseen rows from poll/SSE held back so the list doesn't jump under the cursor.
  const [pending, setPending] = useState<AuditEvent[]>([])
  const eventsRef = useRef<AuditEvent[]>([])
  eventsRef.current = events
  const pendingRef = useRef<AuditEvent[]>([])
  pendingRef.current = pending
  const esRef = useRef<EventSource | null>(null)

  function buildParams(before?: string) {
    const p = new URLSearchParams({ limit: String(PAGE_SIZE) })
    if (before) p.set("before", before)
    if (teamId) p.set("workspace_id", teamId)
    if (filterEventId) {
      p.set("event_id", filterEventId)
      return p.toString()
    }
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

  const beginLoad = useLatestRequest()

  // Merge incoming rows (newest first). Known rows update in place; unseen rows
  // prepend directly when the user is at the top of the page, else wait in `pending`.
  const intake = useCallback((incoming: AuditEvent[], cap?: number) => {
    const upd = new Map(incoming.map(r => [r.id, r] as const))
    const known = new Set(eventsRef.current.map(r => r.id))
    const waiting = new Set(pendingRef.current.map(r => r.id))
    const fresh = incoming.filter(r => !known.has(r.id) && !waiting.has(r.id))
    const apply = (rows: AuditEvent[]) => rows.map(r => upd.get(r.id) ?? r)
    const atTop = typeof window === "undefined" || window.scrollY <= 8
    if (atTop) {
      setPending([])
      setEvents(prev => {
        const merged = [...pendingRef.current, ...fresh, ...apply(prev)]
        return cap ? merged.slice(0, cap) : merged
      })
    } else {
      setEvents(prev => apply(prev))
      setPending(prev => [...fresh, ...apply(prev)].slice(0, cap ?? Infinity))
    }
  }, [])

  const showNew = useCallback(() => {
    const rows = pendingRef.current
    setPending([])
    setEvents(prev => {
      const known = new Set(prev.map(r => r.id))
      return [...rows.filter(r => !known.has(r.id)), ...prev]
    })
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" })
  }, [])
  const foregroundInFlight = useRef(false)

  // Foreground load (mount / filter change) resets the list and shows the
  // skeleton. Background load (poll) never touches loading, offset or loaded
  // pages: it prepends rows we have not seen and updates known rows in place.
  const load = useCallback(async (opts?: { background?: boolean }) => {
    if (!teamId) return
    const background = !!opts?.background
    if (background && foregroundInFlight.current) return
    const isCurrent = beginLoad()
    if (!background) {
      foregroundInFlight.current = true
      setLoading(true)
      setError(null)
      setPending([])
    }
    try {
      const res = await authFetch(`${API}/guard/events?${buildParams()}`)
      if (!res.ok) throw new Error("Failed to load activity events")
      const rows: AuditEvent[] = await res.json()
      if (!isCurrent()) return
      if (background) {
        intake(rows)
      } else {
        setEvents(rows)
        setHasMore(rows.length === PAGE_SIZE)
      }
      setLive(true)
      setLastUpdated(new Date())
    } catch (err) {
      if (!isCurrent()) return
      if (!background) setError(err instanceof Error ? err.message : "Unknown error")
      setLive(false)
    } finally {
      if (!background && isCurrent()) {
        foregroundInFlight.current = false
        setLoading(false)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch, intake, teamId, effectiveDeveloperFilter, filterTool, filterDecision, filterSince, filterUntil, filterRuleId, filterHookSession, filterAgentIdentity, filterEventId])

  useEffect(() => { void load() }, [load])

  // Background refresh: events view only, and never while SSE "Go Live" is on.
  usePolledFetch(() => { void load({ background: true }) }, 30_000, activeView === "events" && !streaming)

  // SSE real-time feed — only active when streaming=true (user clicked Go Live)
  const LIVE_EVENT_CAP = 500
  useEffect(() => {
    if (!streaming || !teamId || filterEventId) return
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
            // Updates (durable finalize UPDATE) flip in place; fresh rows are
            // held in `pending` unless the user is at the top (#1959 Phase 3).
            intake((msg.events as AuditEvent[]).filter(ev =>
              (!filterHookSession || ev.hook_session_id === filterHookSession)
              && (!filterAgentIdentity || ev.agent_identity_id === filterAgentIdentity)
            ).reverse(), LIVE_EVENT_CAP)
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
  }, [streaming, intake, teamId, getToken, filterHookSession, filterAgentIdentity, filterEventId])

  async function loadMore() {
    const last = eventsRef.current[eventsRef.current.length - 1]
    if (!last || loadingMore) return
    setLoadingMore(true)
    try {
      const res = await authFetch(`${API}/guard/events?${buildParams(`${last.ts}|${last.id}`)}`)
      if (!res.ok) throw new Error("Failed to load more events")
      const rows: AuditEvent[] = await res.json()
      setEvents(prev => {
        const known = new Set(prev.map(r => r.id))
        return [...prev, ...rows.filter(r => !known.has(r.id))]
      })
      setHasMore(rows.length === PAGE_SIZE)
    } catch {
      // non-fatal
    } finally {
      setLoadingMore(false)
    }
  }

  return {
    events, loading, loadingMore, hasMore, error, live, lastUpdated, streaming, setStreaming,
    serverTimeDrift, loadMore, pending, showNew,
  }
}
