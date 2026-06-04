"use client"

import { useEffect, useState } from "react"

interface TraceRow {
  id: string
  block_id: string
  turn: number
  role: "user" | "assistant" | "tool_use" | "tool_result"
  content: string | null
  tool_name: string | null
  tool_input: Record<string, unknown> | null
  tool_use_id: string | null
  input_tokens: number | null
  output_tokens: number | null
  created_at: string | null
}

interface Props {
  workflowId: string
  runId: string
  getToken?: (() => Promise<string | null>) | null
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

async function buildHeaders(getToken?: (() => Promise<string | null>) | null): Promise<Record<string, string>> {
  const h: Record<string, string> = {}
  if (getToken) {
    const token = await getToken()
    if (token) h["Authorization"] = `Bearer ${token}`
  }
  const ws = getCookie("delegator_project_id")
  if (ws) h["X-Workspace-Id"] = ws
  return h
}

const ROLE_STYLES: Record<string, { background: string; borderColor: string; label: string; dot: string }> = {
  user:        { background: "var(--blk-trigger-bg, #eff6ff)",   borderColor: "var(--blk-trigger-bd, #bfdbfe)", label: "USER",        dot: "var(--info, #2563eb)"   },
  assistant:   { background: "var(--blk-brain-bg, #f5f3ff)",     borderColor: "var(--blk-brain-bd, #ddd6fe)",   label: "ASSISTANT",   dot: "#7c3aed"                },
  tool_use:    { background: "var(--warn-bg)",                   borderColor: "var(--warn-bd)",                 label: "TOOL CALL",   dot: "var(--warn)"            },
  tool_result: { background: "var(--surface-2)",                 borderColor: "var(--border)",                  label: "RESULT",      dot: "var(--text-muted)"      },
}

function TraceRow({ row }: { row: TraceRow }) {
  const [expanded, setExpanded] = useState(false)
  const style = ROLE_STYLES[row.role] ?? ROLE_STYLES.user
  const hasLongContent = (row.content?.length ?? 0) > 400

  return (
    <div style={{ borderRadius: 8, border: `1px solid ${style.borderColor}`, padding: "10px 13px", background: style.background }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: style.dot, flexShrink: 0 }} />
        <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: ".08em", color: "var(--text-2)", textTransform: "uppercase", whiteSpace: "nowrap" }}>{style.label}</span>
        {row.tool_name && (
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11.5, color: style.dot, fontWeight: 600, whiteSpace: "nowrap" }}>{row.tool_name}</span>
        )}
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono, monospace)", fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap", flexShrink: 0 }}>
          turn {row.turn}{row.input_tokens != null && row.input_tokens > 0 && <>&nbsp;&nbsp;<span style={{ color: "var(--text-3)" }}>{row.input_tokens}↑ {row.output_tokens}↓</span></>}
        </span>
      </div>

      {/* Tool input */}
      {row.role === "tool_use" && row.tool_input && (
        <pre style={{ margin: 0, padding: "9px 11px", background: "var(--surface-3)", borderRadius: 7, fontFamily: "var(--font-mono, monospace)", fontSize: 11.5, overflowX: "auto", lineHeight: 1.5, color: "var(--text-2)" }}>
          {JSON.stringify(row.tool_input, null, 2)}
        </pre>
      )}

      {/* Content */}
      {row.content && (
        <>
          <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5, whiteSpace: "pre-wrap", ...((!expanded && hasLongContent) ? { display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical", overflow: "hidden" } : {}) }}>
            {row.content}
          </div>
          {hasLongContent && (
            <div onClick={() => setExpanded(e => !e)} style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 7, cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
              {expanded ? "▾ collapse" : "▸ expand"}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function ConversationTrace({ workflowId, runId, getToken }: Props) {
  const [rows, setRows] = useState<TraceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const headers = await buildHeaders(getToken)
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}/trace`,
          { headers }
        )
        if (!res.ok) throw new Error(`${res.status}`)
        setRows(await res.json())
      } catch (e) {
        setError(String(e))
      } finally {
        setLoading(false)
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId])

  if (loading) return <p style={{ fontSize: 13, color: "var(--text-muted)", padding: "24px 0", textAlign: "center" }}>Loading trace…</p>
  if (error) return <p style={{ fontSize: 13, color: "var(--err)", padding: "24px 0", textAlign: "center" }}>Failed to load trace: {error}</p>
  if (rows.length === 0) return (
    <p style={{ fontSize: 13, color: "var(--text-muted)", padding: "24px 0", textAlign: "center" }}>
      No trace data — only agentic brain blocks generate traces.
    </p>
  )

  // Group by block_id for section headers
  const blocks: { blockId: string; rows: TraceRow[] }[] = []
  for (const row of rows) {
    const last = blocks[blocks.length - 1]
    if (last?.blockId === row.block_id) {
      last.rows.push(row)
    } else {
      blocks.push({ blockId: row.block_id, rows: [row] })
    }
  }

  const totalInput = rows.reduce((a, r) => a + (r.input_tokens ?? 0), 0)
  const totalOutput = rows.reduce((a, r) => a + (r.output_tokens ?? 0), 0)
  const totalCost = ((totalInput * 3 + totalOutput * 15) / 1_000_000)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Summary */}
      <div style={{ display: "flex", alignItems: "center", gap: 18, paddingBottom: 14, marginBottom: 16, borderBottom: "1px solid var(--border)", fontSize: 13, color: "var(--text-3)" }}>
        <span><b style={{ color: "var(--text)" }}>{rows.length}</b> trace rows</span>
        {totalInput > 0 && <span style={{ fontFamily: "var(--font-mono, monospace)" }}>{(totalInput + totalOutput).toLocaleString()} tokens · ${totalCost.toFixed(4)}</span>}
      </div>

      {blocks.map(({ blockId, rows: blockRows }) => (
        <div key={blockId}>
          <p className="eyebrow mono" style={{ marginBottom: 12 }}>{blockId}</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {blockRows.map(row => <TraceRow key={row.id} row={row} />)}
          </div>
        </div>
      ))}
    </div>
  )
}
