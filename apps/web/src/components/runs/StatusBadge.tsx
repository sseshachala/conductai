// Shared StatusBadge component — single source of truth for all run status display.
// Used by /runs and /workflows/[id]/runs pages.

type BadgeVariant = "ok" | "run" | "wait" | "cancelled" | "skipped" | "idle" | "err"

interface BadgeConfig {
  bg: string
  color: string
  border: string
  label: string
  pulse: boolean
}

const BADGE_MAP: Record<BadgeVariant, BadgeConfig> = {
  ok:        { bg: "var(--ok-bg)",       color: "var(--ok)",      border: "var(--ok)",      label: "Done",      pulse: false },
  run:       { bg: "var(--info-bg)",     color: "var(--info)",    border: "var(--info)",    label: "Running",   pulse: true  },
  wait:      { bg: "var(--warn-bg)",     color: "var(--warn)",    border: "var(--warn)",    label: "Awaiting",  pulse: true  },
  err:       { bg: "var(--err-bg)",      color: "var(--err)",     border: "var(--err)",     label: "Failed",    pulse: false },
  cancelled: { bg: "var(--warn-bg)",     color: "var(--warn)",    border: "var(--warn)",    label: "Cancelled", pulse: false },
  skipped:   { bg: "var(--surface-3)",   color: "var(--text-2)",  border: "var(--border)",  label: "Skipped",   pulse: false },
  idle:      { bg: "var(--surface-3)",   color: "var(--text-2)",  border: "var(--border)",  label: "Queued",    pulse: false },
}

function resolveVariant(status: string): BadgeVariant {
  switch (status) {
    case "run":
    case "running":
      return "run"
    case "ok":
    case "success":
    case "succeeded":
    case "completed":
      return "ok"
    case "err":
    case "error":
    case "failed":
      return "err"
    case "wait":
    case "waiting":
    case "waiting_approval":
    case "paused":
      return "wait"
    case "cancelled":
      return "cancelled"
    case "skipped":
      return "skipped"
    case "pending":
    case "queued":
      return "idle"
    default:
      return "idle"
  }
}

interface StatusBadgeProps {
  status: string
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const variant = resolveVariant(status)
  const cfg = BADGE_MAP[variant]
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1,
        padding: "3px 8px",
        borderRadius: 999,
        background: cfg.bg,
        color: cfg.color,
        border: `1px solid ${cfg.border}`,
        whiteSpace: "nowrap",
        flexShrink: 0,
      }}
    >
      {cfg.pulse && (
        <span
          className="conduct-pulse-dot"
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: cfg.color,
            flexShrink: 0,
          }}
        />
      )}
      {cfg.label}
    </span>
  )
}
