"use client"

// Shared rendering component for the "By AI tool" table on both /guard
// Overview and /guard/spend. Aggregation stays in the consumer (since
// the two pages have different time-window semantics — /spend uses
// month, Overview uses since/today/7d/30d). Consumers normalize their
// rows into ByAiToolRow and pass them in.

export interface ByAiToolRow {
  tool: string
  tokens: number
  costLabel: string
  saved: number
  savedCostLabel?: string
  pct: number
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return String(n)
}

export function ByAiToolTable({ rows }: { rows: ByAiToolRow[] }) {
  if (rows.length === 0) return null
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "15px 20px 13px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14.5 }}>
        By AI tool
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr 1.6fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
        {["Tool", "Tokens used", "Est. cost", "Saved", "% of total"].map((h, i) => (
          <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
        ))}
      </div>
      {rows.map(r => (
        <div
          key={r.tool}
          style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr 1.6fr", gap: 14, padding: "13px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}
        >
          <div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{r.tool}</div>
          <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>{fmtTokens(r.tokens)}</div>
          <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>{r.costLabel}</div>
          <div className="mono" style={{ fontSize: 13, color: "#16a34a" }}>
            {r.saved > 0 ? fmtTokens(r.saved) : "—"}
            {r.savedCostLabel && (
              <span style={{ color: "var(--text-3)", marginLeft: 6, fontSize: 11 }}>({r.savedCostLabel})</span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <div style={{ flex: 1, height: 8, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
              <div style={{ width: `${r.pct}%`, height: "100%", background: "var(--accent)", borderRadius: 6 }} />
            </div>
            <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", width: 34, textAlign: "right" }}>{r.pct}%</span>
          </div>
        </div>
      ))}
    </div>
  )
}
