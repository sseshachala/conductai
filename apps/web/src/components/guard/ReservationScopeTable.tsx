"use client"

import { useEffect, useState } from "react"
import { reservations, type ReservationScope } from "@/lib/api/guard"
import { useAuthFetch } from "@/hooks/useAuthFetch"

/**
 * PR-B: per-scope reservation table shown in the block-detail drawer.
 *
 * Renders one row per budget scope the request tried to reserve against.
 * Columns: scope label (workspace / agent / transport / client tool /
 * user), reserved amount, settled amount, status. Status maps directly
 * to the ledger's outcome:
 *
 *   open       -> reservation still holding capacity (dispatched, unknown outcome)
 *   released   -> caller confirmed no wire bytes fired, refunded
 *   committed  -> success path, actual cost written
 *
 * If ``request_id`` is null (pre-PR-A2b row or feature flag off) OR the
 * server returns an empty list, the component renders nothing so the
 * drawer stays clean.
 */
export function ReservationScopeTable({ requestId }: { requestId: string }) {
  const { authFetch } = useAuthFetch()
  const [rows, setRows] = useState<ReservationScope[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    reservations
      .forRequest(authFetch, requestId)
      .then((result) => {
        if (!cancelled) setRows(result)
      })
      .catch((e: unknown) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "load failed")
      })
    return () => {
      cancelled = true
    }
  }, [authFetch, requestId])

  if (err) {
    return (
      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 12 }}>
        Reservation detail unavailable ({err}).
      </div>
    )
  }
  if (rows == null) return null // still loading — silent
  if (rows.length === 0) return null // no reservations happened for this request

  return (
    <div style={{ marginTop: 16 }}>
      <div
        style={{
          fontSize: 11,
          textTransform: "uppercase",
          letterSpacing: 0.6,
          color: "var(--muted)",
          marginBottom: 6,
        }}
      >
        Budget reservation
      </div>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 12,
        }}
      >
        <thead>
          <tr style={{ textAlign: "left", color: "var(--muted)" }}>
            <th style={{ padding: "4px 8px", borderBottom: "1px solid var(--border)" }}>Scope</th>
            <th style={{ padding: "4px 8px", borderBottom: "1px solid var(--border)" }}>Reserved</th>
            <th style={{ padding: "4px 8px", borderBottom: "1px solid var(--border)" }}>Settled</th>
            <th style={{ padding: "4px 8px", borderBottom: "1px solid var(--border)" }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.reservation_id}>
              <td style={{ padding: "4px 8px", fontFamily: "var(--mono, monospace)" }}>
                {formatScope(r)}
              </td>
              <td style={{ padding: "4px 8px" }}>${formatCents(r.estimated_cents)}</td>
              <td style={{ padding: "4px 8px" }}>
                {r.actual_cents != null ? `$${formatCents(r.actual_cents)}` : "—"}
              </td>
              <td style={{ padding: "4px 8px" }}>
                <StatusPill status={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatScope(r: ReservationScope): string {
  const parts: string[] = []
  if (r.source) parts.push(`transport:${r.source}`)
  if (r.client_tool) parts.push(`tool:${r.client_tool}`)
  if (r.agent_identity_id) parts.push(`agent:${r.agent_identity_id.slice(0, 12)}`)
  if (r.clerk_user_id) parts.push(`user:${r.clerk_user_id.slice(0, 12)}`)
  if (r.ai_tool && r.ai_tool !== "_all") parts.push(`cap:${r.ai_tool}`)
  return parts.length ? parts.join(" · ") : "workspace"
}

function formatCents(cents: number): string {
  const dollars = cents / 100
  return dollars.toFixed(2)
}

function StatusPill({ status }: { status: string }) {
  const styleFor: Record<string, { bg: string; fg: string; label: string }> = {
    open: { bg: "#fef3c7", fg: "#92400e", label: "held" },
    released: { bg: "#e0e7ff", fg: "#3730a3", label: "released" },
    committed: { bg: "#d1fae5", fg: "#065f46", label: "committed" },
  }
  const s = styleFor[status] ?? { bg: "#e5e7eb", fg: "#374151", label: status }
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 0.4,
        padding: "1px 6px",
        borderRadius: 3,
        background: s.bg,
        color: s.fg,
        textTransform: "uppercase",
      }}
    >
      {s.label}
    </span>
  )
}
