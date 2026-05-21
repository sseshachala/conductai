"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

type BlockStatus = "running" | "completed" | "failed" | "skipped"

interface BlockRow {
  blockId: string
  label: string
  type: string
  status: BlockStatus
  output?: string
  error?: string
  costUsd?: number
}

interface RunDrawerProps {
  workflowId: string
  runId: string
  getToken?: (() => Promise<string | null>) | null
  onBlockStatus: (blockId: string, status: BlockStatus) => void
  onClose: () => void
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`))
  return m ? m[1] : null
}

function statusIcon(status: BlockStatus) {
  if (status === "running")   return <span className="inline-block w-3 h-3 rounded-full border-2 border-violet-500 border-t-transparent animate-spin" />
  if (status === "completed") return <span className="text-emerald-500 font-bold text-xs">✓</span>
  if (status === "failed")    return <span className="text-red-500 font-bold text-xs">✗</span>
  if (status === "skipped")   return <span className="text-stone-400 text-xs">—</span>
}

function statusColor(status: BlockStatus) {
  if (status === "running")   return "border-l-violet-400 bg-violet-50/50"
  if (status === "completed") return "border-l-emerald-400 bg-emerald-50/50"
  if (status === "failed")    return "border-l-red-400 bg-red-50/50"
  return "border-l-stone-200 bg-stone-50/50"
}

export default function RunDrawer({ workflowId, runId, getToken, onBlockStatus, onClose }: RunDrawerProps) {
  const [rows, setRows] = useState<BlockRow[]>([])
  const [done, setDone] = useState(false)
  const [runStatus, setRunStatus] = useState<"running" | "succeeded" | "failed">("running")
  const bottomRef = useRef<HTMLDivElement>(null)
  const rowMapRef = useRef<Record<string, BlockRow>>({})

  useEffect(() => {
    let es: EventSource | null = null
    let cancelled = false

    async function connect() {
      const wsId = getCookie("delegator_project_id")
      const params = new URLSearchParams()
      if (wsId) params.set("workspace_id", wsId)

      if (getToken) {
        const token = await getToken()
        if (token) params.set("token", token)
      }

      if (cancelled) return
      const qs = params.toString() ? `?${params.toString()}` : ""
      es = new EventSource(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}/stream${qs}`
      )

      es.onmessage = (e) => {
        if (e.data === "[DONE]") { setDone(true); es?.close(); return }

        let event: { kind: string; block_id?: string; payload: Record<string, unknown> }
        try { event = JSON.parse(e.data) } catch { return }

        const { kind, block_id, payload } = event

        if (kind === "block_started" && block_id) {
          const row: BlockRow = {
            blockId: block_id,
            label: (payload.label as string) || block_id,
            type: (payload.type as string) || "tool",
            status: "running",
          }
          rowMapRef.current[block_id] = row
          setRows(prev => [...prev, row])
          onBlockStatus(block_id, "running")
        }

        if (kind === "block_completed" && block_id && rowMapRef.current[block_id]) {
          const out = payload.output as Record<string, unknown> | undefined
          let outputSnippet = ""
          if (out?.output && typeof out.output === "string") {
            outputSnippet = out.output.slice(0, 120).replace(/\n/g, " ")
          }
          rowMapRef.current[block_id] = {
            ...rowMapRef.current[block_id],
            status: "completed",
            output: outputSnippet,
            costUsd: typeof out?.cost_usd === "number" ? out.cost_usd : undefined,
          }
          setRows(Object.values(rowMapRef.current))
          onBlockStatus(block_id, "completed")
        }

        if (kind === "block_failed" && block_id && rowMapRef.current[block_id]) {
          rowMapRef.current[block_id] = {
            ...rowMapRef.current[block_id],
            status: "failed",
            error: (payload.error as string) || "Unknown error",
          }
          setRows(Object.values(rowMapRef.current))
          onBlockStatus(block_id, "failed")
        }

        if (kind === "block_skipped" && block_id) {
          const row: BlockRow = {
            blockId: block_id,
            label: (payload.label as string) || block_id,
            type: (payload.type as string) || "tool",
            status: "skipped",
          }
          rowMapRef.current[block_id] = row
          setRows(Object.values(rowMapRef.current))
          onBlockStatus(block_id, "skipped")
        }

        if (kind === "run_completed") setRunStatus("succeeded")
        if (kind === "run_failed")    setRunStatus("failed")
      }

      es.onerror = () => { es?.close(); setDone(true) }
    }

    connect()
    return () => { cancelled = true; es?.close() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [rows])

  const statusBanner = done
    ? runStatus === "succeeded"
      ? "bg-emerald-50 border-t border-emerald-200 text-emerald-700"
      : "bg-red-50 border-t border-red-200 text-red-700"
    : "bg-violet-50 border-t border-violet-200 text-violet-700"

  const statusLabel = done
    ? runStatus === "succeeded" ? "Run completed" : "Run failed"
    : "Running…"

  return (
    <div className="absolute bottom-0 left-0 right-0 z-50 flex flex-col rounded-t-xl border border-stone-200 bg-white shadow-2xl"
      style={{ height: "42%" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-stone-100 shrink-0">
        <div className="flex items-center gap-2">
          {!done && <span className="inline-block w-2 h-2 rounded-full bg-violet-500 animate-pulse" />}
          <span className="text-sm font-semibold text-stone-800">{statusLabel}</span>
          <span className="text-xs text-stone-400">{rows.length} block{rows.length !== 1 ? "s" : ""}</span>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={`/workflows/${workflowId}/runs/${runId}`}
            target="_blank"
            className="text-xs text-violet-600 hover:text-violet-800 font-medium"
          >
            Full trace →
          </a>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-700 text-lg leading-none">×</button>
        </div>
      </div>

      {/* Block rows */}
      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1.5">
        {rows.length === 0 && !done && (
          <p className="text-xs text-stone-400 py-4 text-center animate-pulse">Starting run…</p>
        )}
        {rows.map(row => (
          <div key={row.blockId} className={cn(
            "flex items-start gap-2.5 rounded-lg border-l-4 px-3 py-2 text-xs",
            statusColor(row.status)
          )}>
            <span className="mt-0.5 w-4 shrink-0 flex items-center justify-center">
              {statusIcon(row.status)}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-stone-700 truncate">{row.label}</span>
                {row.costUsd !== undefined && (
                  <span className="text-stone-400 shrink-0">${row.costUsd.toFixed(3)}</span>
                )}
              </div>
              {row.output && (
                <p className="text-stone-500 mt-0.5 truncate">{row.output}</p>
              )}
              {row.error && (
                <p className="text-red-600 mt-0.5 truncate">{row.error}</p>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Footer status bar */}
      <div className={cn("px-4 py-1.5 text-xs font-medium shrink-0", statusBanner)}>
        {statusLabel}
        {!done && " — keep this panel open to stream events"}
      </div>
    </div>
  )
}
