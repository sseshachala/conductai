"use client"

import { useState } from "react"
import type { Node, Edge } from "@xyflow/react"

interface BlockRunData {
  turns?: number
  cost_usd?: number
  model?: string
  input_tokens?: number
  output_tokens?: number
  output?: string
  // tool blocks
  sent?: boolean
  issue_url?: string
  issue_number?: number
  // condition block
  route?: string
  condition?: string
  // memory blocks
  key?: string
  written?: boolean
  count?: number
  entries?: unknown[]
  // error
  error?: string
  [key: string]: unknown
}

interface RunSummary {
  status: string
  created_at?: string
  total_cost?: number
  run_id?: string
}

interface Props {
  nodes: Node[]
  edges: Edge[]
  workflowName: string
  getToken: (() => Promise<string | null>) | null | undefined
  workflowId: string
  // optional run data — populated by CanvasEditor when available
  runState?: Record<string, BlockRunData>
  runSummary?: RunSummary
}

const TYPE_LABEL: Record<string, string> = {
  trigger: "Trigger", brain: "AI step", tool: "Action",
  memory: "Memory", output: "Notify", logic: "Condition",
  approval: "Approval", for_each: "Loop", mcp: "MCP tool",
  sandbox: "Sandbox", cleanup: "Cleanup",
}
const TYPE_COLOR: Record<string, string> = {
  trigger: "#3b82f6", brain: "#8b5cf6", tool: "#10b981",
  memory: "#f59e0b", output: "#f43f5e", logic: "#78716c",
  approval: "#f97316", for_each: "#14b8a6", mcp: "#06b6d4",
  sandbox: "#22c55e", cleanup: "#0ea5e9",
}

function statusColor(status: string) {
  if (status === "running") return "#f59e0b"
  if (status === "succeeded") return "#10b981"
  if (status === "failed") return "#ef4444"
  return "#94a3b8"
}

function fmtCost(c?: number) {
  if (!c) return null
  return c < 0.001 ? "<$0.001" : `$${c.toFixed(4)}`
}

function fmtTokens(i?: number, o?: number) {
  if (!i && !o) return null
  return `${(i ?? 0).toLocaleString()} in · ${(o ?? 0).toLocaleString()} out`
}

function blockOutput(type: string, d: BlockRunData): string | null {
  if (d.error) return `Error: ${d.error}`
  if (type === "logic") return d.route ? `Route taken: "${d.route}"` : null
  if (type === "memory") {
    if (d.written) return `Wrote to memory: ${d.key}`
    if (d.count !== undefined) return `Recalled ${d.count} entr${d.count === 1 ? "y" : "ies"} from ${d.key}`
    return null
  }
  if (type === "output") return d.sent ? "Notification sent" : "Notification skipped"
  if (type === "tool") {
    if (d.issue_url) return `Issue #${d.issue_number} created`
    if (d.sent) return "Sent successfully"
    return null
  }
  // brain block — show truncated output
  const out = d.output as string | undefined
  if (!out) return null
  const text = typeof out === "string" ? out : JSON.stringify(out)
  return text.length > 180 ? text.slice(0, 180) + "…" : text
}

function hasRunData(d?: BlockRunData) {
  if (!d) return false
  return d.turns !== undefined || d.sent !== undefined || d.route !== undefined
    || d.written !== undefined || d.count !== undefined || d.issue_url !== undefined
}

