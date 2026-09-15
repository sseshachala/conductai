// Durable-audit lifecycle pill — #1959 Phase 3.
//
// Renders a compact status glyph reflecting an audit row's two-phase
// lifecycle_state, or nothing at all for legacy single-phase rows so the
// column stays visually quiet until real durable traffic starts flowing.
//
// State legend:
//   ⏳ in flight    accepted, lease has time left
//   ✓ finalized    UPDATE completed via audit.finalize()
//   ⚠ orphaned     reconciler flagged (Phase 4)
//   ∅ expired      past lease with no finalize
//   —              legacy row, lifecycle_state IS NULL
//
// The component is intentionally styling-only; it doesn't reach into
// filters or DB — the parent decides which rows to render.

"use client"

export type LifecycleState =
  | "accepted"
  | "finalized"
  | "orphaned"
  | "expired"
  | null
  | undefined

interface LifecyclePillProps {
  state: LifecycleState
  // ISO string; when the row is still 'accepted' and this timestamp has
  // passed we render it as `expired` visually so the user sees the drift
  // even before the Phase 4 reconciler updates the column.
  leaseExpiresAt?: string | null
  // #1990 item D — millisecond offset to apply to Date.now() to
  // correct a skewed browser clock. Positive value = browser is
  // ahead of the server. Optional; defaults to 0 so callers that
  // don't wire it in behave exactly as before.
  nowOffsetMs?: number
}

interface Style {
  icon: string
  label: string
  color: string
  bg: string
  border: string
  title: string
}

const STYLES: Record<Exclude<LifecycleState, null | undefined>, Style> = {
  accepted: {
    icon: "⏳",
    label: "In flight",
    color: "#7c3aed",
    bg: "#ede9fe",
    border: "#c4b5fd",
    title: "Accepted for processing; waiting for the response to be finalized.",
  },
  finalized: {
    icon: "✓",
    label: "Finalized",
    color: "#16a34a",
    bg: "#dcfce7",
    border: "#86efac",
    title: "Response received and audit row finalized.",
  },
  orphaned: {
    icon: "⚠",
    label: "Orphaned",
    color: "#c2410c",
    bg: "#ffedd5",
    border: "#fdba74",
    title: "Reconciler flagged this row — accepted but never finalized before its lease expired.",
  },
  expired: {
    icon: "∅",
    label: "Expired",
    color: "var(--text-muted)",
    bg: "var(--surface-2)",
    border: "var(--border)",
    title: "Lease timed out with no finalize; no further action expected.",
  },
}

export function LifecyclePill({ state, leaseExpiresAt, nowOffsetMs = 0 }: LifecyclePillProps) {
  // Legacy single-phase row — render an em dash so the column has content
  // that lines up with siblings without pretending it's a real state.
  if (!state) {
    return (
      <span style={{ fontSize: 11, color: "var(--text-muted)" }} title="Legacy row — no lifecycle recorded">
        —
      </span>
    )
  }

  // Client-side stale detection: if the row still reads 'accepted' but its
  // lease timestamp is in the past, present it as expired. Server catches
  // up on the next reconciler pass; this keeps the UI honest in between.
  // #1990 item D — subtract the drift from Date.now() so a browser whose
  // clock is 60s ahead doesn't flip rows to Expired prematurely.
  const now = Date.now() - nowOffsetMs
  const leaseTs = leaseExpiresAt ? Date.parse(leaseExpiresAt) : NaN
  const effective: keyof typeof STYLES =
    state === "accepted" && !Number.isNaN(leaseTs) && leaseTs < now ? "expired" : state

  const style = STYLES[effective]
  return (
    <span
      role="status"
      aria-label={style.label}
      title={style.title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 10.5,
        fontWeight: 600,
        padding: "2px 6px",
        borderRadius: 3,
        color: style.color,
        background: style.bg,
        border: `1px solid ${style.border}`,
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden style={{ fontSize: 11 }}>{style.icon}</span>
      {style.label}
    </span>
  )
}
