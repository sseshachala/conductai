"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"
import { buildWorkspaceHeaders } from "@/lib/workspaceHeaders"

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

const SEVERITY_FILTER = [
  { value: "", label: "All severities" },
  { value: "error", label: "Error" },
  { value: "warning", label: "Warning" },
  { value: "info", label: "Info" },
] as const

export default function AlertsPage() {
  const { getToken } = useAuth()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMore, setHasMore] = useState(false)
  const offsetRef = useRef(0)
  const [eventType, setEventType] = useState("")
  const [severity, setSeverity] = useState("")
  const [resolving, setResolving] = useState<Set<string>>(new Set())
  const [resolvingAll, setResolvingAll] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resolveError, setResolveError] = useState<string | null>(null)

  const load = useCallback(async (off: number, type: string, sev: string, replace: boolean) => {
    const token = await getToken()
    const headers = buildWorkspaceHeaders(token)
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(off) })
    if (type) params.set("event_type", type)
    if (sev) params.set("severity", sev)

    try {
      const res = await fetch(`${base}/observability/alerts?${params}`, { headers })
      if (!res.ok) { setError(`Failed to load alerts (${res.status})`); return }
      const data: Alert[] = await res.json()
      setAlerts(prev => replace ? data : [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
      setError(null)
    } catch {
      setError("Network error loading alerts.")
    } finally {
      setLoading(false)
    }
  }, [getToken])

  useEffect(() => {
    setLoading(true)
    offsetRef.current = 0
    load(0, eventType, severity, true)
  }, [eventType, severity, load])

  async function resolve(id: string) {
    setResolving(prev => new Set(prev).add(id))
    setResolveError(null)
    const token = await getToken()
    const headers = buildWorkspaceHeaders(token)
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    try {
      const res = await fetch(`${base}/observability/alerts/${id}/resolve`, { method: "POST", headers })
      if (res.ok) {
        const updated: Alert = await res.json()
        setAlerts(prev => prev.map(a => a.id === id ? updated : a))
      } else {
        setResolveError(`Failed to resolve alert (${res.status})`)
      }
    } catch {
      setResolveError("Network error — could not resolve alert.")
    } finally {
      setResolving(prev => { const next = new Set(prev); next.delete(id); return next })
    }
  }

  async function resolveAll() {
    const open = alerts.filter(a => !a.resolved_at)
    if (!open.length) return
    if (!window.confirm(`Resolve all ${open.length} open alerts?`)) return
    setResolvingAll(true)
    setResolveError(null)
    const token = await getToken()
    const headers = buildWorkspaceHeaders(token)
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    try {
      const results = await Promise.allSettled(
        open.map(a => fetch(`${base}/observability/alerts/${a.id}/resolve`, { method: "POST", headers })
          .then(r => r.ok ? r.json() as Promise<Alert> : Promise.reject(r.status))
        )
      )
      const resolved = results
        .filter((r): r is PromiseFulfilledResult<Alert> => r.status === "fulfilled")
        .map(r => r.value)
      const failed = results.filter(r => r.status === "rejected").length
      if (resolved.length) {
        const resolvedIds = new Set(resolved.map(a => a.id))
        setAlerts(prev => prev.map(a => resolvedIds.has(a.id) ? resolved.find(r => r.id === a.id)! : a))
      }
      if (failed) setResolveError(`${failed} alert(s) failed to resolve.`)
    } finally {
      setResolvingAll(false)
    }
  }

  function loadMore() {
    const next = offsetRef.current + PAGE_SIZE
    offsetRef.current = next
    load(next, eventType, severity, false)
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 24 }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
              <Link href="/observability" className="breadcrumb-link">Observability</Link>
              <span>/</span>
              <span style={{ color: "var(--text-2)" }}>Alert History</span>
            </div>
            <h1 className="page-title">Alert History</h1>
            <p className="page-sub" style={{ marginTop: 2 }}>Watchdog events from the last 30 days</p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select
              aria-label="Filter by severity"
              value={severity}
              onChange={e => setSeverity(e.target.value)}
              style={{ fontSize: 13, border: "1px solid var(--border)", borderRadius: 8, padding: "6px 12px", background: "var(--surface)", color: "var(--text-2)", outline: "none" }}
            >
              {SEVERITY_FILTER.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            <select
              aria-label="Filter by event type"
              value={eventType}
              onChange={e => setEventType(e.target.value)}
              style={{ fontSize: 13, border: "1px solid var(--border)", borderRadius: 8, padding: "6px 12px", background: "var(--surface)", color: "var(--text-2)", outline: "none" }}
            >
              {EVENT_TYPES_FILTER.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            {alerts.some(a => !a.resolved_at) && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={resolveAll}
                disabled={resolvingAll}
                style={{ opacity: resolvingAll ? 0.5 : 1 }}
              >
                {resolvingAll ? "Resolving…" : "Resolve all"}
              </button>
            )}
          </div>
        </div>

        {/* Error banners */}
        {error && (
          <div style={{ borderRadius: 10, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)" }}>
            {error}
          </div>
        )}
        {resolveError && (
          <div style={{ borderRadius: 10, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>{resolveError}</span>
            <button onClick={() => setResolveError(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--err)", fontSize: 14, padding: 0 }}>✕</button>
          </div>
        )}

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
        ) : error && alerts.length === 0 ? null : alerts.length === 0 ? (
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
                      scope="col"
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
                        title={detail || undefined}
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
                          <span title={new Date(a.resolved_at).toLocaleString()} style={{ fontSize: 12, color: "var(--ok)" }}>
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
                            disabled={resolving.has(a.id) || resolvingAll}
                            style={{ opacity: resolving.has(a.id) || resolvingAll ? 0.4 : 1 }}
                          >
                            {resolving.has(a.id) ? "Resolving…" : "Resolve"}
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
                <button className="btn btn-ghost btn-sm" onClick={loadMore}>
                  Load more ({PAGE_SIZE} more)
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  )
}
