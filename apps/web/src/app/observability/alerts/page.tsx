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
  { value: "queue_backup", label: "Queue backup" },
  { value: "silent_playbook", label: "Silent playbook" },
  { value: "unknown", label: "Unknown" },
] as const

const EVENT_LABELS: Record<string, string> = {
  stale_worker:      "Stale worker",
  approval_timeout:  "Approval timeout",
  repeated_failure:  "Repeated failures",
  credential_expiry: "Credential expired (401)",
  queue_backup:      "Queue backup",
  silent_playbook:   "Silent playbook",
  unknown:           "Unknown",
}

// Maps severity to sbadge class names
function severityClass(severity: string): string {
  if (severity === "error")   return "sbadge err"
  if (severity === "warning") return "sbadge warn"
  return "sbadge ok"
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
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 24 }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
              <Link
                href="/observability"
                style={{ color: "var(--text-muted)", textDecoration: "none" }}
                onMouseEnter={e => (e.currentTarget.style.color = "var(--text-2)")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
              >
                Observability
              </Link>
              <span>/</span>
              <span style={{ color: "var(--text-2)" }}>Alert History</span>
            </div>
            <h1 className="page-title">Alert History</h1>
            <p className="page-sub" style={{ marginTop: 2 }}>Watchdog events from the last 30 days</p>
          </div>
          <select
            value={eventType}
            onChange={e => setEventType(e.target.value)}
            style={{
              fontSize: 13,
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "6px 12px",
              background: "var(--surface)",
              color: "var(--text-2)",
              outline: "none",
            }}
          >
            {EVENT_TYPES_FILTER.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>

        {/* Table */}
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                style={{
                  background: "var(--surface-3)",
                  borderRadius: 12,
                  height: 64,
                  opacity: 0.6,
                }}
              />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <div
            className="card"
            style={{
              padding: "64px 24px",
              textAlign: "center",
            }}
          >
            <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No alerts in the last 30 days</div>
            <Link
              href="/observability"
              style={{ fontSize: 12, color: "var(--accent)", marginTop: 8, display: "inline-block" }}
            >
              Back to Observability
            </Link>
          </div>
        ) : (
          <div className="card" style={{ overflow: "hidden", padding: 0 }}>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Type", "Agent", "Detail", "When", "Status", ""].map((heading, i) => (
                    <th
                      key={i}
                      className="eyebrow"
                      style={{
                        padding: "10px 16px",
                        textAlign: "left",
                        fontWeight: 500,
                        color: "var(--text-muted)",
                      }}
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {alerts.map((a, idx) => {
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
                    : a.event_type === "queue_backup"
                    ? `${a.payload.pending_count ?? "?"} pending runs (threshold: ${a.payload.threshold ?? 10})`
                    : a.event_type === "silent_playbook"
                    ? `No runs in ${a.payload.silent_days ?? 7} days`
                    : ""

                  const isLast = idx === alerts.length - 1

                  return (
                    <tr
                      key={a.id}
                      style={{ borderBottom: isLast ? "none" : "1px solid var(--border)" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "10px 16px" }}>
                        <span className={severityClass(a.severity)}>
                          {label}
                        </span>
                      </td>
                      <td style={{ padding: "10px 16px" }}>
                        {a.workflow_id ? (
                          <Link
                            href={`/workflows/${a.workflow_id}`}
                            style={{ color: "var(--text)", textDecoration: "none", fontWeight: 500 }}
                            onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
                            onMouseLeave={e => (e.currentTarget.style.color = "var(--text)")}
                          >
                            {workflowName}
                          </Link>
                        ) : (
                          <span style={{ color: "var(--text-3)" }}>{workflowName}</span>
                        )}
                      </td>
                      <td
                        style={{
                          padding: "10px 16px",
                          color: "var(--text-3)",
                          fontSize: 12,
                          maxWidth: 280,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {detail}
                      </td>
                      <td style={{ padding: "10px 16px", color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>
                        {timeAgo(a.created_at)}
                      </td>
                      <td style={{ padding: "10px 16px" }}>
                        {a.resolved_at ? (
                          <span style={{ fontSize: 12, color: "var(--ok)" }}>
                            Resolved {timeAgo(a.resolved_at)}
                          </span>
                        ) : (
                          <span style={{ fontSize: 12, color: "var(--warn)", fontWeight: 500 }}>
                            Open
                          </span>
                        )}
                      </td>
                      <td style={{ padding: "10px 16px", textAlign: "right" }}>
                        {!a.resolved_at && (
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => resolve(a.id)}
                            disabled={resolving === a.id}
                            style={{ opacity: resolving === a.id ? 0.4 : 1 }}
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
              <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)" }}>
                <button
                  onClick={loadMore}
                  style={{
                    fontSize: 12,
                    color: "var(--accent)",
                    fontWeight: 500,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = "var(--accent-text)")}
                  onMouseLeave={e => (e.currentTarget.style.color = "var(--accent)")}
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
