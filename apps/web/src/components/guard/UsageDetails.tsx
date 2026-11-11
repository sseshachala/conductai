"use client"

import { useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { formatCount, formatCostUsd, usageSourceLabel, usageStatusLabel } from "./common/formatTokens"

type Total = { value: number | null; status: "complete" | "partial" | "unavailable" }
export type UsageAttempt = {
  id: string
  attempt_ordinal: number
  provider: string
  model: string
  execution_outcome: string
  usage_completeness: string
  total_input_tokens: number | null
  total_output_tokens: number | null
  calculated_cost_microdollars: number | null
}
export type UsageData = {
  event_id: string
  row: {
    input_tokens: number | null
    output_tokens: number | null
    source: string | null
    status: string | null
    cost_usd: number | null
  }
  attempts: UsageAttempt[]
  totals: {
    input_tokens: Total
    output_tokens: Total
    calculated_cost_microdollars: Total
  } | null
  coverage: { complete: boolean; expected_attempt_count: number | null; missing_attempt_count: number } | null
}

const micro = (v: number | null) => (v == null ? null : v / 1_000_000)
const badge = { marginLeft: 6, fontSize: 11, padding: "1px 6px", borderRadius: 8, border: "1px solid var(--border)", color: "var(--text-muted)" } as const

function TotalCell({ total, cost }: { total: Total; cost?: boolean }) {
  const text = cost ? formatCostUsd(micro(total.value)) : formatCount(total.value)
  return <>
    {text}
    {total.status === "partial" && <span style={badge} title="At least one attempt has unknown usage">partial</span>}
    {total.status === "unavailable" && <span style={badge}>unavailable</span>}
  </>
}

export function UsageDetailsView({ data }: { data: UsageData }) {
  const source = usageSourceLabel(data.row.source)
  const status = usageStatusLabel(data.row.status)
  return <div>
    <div>
      {formatCount(data.row.input_tokens)} in / {formatCount(data.row.output_tokens)} out
      <span style={badge}>{source ?? "Source unknown"}</span>
      {status && <span style={badge}>{status}</span>}
    </div>
    {data.attempts.length > 0 && <table style={{ width: "100%", marginTop: 4 }}>
      <thead><tr><th>#</th><th>Model</th><th>Status</th><th>Input</th><th>Output</th><th>Cost</th></tr></thead>
      <tbody>
        {data.attempts.map(a => <tr key={a.id}>
          <td>{a.attempt_ordinal}</td>
          <td className="mono">{a.provider ? `${a.provider} / ${a.model}` : a.model}</td>
          <td>{a.execution_outcome}{a.usage_completeness !== "complete" ? ` (usage ${a.usage_completeness})` : ""}</td>
          <td>{formatCount(a.total_input_tokens)}</td>
          <td>{formatCount(a.total_output_tokens)}</td>
          <td>{formatCostUsd(micro(a.calculated_cost_microdollars))}</td>
        </tr>)}
      </tbody>
      {data.totals && <tfoot><tr>
        <th colSpan={3} style={{ textAlign: "left" }}>Total</th>
        <td><TotalCell total={data.totals.input_tokens} /></td>
        <td><TotalCell total={data.totals.output_tokens} /></td>
        <td><TotalCell total={data.totals.calculated_cost_microdollars} cost /></td>
      </tr></tfoot>}
    </table>}
    {data.attempts.length === 0 && <div style={{ color: "var(--text-muted)", marginTop: 4 }}>
      No per-attempt receipts{data.row.status === "pending" ? " yet" : ""}
    </div>}
    {data.coverage && data.coverage.missing_attempt_count > 0 && <div style={{ color: "var(--text-muted)", marginTop: 4 }}>
      {data.coverage.missing_attempt_count} expected attempt(s) have no receipt; totals are partial.
    </div>}
  </div>
}

/** "Usage" subsection of a gateway audit row: provenance and per-attempt accounting (#2069). */
export function UsageDetails({ eventId }: { eventId: string }) {
  const { authFetch, workspaceId } = useAuthFetch()
  const [data, setData] = useState<UsageData | null>(null)
  const [error, setError] = useState("")
  useEffect(() => {
    let cancelled = false
    setData(null); setError("")
    if (!workspaceId) return
    void (async () => {
      try {
        const response = await authFetch(`${API}/guard/events/${encodeURIComponent(eventId)}/usage?workspace_id=${encodeURIComponent(workspaceId)}`)
        if (!response.ok) throw new Error("Usage unavailable")
        const body = await response.json()
        if (!cancelled) setData(body)
      } catch { if (!cancelled) setError("Usage unavailable") }
    })()
    return () => { cancelled = true }
  }, [authFetch, eventId, workspaceId])
  return <div style={{ gridColumn: "1 / -1", minWidth: 0, overflowWrap: "anywhere" }}>
    <strong>Usage</strong>
    {error && <div role="alert">{error}</div>}
    {!error && !data && <div role="status">Loading usage...</div>}
    {data && <UsageDetailsView data={data} />}
  </div>
}
