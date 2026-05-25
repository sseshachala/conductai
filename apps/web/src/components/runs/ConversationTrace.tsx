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

const ROLE_STYLES: Record<string, { bg: string; label: string; dot: string }> = {
  user:        { bg: "bg-blue-50 border-blue-100",   label: "User",        dot: "bg-blue-400"   },
  assistant:   { bg: "bg-purple-50 border-purple-100", label: "Assistant", dot: "bg-purple-400" },
  tool_use:    { bg: "bg-amber-50 border-amber-100",  label: "Tool Call",  dot: "bg-amber-400"  },
  tool_result: { bg: "bg-stone-50 border-stone-200",  label: "Result",     dot: "bg-stone-300"  },
}

function TraceRow({ row }: { row: TraceRow }) {
  const [expanded, setExpanded] = useState(false)
  const style = ROLE_STYLES[row.role] ?? ROLE_STYLES.user
  const hasLongContent = (row.content?.length ?? 0) > 400

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${style.bg}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${style.dot}`} />
        <span className="font-semibold text-stone-600 uppercase tracking-wider text-[9px]">{style.label}</span>
        {row.tool_name && (
          <span className="font-mono text-amber-700 text-[10px]">{row.tool_name}</span>
        )}
        <span className="ml-auto text-stone-400 font-mono text-[9px]">turn {row.turn}</span>
        {row.input_tokens != null && row.input_tokens > 0 && (
          <span className="text-stone-400 font-mono text-[9px]">{row.input_tokens}↑ {row.output_tokens}↓</span>
        )}
      </div>

      {/* Tool input */}
      {row.role === "tool_use" && row.tool_input && (
        <pre className="font-mono text-[10px] text-stone-600 bg-white/60 rounded p-1.5 overflow-x-auto whitespace-pre-wrap max-h-40">
          {JSON.stringify(row.tool_input, null, 2)}
        </pre>
      )}

      {/* Content */}
      {row.content && (
        <>
          <p className={`text-stone-700 leading-relaxed whitespace-pre-wrap ${!expanded && hasLongContent ? "line-clamp-4" : ""}`}>
            {row.content}
          </p>
          {hasLongContent && (
            <button
              onClick={() => setExpanded(e => !e)}
              className="mt-1 text-[10px] text-stone-400 hover:text-stone-600"
            >
              {expanded ? "▾ collapse" : "▸ expand"}
            </button>
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

  if (loading) return <p className="text-sm text-stone-400 py-6 text-center">Loading trace…</p>
  if (error) return <p className="text-sm text-red-500 py-6 text-center">Failed to load trace: {error}</p>
  if (rows.length === 0) return (
    <p className="text-sm text-stone-400 py-6 text-center">
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
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex items-center gap-4 text-xs text-stone-500 border-b border-stone-100 pb-3">
        <span>{rows.length} trace rows</span>
        {totalInput > 0 && <span>{(totalInput + totalOutput).toLocaleString()} tokens · ${totalCost.toFixed(4)}</span>}
      </div>

      {blocks.map(({ blockId, rows: blockRows }) => (
        <div key={blockId}>
          <p className="text-[9px] font-bold uppercase tracking-widest text-stone-400 mb-2 font-mono">
            {blockId}
          </p>
          <div className="space-y-1.5">
            {blockRows.map(row => <TraceRow key={row.id} row={row} />)}
          </div>
        </div>
      ))}
    </div>
  )
}
