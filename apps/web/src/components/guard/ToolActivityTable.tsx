/**
 * ToolActivityTable — CLI / booster telemetry feed (#718 Phase 1B).
 *
 * Reads from `GET /guard/events/unified?source=tool` and renders a single
 * compact table. Same visual language as the Sessions tab so the activity
 * page reads as one product, not three siloes.
 */
"use client"

import { useAuth } from "@clerk/nextjs"
import { useCallback, useEffect, useState } from "react"

type ToolEvent = {
  event_id:   string
  source:     string
  ts:         string | null
  actor:      string | null
  action:     string         // tool name: 'conduct-cli' | 'agent-booster'
  status:     string         // info | warning | error
  message:    string | null
  session_id: string | null
}

type Props = {
  workspaceId: string | null
}

const STATUS_COLORS: Record<string, string> = {
  error:   "var(--err)",
  warning: "var(--warn)",
  info:    "var(--text-2)",
}

function formatTs(ts: string | null): string {
  if (!ts) return "—"
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    })
  } catch {
    return ts
  }
}

export default function ToolActivityTable({ workspaceId }: Props) {
  const { getToken } = useAuth()
  const [rows, setRows] = useState<ToolEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    setError(null)
    try {
      const token = await getToken()
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (token) headers["Authorization"] = `Bearer ${token}`
      const params = new URLSearchParams({
        workspace_id: workspaceId,
        source: "tool",
        limit: "100",
      })
      const res = await fetch(`${base}/guard/events/unified?${params}`, { headers })
      if (!res.ok) throw new Error("Failed to load tool events")
      const body = await res.json()
      setRows(body.items ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tool events")
    } finally {
      setLoading(false)
    }
  }, [getToken, workspaceId])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  if (error) {
    return (
      <div style={{
        borderRadius: 8, border: "1px solid var(--err-bd)",
        background: "var(--err-bg)", padding: "10px 16px",
        fontSize: 13, color: "var(--err)", marginBottom: 16,
      }}>
        {error}
      </div>
    )
  }

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: "0.9fr 1fr 0.7fr 2.5fr 1fr",
        gap: 12, padding: "10px 18px",
        borderBottom: "1px solid var(--border)", background: "var(--surface-2)",
      }}>
        {["Time", "Tool", "Level", "Message", "Session"].map((h, i) => (
          <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
        ))}
      </div>

      {loading ? (
        [...Array(4)].map((_, i) => (
          <div key={i} style={{
            height: 44, background: "var(--surface-2)", opacity: 0.5,
            borderBottom: "1px solid var(--border)",
          }} />
        ))
      ) : rows.length === 0 ? (
        <div style={{ padding: "32px 18px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          No CLI events yet. They appear here when conduct-cli or agent-booster posts a warning or error.
        </div>
      ) : rows.map((r, i) => (
        <div key={r.event_id} style={{
          display: "grid",
          gridTemplateColumns: "0.9fr 1fr 0.7fr 2.5fr 1fr",
          gap: 12, padding: "11px 18px", alignItems: "center",
          borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none",
        }}>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {formatTs(r.ts)}
          </div>
          <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)" }}>
            {r.action}
          </div>
          <div style={{
            fontSize: 11, fontWeight: 600, textTransform: "uppercase",
            color: STATUS_COLORS[r.status] ?? "var(--text-2)",
          }}>
            {r.status}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {r.message ?? "—"}
          </div>
          <div className="mono" style={{ fontSize: 10.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {r.session_id ?? "—"}
          </div>
        </div>
      ))}

      {!loading && rows.length > 0 && (
        <div style={{
          borderTop: "1px solid var(--border)", padding: "8px 18px",
          fontSize: 12, color: "var(--text-muted)", textAlign: "center",
        }}>
          {rows.length} event{rows.length !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  )
}
