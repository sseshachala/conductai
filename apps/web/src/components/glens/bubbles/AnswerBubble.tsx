"use client"
import { SKILL_LABELS } from "@/components/glens/glensConstants"
import { renderMd } from "@/components/glens/glensMarkdown"

export function AnswerBubble({ text, skill, drilldown, followups, onFollowup, understoodAs }: { text: string; skill?: string; drilldown?: { path: string }; followups?: string[]; onFollowup?: (q: string) => void; understoodAs?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
      <div style={{ maxWidth: "75%" }}>
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
        <div style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: "4px 14px 14px 14px",
          padding: "10px 16px",
          fontSize: 14,
          color: "var(--text)",
          lineHeight: 1.6,
        }}>
          {renderMd(text)}
          {drilldown && (
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
      </div>
    </div>
  )
}
