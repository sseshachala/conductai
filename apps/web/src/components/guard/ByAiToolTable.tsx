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

// Telemetry coverage per tool. "full" = hook-level counts (used/cost/saved).
// "partial" = MCP-routed calls visible but token counts not cleanly exposed.
// "detected" = we know it's installed/active but can't measure per-call.
type Coverage = "full" | "partial" | "detected"

const COVERAGE: Record<string, Coverage> = {
  claude_code:      "full",
  codex:            "full",
  workflow:         "full",
  platform:         "full",
  "conduct-guard":  "full",
  cursor:           "partial",
  claude_desktop:   "partial",
  claude_chat:      "detected",
  claude_ai:        "detected",
  copilot:          "detected",
  github_copilot:   "detected",
  devin:            "detected",
  chatgpt:          "detected",
  openai_chat:      "detected",
}

function coverageOf(tool: string): Coverage {
  return COVERAGE[tool.toLowerCase()] ?? "detected"
}

const COVERAGE_STYLE: Record<Coverage, { label: string; color: string; bg: string; border: string }> = {
  full:     { label: "full",     color: "#15803d", bg: "#dcfce7", border: "#86efac" },
  partial:  { label: "partial",  color: "#92400e", bg: "#fef3c7", border: "#fcd34d" },
  detected: { label: "detected", color: "#57534e", bg: "#f5f5f4", border: "#d6d3d1" },
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return String(n)
}

const GRID = "1.4fr 0.9fr 1fr 1fr 1fr 1.4fr"

export function ByAiToolTable({ rows }: { rows: ByAiToolRow[] }) {
  // Hide rows with no signal — tokens used = 0 AND saved = 0. Otherwise the
  // table fills with measurable-but-quiet tool categories that just confuse.
  const visible = rows.filter(r => r.tokens > 0 || r.saved > 0)
  if (visible.length === 0) return null
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "15px 20px 13px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14.5, display: "flex", alignItems: "center", gap: 10 }}>
        By AI tool
        <span className="mono" style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 500 }}>
          empty tools hidden · hover badge for telemetry coverage
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
        {["Tool", "Coverage", "Tokens used", "Est. cost", "Saved", "% of total"].map((h, i) => (
          <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
        ))}
      </div>
      {visible.map(r => {
        const cov = coverageOf(r.tool)
        const s   = COVERAGE_STYLE[cov]
        return (
          <div
            key={r.tool}
            style={{ display: "grid", gridTemplateColumns: GRID, gap: 14, padding: "13px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}
          >
            <div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{r.tool}</div>
            <div>
              <span
                title={
                  cov === "full"     ? "Full telemetry — token counts and cost captured at the hook level." :
                  cov === "partial"  ? "Partial — tool calls visible via MCP, but token counts not cleanly exposed." :
                                       "Detected — we know it's installed, but per-call telemetry isn't reachable."
                }
                style={{
                  display: "inline-block", fontSize: 11, fontWeight: 600,
                  color: s.color, background: s.bg, border: `1px solid ${s.border}`,
                  padding: "2px 9px", borderRadius: 99, cursor: "help",
                }}
              >
                {s.label}
              </span>
            </div>
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
        )
      })}
    </div>
  )
}
