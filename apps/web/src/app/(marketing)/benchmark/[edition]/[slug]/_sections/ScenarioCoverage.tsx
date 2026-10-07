"use client"

import { useState } from "react"
import { type ScenarioSet } from "./helpers"

// ─── Scenario coverage ────────────────────────────────────────────────────────

export function ScenarioCoverage({ scenarios }: { scenarios: ScenarioSet }) {
  const [expanded, setExpanded] = useState(false)

  function tagStyle(tag: string): React.CSSProperties {
    if (tag === "positive") return {
      background: "var(--ok-bg)",
      color: "var(--ok)",
      borderColor: "#6ee7b7",
    }
    if (tag === "negative") return {
      background: "var(--err-bg)",
      color: "var(--err)",
      borderColor: "#fca5a5",
    }
    return {
      background: "var(--surface-3)",
      color: "var(--text-3)",
      borderColor: "var(--border)",
    }
  }

  return (
    <section>
      <p className="eyebrow" style={{ color: "var(--text-muted)", marginBottom: 12 }}>
        Scenario coverage
      </p>

      <div className="card" style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* Summary row */}
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 24, fontWeight: 900, color: "var(--text)" }}>{scenarios.scenario_count}</p>
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>total</p>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--surface-3)" }} />
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 20, fontWeight: 700, color: "var(--ok)" }}>{scenarios.positive_count}</p>
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>positive</p>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--surface-3)" }} />
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 20, fontWeight: 700, color: "var(--err)" }}>{scenarios.negative_count}</p>
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>negative</p>
          </div>
          {scenarios.description && (
            <>
              <div style={{ width: 1, height: 32, background: "var(--surface-3)" }} />
              <p style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6, flex: 1 }}>
                {scenarios.description}
              </p>
            </>
          )}
        </div>

        {/* Toggle scenario list */}
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
            fontSize: 12,
            color: "var(--text-muted)",
            textAlign: "left",
          }}
        >
          {expanded ? "Hide scenarios" : `Show ${scenarios.scenario_count} scenarios`}
        </button>

        {expanded && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 4 }}>
            {scenarios.scenarios.map((s, i) => (
              <div
                key={s.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  padding: "8px 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--border)",
                }}
              >
                <span className="mono" style={{
                  fontSize: 10,
                  fontWeight: 900,
                  color: "var(--text-muted)",
                  marginTop: 2,
                  width: 16,
                  flexShrink: 0,
                }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{s.label}</p>
                  <p className="mono" style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>{s.id}</p>
                  <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                    expected: <span className="mono">{s.expected_outcome_type}</span>
                  </p>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 2, flexShrink: 0 }}>
                  {s.tags.map(tag => (
                    <span
                      key={tag}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        borderRadius: 999,
                        border: "1px solid",
                        padding: "2px 6px",
                        fontSize: 9,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        ...tagStyle(tag),
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