export default function DefinitionPanel({ nodes, workflowName, runState, runSummary }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const sorted = nodes
    .slice()
    .sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0))

  const hasRun = !!runSummary
  const isLive = runSummary?.status === "running" || runSummary?.status === "pending"
  const totalCost = hasRun
    ? Object.values(runState ?? {}).reduce((sum, b) => sum + (b.cost_usd ?? 0), 0)
    : 0

  function toggle(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="flex-1 overflow-auto bg-white">
      <div style={{ maxWidth: 640, margin: "0 auto", padding: "40px 24px" }}>

        <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>
          {workflowName}
        </h2>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 24 }}>
          What this agent does, step by step.
        </p>

        {/* Run summary strip */}
        {hasRun && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
            padding: "10px 14px", borderRadius: 10, marginBottom: 20,
            background: isLive ? "#fffbeb" : runSummary.status === "succeeded" ? "#f0fdf4" : "#fef2f2",
            border: `1px solid ${isLive ? "#fde68a" : runSummary.status === "succeeded" ? "#bbf7d0" : "#fecaca"}`,
          }}>
            {/* status dot */}
            <span style={{
              display: "inline-block", width: 7, height: 7, borderRadius: "50%",
              background: statusColor(runSummary.status),
              animation: isLive ? "pulse-def 1.5s ease-in-out infinite" : "none",
            }} />
            <span style={{ fontSize: 12, fontWeight: 600, color: statusColor(runSummary.status), textTransform: "capitalize" }}>
              {isLive ? "Running…" : runSummary.status}
            </span>
            {runSummary.created_at && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {new Date(runSummary.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
            {totalCost > 0 && (
              <span style={{
                marginLeft: "auto", fontSize: 11, fontWeight: 600,
                color: "#6d28d9", background: "#ede9fe",
                padding: "2px 8px", borderRadius: 100,
              }}>
                {fmtCost(totalCost)} total
              </span>
            )}
          </div>
        )}

        <style>{`
          @keyframes pulse-def { 0%,100%{opacity:1} 50%{opacity:0.35} }
          .def-block { transition: box-shadow 0.15s; cursor: default; }
          .def-block:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
          .def-block.has-run { cursor: pointer; }
        `}</style>

        {/* Block list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {sorted.map((node, i) => {
            const d = node.data as Record<string, unknown>
            const type = d.type as string
            const label = (d.label as string) || `Step ${i + 1}`
            const color = TYPE_COLOR[type] || "#78716c"

            // run data — node.id matches the run state key (e.g. "plan", "surface_risks")
            const rd = runState?.[node.id]
            const ran = hasRunData(rd)
            const isOpen = expanded.has(node.id)
            const output = ran && rd ? blockOutput(type, rd) : null

            // status for this block
            const blockStatus = !hasRun ? null
              : ran ? "done"
              : isLive ? null  // not yet reached
              : null

            return (
              <div
                key={node.id}
                className={`def-block${ran ? " has-run" : ""}`}
                onClick={() => ran && toggle(node.id)}
                style={{
                  borderRadius: 10, border: "1px solid var(--border)",
                  background: ran ? "#fafafa" : "var(--surface)",
                  overflow: "hidden",
                  outline: ran && isOpen ? `2px solid ${color}22` : "none",
                }}
              >
                {/* Header row */}
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 14px" }}>
                  {/* color dot / status */}
                  <div style={{ position: "relative", marginTop: 6, flexShrink: 0 }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />
                    {blockStatus === "done" && (
                      <div style={{
                        position: "absolute", top: -3, left: -3,
                        width: 14, height: 14, borderRadius: "50%",
                        background: "#10b98122", border: "1px solid #10b981",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 8, color: "#10b981",
                      }}>✓</div>
                    )}
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 2 }}>
                      {TYPE_LABEL[type] || type}
                    </p>
                    <p style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>{label}</p>

                    {/* static description when no run */}
                    {!ran && (d.custom_instructions as string) && (
                      <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                        {(d.custom_instructions as string).slice(0, 120)}
                        {(d.custom_instructions as string).length > 120 ? "…" : ""}
                      </p>
                    )}

                    {/* run inline summary (collapsed) */}
                    {ran && !isOpen && output && (
                      <p style={{ fontSize: 12, color: "#64748b", marginTop: 4, lineHeight: 1.5 }}>
                        {output.length > 100 ? output.slice(0, 100) + "…" : output}
                      </p>
                    )}
                  </div>

                  {/* right: tokens + cost chip */}
                  {ran && rd && (
                    <div style={{ flexShrink: 0, textAlign: "right", display: "flex", flexDirection: "column", gap: 4 }}>
                      {rd.cost_usd !== undefined && (
                        <span style={{
                          fontSize: 11, fontWeight: 600, color: "#6d28d9",
                          background: "#ede9fe", padding: "2px 7px", borderRadius: 100,
                        }}>
                          {fmtCost(rd.cost_usd)}
                        </span>
                      )}
                      {rd.model && (
                        <span style={{ fontSize: 10, color: "#94a3b8" }}>
                          {rd.model.replace("claude-", "").replace("-latest", "")}
                        </span>
                      )}
                      {ran && (
                        <span style={{ fontSize: 10, color: "#94a3b8" }}>
                          {isOpen ? "▲ collapse" : "▼ expand"}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Expanded run detail */}
                {ran && isOpen && rd && (
                  <div style={{
                    borderTop: "1px solid var(--border)",
                    padding: "12px 14px", background: "#fff",
                    display: "flex", flexDirection: "column", gap: 10,
                  }}>

                    {/* tokens */}
                    {fmtTokens(rd.input_tokens, rd.output_tokens) && (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, color: "#64748b" }}>
                          🔢 {fmtTokens(rd.input_tokens, rd.output_tokens)}
                        </span>
                        {rd.turns !== undefined && (
                          <span style={{ fontSize: 11, color: "#64748b" }}>
                            · {rd.turns} turn{rd.turns !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    )}

                    {/* full output */}
                    {output && (
                      <div style={{
                        fontSize: 12, color: "#374151", lineHeight: 1.65,
                        background: "#f8f7ff", border: "1px solid #ede9fe",
                        borderRadius: 8, padding: "10px 12px",
                        whiteSpace: "pre-wrap", fontFamily: "inherit",
                      }}>
                        {type === "brain"
                          ? (() => {
                              const raw = rd.output as string | undefined
                              return raw ? (raw.length > 600 ? raw.slice(0, 600) + "\n\n…" : raw) : output
                            })()
                          : output}
                      </div>
                    )}

                    {/* structured fields for non-brain blocks */}
                    {type !== "brain" && Object.entries(rd)
                      .filter(([k]) => !["output","cost_usd","model","turns","input_tokens","output_tokens","pricing_rates","pricing_version","routing_reason","provider"].includes(k))
                      .filter(([, v]) => v !== null && v !== undefined && typeof v !== "object")
                      .slice(0, 6)
                      .map(([k, v]) => (
                        <div key={k} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".06em", minWidth: 90, flexShrink: 0 }}>
                            {k.replace(/_/g, " ")}
                          </span>
                          <span style={{ fontSize: 12, color: "#374151" }}>{String(v)}</span>
                        </div>
                      ))
                    }
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {nodes.length === 0 && (
          <p style={{ fontSize: 14, color: "var(--text-muted)", textAlign: "center", marginTop: 80 }}>
            No blocks yet — add blocks on the Canvas tab to see the definition here.
          </p>
        )}

        {/* No run yet nudge */}
        {nodes.length > 0 && !hasRun && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", marginTop: 32 }}>
            Run this agent to see per-block outputs, token usage, and cost here.
          </p>
        )}
      </div>
    </div>
  )
}
