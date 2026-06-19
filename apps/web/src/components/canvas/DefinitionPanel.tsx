"use client"

import type { Node, Edge } from "@xyflow/react"

interface Props {
  nodes: Node[]
  edges: Edge[]
  workflowName: string
  getToken: (() => Promise<string | null>) | null | undefined
  workflowId: string
}

export default function DefinitionPanel({ nodes, workflowName }: Props) {
  return (
    <div className="flex-1 overflow-auto bg-white">
      <div style={{ maxWidth: 640, margin: "0 auto", padding: "40px 24px" }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>{workflowName}</h2>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 32 }}>
          What this agent does, step by step.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {nodes
            .slice()
            .sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0))
            .map((node, i) => {
              const d = node.data as Record<string, unknown>
              const type = d.type as string
              const label = d.label as string || `Step ${i + 1}`
              const typeLabel: Record<string, string> = {
                trigger: "Trigger",
                brain: "AI step",
                tool: "Action",
                memory: "Memory",
                output: "Notify",
                logic: "Condition",
                approval: "Approval",
                for_each: "Loop",
                mcp: "MCP tool",
                sandbox: "Sandbox",
                cleanup: "Cleanup",
              }
              const typeColors: Record<string, string> = {
                trigger: "#3b82f6",
                brain: "#8b5cf6",
                tool: "#10b981",
                memory: "#f59e0b",
                output: "#f43f5e",
                logic: "#78716c",
                approval: "#f97316",
                for_each: "#14b8a6",
                mcp: "#06b6d4",
                sandbox: "#22c55e",
                cleanup: "#0ea5e9",
              }
              const color = typeColors[type] || "#78716c"

              return (
                <div key={node.id} style={{
                  display: "flex", alignItems: "flex-start", gap: 12,
                  padding: "12px 16px", borderRadius: 10,
                  border: "1px solid var(--border)", background: "var(--surface)",
                }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: "50%",
                    background: color, marginTop: 6, flexShrink: 0,
                  }} />
                  <div>
                    <p style={{ fontSize: 11, fontWeight: 600, color, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 2 }}>
                      {typeLabel[type] || type}
                    </p>
                    <p style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>{label}</p>
                    {(d.custom_instructions as string) && (
                      <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                        {(d.custom_instructions as string).slice(0, 120)}{(d.custom_instructions as string).length > 120 ? "\u2026" : ""}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
        </div>

        {nodes.length === 0 && (
          <p style={{ fontSize: 14, color: "var(--text-muted)", textAlign: "center", marginTop: 80 }}>
            No blocks yet — add blocks on the Canvas tab to see the definition here.
          </p>
        )}
      </div>
    </div>
  )
}
