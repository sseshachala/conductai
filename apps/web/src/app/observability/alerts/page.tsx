"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface Alert {
  id: string
  event_type: string
  severity: string
  run_id: string | null
  workflow_id: string | null
  payload: Record<string, unknown>
  created_at: string
  resolved_at: string | null
}

const EVENT_TYPES_FILTER = [
  { value: "", label: "All types" },
  { value: "stale_worker", label: "Stale worker" },
  { value: "approval_timeout", label: "Approval timeout" },
  { value: "repeated_failure", label: "Repeated failures" },
  { value: "credential_expiry", label: "Credential expired (401)" },
] as const

const EVENT_LABELS: Record<string, string> = {
  stale_worker:      "Stale worker",
  approval_timeout:  "Approval timeout",
  repeated_failure:  "Repeated failures",
  credential_expiry: "Credential expired (401)",
}

const SEVERITY_STYLES: Record<string, string> = {
  info:    "text-blue-700 bg-blue-50 border-blue-200",
  warning: "text-amber-700 bg-amber-50 border-amber-200",
  error:   "text-red-700 bg-red-50 border-red-200",
}


const PAGE_SIZE = 50

export default function AlertsPage() {
  const { getToken } = useAuth()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [eventType, setEventType] = useState("")
  const [resolving, setResolving] = useState<string | null>(null)

  const load = useCallback(async (off: number, type: string, replace: boolean) => {
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id") ?? ""
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    if (workspaceId) headers["x-workspace-id"] = workspaceId
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(off) })
    if (type) params.set("event_type", type)

    try {
      const res = await fetch(`${base}/observability/alerts?${params}`, { headers })
      if (!res.ok) return
      const data: Alert[] = await res.json()
      setAlerts(prev => replace ? data : [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
    } finally {
      setLoading(false)
    }
  }, [getToken])

  useEffect(() => {
    setLoading(true)
    setOffset(0)
    load(0, eventType, true)
  }, [eventType, load])

  async function resolve(id: string) {
    setResolving(id)
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id") ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    if (workspaceId) headers["x-workspace-id"] = workspaceId
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    try {
      const res = await fetch(`${base}/observability/alerts/${id}/resolve`, { method: "POST", headers })
      if (res.ok) {
        const updated: Alert = await res.json()
        setAlerts(prev => prev.map(a => a.id === id ? updated : a))
      }
    } finally {
      setResolving(null)
    }
  }

  function loadMore() {
    const next = offset + PAGE_SIZE
    setOffset(next)
    load(next, eventType, false)
  }

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-stone-400 mb-1">
              <Link href="/observability" className="hover:text-stone-600 transition-colors">Observability</Link>
              <span>/</span>
              <span className="text-stone-600">Alert History</span>
            </div>
            <h1 className="text-xl font-semibold text-stone-900">Alert History</h1>
            <p className="text-sm text-stone-500 mt-0.5">Watchdog events from the last 30 days</p>
          </div>
          <select
            value={eventType}
            onChange={e => setEventType(e.target.value)}
            className="text-sm border border-stone-200 rounded-lg px-3 py-1.5 bg-white text-stone-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {EVENT_TYPES_FILTER.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>

        {/* Table */}
        {loading ? (
          <div className="space-y-2 animate-pulse">
            {[...Array(6)].map((_, i) => <div key={i} className="bg-stone-100 rounded-xl h-16" />)}
          </div>
        ) : alerts.length === 0 ? (
          <div className="rounded-xl border border-stone-200 bg-white px-6 py-16 text-center">
            <div className="text-stone-400 text-sm">No alerts in the last 30 days</div>
            <Link href="/observability" className="text-xs text-indigo-600 hover:underline mt-2 inline-block">
              Back to Observability
            </Link>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left font-medium">Type</th>
                  <th className="px-4 py-3 text-left font-medium">Agent</th>
                  <th className="px-4 py-3 text-left font-medium">Detail</th>
                  <th className="px-4 py-3 text-left font-medium">When</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {alerts.map(a => {
                  const sevStyle = SEVERITY_STYLES[a.severity] ?? SEVERITY_STYLES.warning
                  const label = EVENT_LABELS[a.event_type] ?? a.event_type.replace(/_/g, " ")
                  const workflowName = (a.payload.workflow_name as string) ?? "—"
                  const detail = a.event_type === "stale_worker"
                    ? `Stuck for ${a.payload.minutes_stale ?? "?"} min`
                    : a.event_type === "approval_timeout"
                    ? `Waiting ${a.payload.minutes_waiting ?? "?"} min`
                    : a.event_type === "repeated_failure"
                    ? `${a.payload.fail_count ?? "?"} failures in 1h`
                    : a.event_type === "credential_expiry"
                    ? (a.payload.hint as string) ?? "Reconnect in Settings"
                    : ""

                  return (
                    <tr key={a.id} className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors">
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border ${sevStyle}`}>
                          {label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {a.workflow_id ? (
                          <Link href={`/workflows/${a.workflow_id}`} className="text-stone-800 hover:text-indigo-600 transition-colors font-medium">
                            {workflowName}
                          </Link>
                        ) : (
                          <span className="text-stone-500">{workflowName}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-stone-500 text-xs max-w-xs truncate">{detail}</td>
                      <td className="px-4 py-3 text-stone-400 text-xs whitespace-nowrap">{timeAgo(a.created_at)}</td>
                      <td className="px-4 py-3">
                        {a.resolved_at ? (
                          <span className="text-xs text-green-600">Resolved {timeAgo(a.resolved_at)}</span>
                        ) : (
                          <span className="text-xs text-amber-600 font-medium">Open</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {!a.resolved_at && (
                          <button
                            onClick={() => resolve(a.id)}
                            disabled={resolving === a.id}
                            className="text-xs text-stone-500 hover:text-stone-800 border border-stone-200 hover:border-stone-300 rounded-md px-2.5 py-1 transition-colors disabled:opacity-40"
                          >
                            {resolving === a.id ? "Resolving…" : "Resolve"}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {hasMore && (
              <div className="px-4 py-3 border-t border-stone-100">
                <button
                  onClick={loadMore}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  Load more
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  )
}
