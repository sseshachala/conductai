import { type BaselinePlaybook, fmt, gradeStyles } from "./helpers"

// ─── Score card ───────────────────────────────────────────────────────────────

export function ScoreCard({
  baseline,
  editionLabel,
  model,
  publishedAt,
}: {
  baseline: BaselinePlaybook
  editionLabel: string
  model: string
  publishedAt: string
}) {
  const s = gradeStyles(baseline.grade)
  const structPct = baseline.total_max > 0 ? (baseline.structural_score / baseline.total_max) * 100 : 0
  const qualPct   = baseline.total_max > 0 ? (baseline.quality_score   / baseline.total_max) * 100 : 0

  return (
    <div className="card" style={{ padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 20 }}>
        {/* Grade */}
        <div style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 64,
          height: 64,
          borderRadius: 12,
          fontSize: 30,
          fontWeight: 900,
          background: s.bg,
          color: s.text,
        }}>
          {baseline.grade}
        </div>

        {/* Score and bars */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 24, fontWeight: 700, color: "var(--text)" }}>
              {baseline.pct.toFixed(0)}%
            </span>
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {baseline.total_score} / {baseline.total_max} pts
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {/* Structural bar */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className="eyebrow" style={{ width: 64, flexShrink: 0, color: "var(--text-muted)" }}>
                Structural
              </span>
              <div style={{
                width: 128,
                height: 6,
                borderRadius: 999,
                background: "var(--surface-3)",
                overflow: "hidden",
              }}>
                <div style={{
                  height: "100%",
                  background: "#60a5fa",
                  borderRadius: 999,
                  transition: "width 0.3s ease",
                  width: `${Math.min(structPct, 100)}%`,
                }} />
              </div>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>
                {baseline.structural_score} pts
              </span>
            </div>

            {/* Quality bar (only if non-zero) */}
            {baseline.quality_score > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className="eyebrow" style={{ width: 64, flexShrink: 0, color: "var(--text-muted)" }}>
                  Quality
                </span>
                <div style={{
                  width: 128,
                  height: 6,
                  borderRadius: 999,
                  background: "var(--surface-3)",
                  overflow: "hidden",
                }}>
                  <div style={{
                    height: "100%",
                    background: "#a78bfa",
                    borderRadius: 999,
                    transition: "width 0.3s ease",
                    width: `${Math.min(qualPct, 100)}%`,
                  }} />
                </div>
                <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>
                  {baseline.quality_score} pts
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Edition meta */}
        <div style={{ flexShrink: 0, textAlign: "right" }}>
          <span style={{
            display: "inline-flex",
            alignItems: "center",
            borderRadius: 999,
            padding: "2px 10px",
            fontSize: 10,
            fontWeight: 600,
            border: `1px solid ${s.border}`,
            background: s.bg,
            color: s.text,
          }}>
            {editionLabel}
          </span>
          <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>{fmt(publishedAt)}</p>
          <p className="mono" style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2, opacity: 0.6 }}>{model}</p>
        </div>
      </div>
    </div>
  )
}
