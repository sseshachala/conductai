"use client"

import type { RunMeta } from "@/components/runs/RunDetailPanel"

export interface RunCostTabProps {
  run: RunMeta
}

export default function RunCostTab({ run }: RunCostTabProps) {
  const state = (run.state ?? {}) as Record<string, unknown>
  const blocks = Object.entries(state).filter(([k]) => !k.startsWith("__") && !k.startsWith("_"))
  let totalInput = 0, totalOutput = 0, totalCost = 0
  const rows: { block: string; label: string; input: number; output: number; cost: number; turns: number }[] = []
  for (const [blockId, val] of blocks) {
    const v = val as Record<string, unknown>
    const input  = (v?.input_tokens  as number) || 0
    const output = (v?.output_tokens as number) || 0
    const cost   = (v?.cost_usd      as number) || 0
    const turns  = (v?.turns         as number) || 0
    const label  = (v?.label ?? v?.name ?? blockId) as string
    if (input || output || cost) {
      rows.push({ block: blockId, label, input, output, cost, turns })
      totalInput  += input
      totalOutput += output
      totalCost   += cost
    }
  }

  if (rows.length === 0) return (
    <div style={{ textAlign: "center", padding: "48px 0" }}>
      <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>No cost data yet</p>
      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Token usage is recorded once the run completes.</p>
    </div>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Totals grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {[
          { label: "Total cost",    value: `$${totalCost.toFixed(2)}`,  color: "var(--text)"        },
          { label: "Input tokens",  value: totalInput.toLocaleString(), color: "var(--info)"        },
          { label: "Output tokens", value: totalOutput.toLocaleString(),color: "var(--accent-text)" },
        ].map(({ label, value, color }) => (
          <div key={label} className="card" style={{ padding: "14px 18px" }}>
            <p className="eyebrow" style={{ marginBottom: 8 }}>{label}</p>
            <p style={{ fontSize: 26, fontWeight: 700, color, letterSpacing: "-.01em" }}>{value}</p>
          </div>
        ))}
      </div>
      {/* Per-block breakdown */}
      <div>
        <p className="eyebrow" style={{ marginBottom: 8 }}>Per block</p>
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 1fr 0.7fr 1fr", padding: "10px 16px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
            {["Block", "Input", "Output", "Turns", "Cost"].map((h, i) => (
              <span key={h} className="eyebrow" style={{ textAlign: i ? "right" : "left" }}>{h}</span>
            ))}
          </div>
          {rows.map((r, i) => (
            <div key={r.block} style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 1fr 0.7fr 1fr", padding: "10px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
              <span style={{ fontSize: 12, color: "var(--text-2)" }}>{r.label}</span>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{r.input.toLocaleString()}</span>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{r.output.toLocaleString()}</span>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{r.turns}</span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", textAlign: "right" }}>${r.cost.toFixed(2)}</span>
            </div>
          ))}
        </div>
        <p style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 8 }}>Pricing: $3/1M input · $15/1M output (claude-sonnet-4-6)</p>
      </div>
    </div>
  )
}
