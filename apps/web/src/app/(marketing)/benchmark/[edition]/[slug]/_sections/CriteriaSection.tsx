"use client"

import { useState } from "react"
import { type CriterionResult, type PlaybookLiveDetail } from "./helpers"

// ─── Criteria breakdown ───────────────────────────────────────────────────────

function CriterionRow({ c }: { c: CriterionResult }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ borderBottom: "1px solid var(--border)" }}>
      <button
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
          transition: "background 0.15s",
        }}
        onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
        onMouseLeave={e => (e.currentTarget.style.background = "none")}
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        <span style={{
          flexShrink: 0,
          width: 20,
          height: 20,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 10,
          fontWeight: 700,
          background: c.passed ? "var(--ok-bg)" : "var(--err-bg)",
          color: c.passed ? "var(--ok)" : "var(--err)",
        }}>
          {c.passed ? "✓" : "✗"}
        </span>
        <span className="mono" style={{ flex: 1, fontSize: 12, color: "var(--text-2)" }}>{c.name}</span>
        <span style={{
          fontSize: 12,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 500,
          color: c.passed ? "var(--ok)" : "var(--err)",
        }}>
          {c.points_earned} / {c.points_possible}
        </span>
        {c.detail && (
          <span style={{
            color: "var(--text-muted)",
            fontSize: 12,
            marginLeft: 4,
            display: "inline-block",
            transition: "transform 0.15s",
            transform: open ? "rotate(90deg)" : "none",
          }}>›</span>
        )}
      </button>

      {open && c.detail && (
        <div style={{ padding: "0 16px 12px", marginLeft: 32 }}>
          <p style={{
            fontSize: 12,
            color: "var(--text-3)",
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
          }}>{c.detail}</p>
        </div>
      )}
    </div>
  )
}

export function CriteriaSection({ live }: { live: PlaybookLiveDetail }) {
  const passing = live.criteria.filter(c => c.passed).length
  const failing  = live.criteria.filter(c => !c.passed).length

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p className="eyebrow" style={{ color: "var(--text-muted)" }}>
          Criteria breakdown
          <span style={{ marginLeft: 8, textTransform: "none", fontWeight: 400, color: "var(--text-muted)", opacity: 0.6 }}>
            (current)
          </span>
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {passing > 0 && (
            <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 500 }}>{passing} passing</span>
          )}
          {failing > 0 && (
            <span style={{ fontSize: 12, color: "var(--err)", fontWeight: 500 }}>{failing} failing</span>
          )}
        </div>
      </div>

      <div className="card" style={{ overflow: "hidden", padding: 0 }}>
        {live.criteria.length === 0 ? (
          <div style={{ padding: "32px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No criteria available for this playbook yet.
          </div>
        ) : (
          live.criteria.map((c, i) => <CriterionRow key={`${c.name}-${i}`} c={c} />)
        )}
      </div>

      <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 8, textAlign: "right", opacity: 0.7 }}>
        Criteria reflect the latest published quality data, not necessarily the frozen edition score.
      </p>
    </section>
  )
}
