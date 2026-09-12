// Shared badge component for Guard event surfaces.
//
// One rendering rule for every colored pill in the Guard IA:
// severity, decision, status, source. Keeps color language consistent
// so users learn "critical is always red, allowed is always green,
// open is always warn-toned" no matter which page they land on.
//
// Extend by adding a new variant kind + palette entry — don't inline
// styled pills in pages.

import type { CSSProperties } from "react"

type Kind = "severity" | "decision" | "status" | "source"
type Tone = "critical" | "warn" | "ok" | "info" | "plain"

const TONE_STYLES: Record<Tone, CSSProperties> = {
  critical: { background: "var(--err-bg)",  color: "var(--err)"  },
  warn:     { background: "var(--warn-bg)", color: "var(--warn)" },
  ok:       { background: "var(--ok-bg)",   color: "var(--ok)"   },
  info:     { background: "var(--info-bg)", color: "var(--info)" },
  plain:    { background: "var(--surface)", color: "var(--text-muted)" },
}

function toneFor(kind: Kind, value: string): Tone {
  const v = value.toLowerCase()
  if (kind === "severity") {
    if (v === "critical" || v === "high") return "critical"
    if (v === "medium") return "warn"
    if (v === "low") return "info"
    return "plain"
  }
  if (kind === "decision") {
    if (v === "blocked") return "critical"
    if (v === "warned") return "warn"
    if (v === "allowed" || v === "approved") return "ok"
    return "plain"
  }
  if (kind === "status") {
    if (v === "open" || v === "pending") return "warn"
    if (v === "triaging") return "info"
    if (v === "resolved" || v === "approved") return "ok"
    if (v === "rejected") return "critical"
    return "plain"
  }
  // source — all neutral by design; the color language is reserved for
  // the "does this need my attention" axis (severity + decision).
  return "plain"
}

export function GuardBadge({
  kind,
  value,
  label,
}: {
  kind: Kind
  value: string
  label?: string
}) {
  const tone = toneFor(kind, value)
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        fontSize: 11,
        fontWeight: 600,
        borderRadius: 4,
        textAlign: "center",
        letterSpacing: 0.2,
        ...TONE_STYLES[tone],
      }}
    >
      {label ?? value}
    </span>
  )
}
