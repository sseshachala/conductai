"use client"

import { useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

export type ToolExecution = {
  correlation_id: string
  tool_call_id: string | null
  tool_name: string | null
  execution_status: string | null
  duration_ms: number | null
  correlation_source: "reported" | "resolved"
  ts: string | null
}
export type ToolExecutionsData = {
  correlation_ids: Record<string, string>
  executions: ToolExecution[]
}

export function ToolExecutionsList({ data }: { data: ToolExecutionsData }) {
  if (data.executions.length === 0) {
    return <div style={{ color: "var(--text-muted)" }}>No execution outcomes reported yet</div>
  }
  return <table style={{ width: "100%", marginTop: 4 }}>
    <thead><tr><th>Tool</th><th>Correlation</th><th>Outcome</th><th>Duration</th></tr></thead>
    <tbody>
      {data.executions.map(row => <tr key={row.correlation_id}>
        <td>{row.tool_name ?? "Unknown"}</td>
        <td className="mono" title={row.tool_call_id ?? undefined}>{row.correlation_id}</td>
        <td>{row.execution_status ?? "Unknown"}</td>
        <td>{row.duration_ms == null ? "—" : `${row.duration_ms} ms`}</td>
      </tr>)}
    </tbody>
  </table>
}

/** "Tool executions" subsection of a gateway audit row: execution outcomes joined by correlation id (#2169). */
export function ToolExecutions({ eventId }: { eventId: string }) {
  const { authFetch, workspaceId } = useAuthFetch()
  const [data, setData] = useState<ToolExecutionsData | null>(null)
  const [error, setError] = useState("")
  useEffect(() => {
    let cancelled = false
    setData(null); setError("")
    if (!workspaceId) return
    void (async () => {
      try {
        const response = await authFetch(`${API}/guard/events/${encodeURIComponent(eventId)}/tool-executions?workspace_id=${encodeURIComponent(workspaceId)}`)
        if (!response.ok) throw new Error("Tool executions unavailable")
        const body = await response.json()
        if (!cancelled) setData(body)
      } catch { if (!cancelled) setError("Tool executions unavailable") }
    })()
    return () => { cancelled = true }
  }, [authFetch, eventId, workspaceId])
  return <div style={{ gridColumn: "1 / -1", minWidth: 0, overflowWrap: "anywhere" }}>
    <strong>Tool executions</strong>
    {error && <div role="alert">{error}</div>}
    {!error && !data && <div role="status">Loading tool executions...</div>}
    {data && <ToolExecutionsList data={data} />}
  </div>
}
