"use client"

import { useEffect, useState } from "react"
import { RefreshCw } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

type Total = { value: number | null; status: "complete" | "partial" | "unavailable" }
export type SessionSpendEvidence = {
  link_status: "session_id_linked" | "unlinked"
  reported: { snapshot_count: number; truncated: boolean; estimated_microdollars: number | null;
    cost_status: "estimated" | "partial" | "unpriced"; unpriced_snapshot_count: number }
  gateway: { request_count: number; receipt_count: number; truncated: boolean;
    calculated_cost_microdollars: Total }
}

function dollars(value: number | null) {
  return value === null ? "Unavailable" : `$${(value / 1_000_000).toFixed(6)}`
}

export function SessionSpendSummary({ data }: { data: SessionSpendEvidence }) {
  return <div style={{ marginTop: 8, overflowWrap: "anywhere" }}>
    <strong>Session spend</strong>
    <div>Reported estimate: {dollars(data.reported.estimated_microdollars)} ({data.reported.cost_status})</div>
    <div>Gateway recorded cost: {dollars(data.gateway.calculated_cost_microdollars.value)} ({data.gateway.calculated_cost_microdollars.status})</div>
    <div>{data.reported.snapshot_count} snapshots · {data.gateway.request_count} Gateway requests · {data.gateway.receipt_count} attempts</div>
    <div>{data.link_status === "session_id_linked" ? "Session ID linked · Token overlap unverified" : "No linked Gateway receipts"}</div>
    <div>Combined total unavailable · Reported estimates excluded from budgets</div>
    {data.reported.unpriced_snapshot_count > 0 && <div>{data.reported.unpriced_snapshot_count} unpriced snapshots</div>}
    {(data.reported.truncated || data.gateway.truncated) && <div role="status">Partial session: evidence limit reached</div>}
  </div>
}

export function SessionSpend({ eventId }: { eventId: string }) {
  const { authFetch, workspaceId } = useAuthFetch()
  const [data, setData] = useState<SessionSpendEvidence | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let cancelled = false
    setData(null); setError("")
    if (!workspaceId) return
    setBusy(true)
    void (async () => {
      try {
        const response = await authFetch(`${API}/guard/events/session-usage/${encodeURIComponent(eventId)}/reconciliation?workspace_id=${encodeURIComponent(workspaceId)}`)
        if (!response.ok) throw new Error("Session spend unavailable")
        const body = await response.json()
        if (!cancelled) setData(body)
      } catch { if (!cancelled) setError("Session spend unavailable") }
      finally { if (!cancelled) setBusy(false) }
    })()
    return () => { cancelled = true }
  }, [authFetch, eventId, workspaceId, refresh])
  return <div style={{ gridColumn: "1 / -1", minWidth: 0 }}>
    {busy && <div role="status">Loading session spend...</div>}
    {error && <div role="alert">{error}</div>}
    {data && <SessionSpendSummary data={data} />}
    <button type="button" className="btn btn-ghost btn-sm btn-icon" title="Refresh session spend"
      aria-label="Refresh session spend" disabled={busy || !workspaceId} onClick={() => setRefresh(n => n + 1)}>
      <RefreshCw size={16} />
    </button>
  </div>
}
