"use client"
import React from "react"
import { SKILL_LABELS } from "@/components/glens/glensConstants"
import { renderMd } from "@/components/glens/glensMarkdown"

/**
 * Shared assistant bubble for both Lens surfaces.
 *
 * - Full-page canvas (`GLensChatPage`) uses defaults: skill label, `maxWidth: 75%`,
 *   14px, followup chips row.
 * - Docked side panel (`LensPanel`) passes `dense`: no skill label, `maxWidth: 92%`,
 *   13px, tighter padding. Streaming state adds a blinking cursor; error tone
 *   flips to red styling. Docked passes its own `footer` (e.g. "Open in Lens →").
 *
 * All markdown flows through `renderMd` — one parser, identical output on both
 * surfaces.
 */
export function AnswerBubble({
  text,
  skill,
  drilldown,
  followups,
  onFollowup,
  understoodAs,
  streaming = false,
  dense = false,
  tone,
  footer,
}: {
  text: string
  skill?: string
  drilldown?: { path: string }
  followups?: string[]
  onFollowup?: (q: string) => void
  understoodAs?: string
  streaming?: boolean
  dense?: boolean
  tone?: "error"
  footer?: React.ReactNode
}) {
  const isError = tone === "error"
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: dense ? 10 : 16 }}>
      <div style={{ maxWidth: dense ? "92%" : "75%" }}>
        {!dense && (skill || understoodAs) && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            {skill && (
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>
                {SKILL_LABELS[skill] ?? skill}
              </div>
            )}
            {understoodAs && (
              <div style={{ fontSize: 10, color: "var(--text-muted)", fontStyle: "italic" }}>
                · {understoodAs}
              </div>
            )}
          </div>
        )}
        <div style={{
          background: isError ? "rgba(239,68,68,.08)" : "var(--surface-2)",
          border: `1px solid ${isError ? "rgba(239,68,68,.35)" : "var(--border)"}`,
          borderRadius: "4px 14px 14px 14px",
          padding: dense ? "8px 12px" : "10px 16px",
          fontSize: dense ? 13 : 14,
          color: isError ? "#ef4444" : "var(--text)",
          lineHeight: dense ? 1.5 : 1.6,
        }}>
          <div>{renderMd(text)}</div>
          {streaming && <span style={{ opacity: .5 }}>▍</span>}
          {drilldown && !streaming && (
            <div style={{ marginTop: 8, textAlign: "right" }}>
              <a href={drilldown.path} style={{ fontSize: 12, color: "var(--accent, #6366f1)", textDecoration: "none", fontWeight: 500 }}>
                View full &rarr;
              </a>
            </div>
          )}
        </div>
        {followups && followups.length > 0 && onFollowup && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {followups.map(q => (
              <button
                key={q}
                onClick={() => onFollowup(q)}
                style={{
                  fontSize: 12, padding: "5px 12px", borderRadius: 16,
                  border: "1px solid var(--border)", background: "var(--surface-2)",
                  color: "var(--text-2)", cursor: "pointer",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        )}
        {footer}
      </div>
    </div>
  )
}
