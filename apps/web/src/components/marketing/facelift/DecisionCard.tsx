"use client"

/**
 * DecisionCard — renders a Guard policy decision card.
 * Supports ALLOW / APPROVE / BLOCK states.
 * Canonical fake data from plan §10 should be passed via props.
 */

export type DecisionState = "ALLOW" | "APPROVE" | "BLOCK"

export interface DecisionCardProps {
  agent?: string
  action?: string
  resource?: string
  policy?: string
  decision: DecisionState
  reason?: string
  showButtons?: boolean
  compact?: boolean
}

const STATE_CONFIG: Record<DecisionState, {
  bg: string
  border: string
  badge: string
  badgeBg: string
  dot: string
  label: string
}> = {
  ALLOW: {
    bg: "bg-white",
    border: "border-emerald-200",
    badge: "text-emerald-700",
    badgeBg: "bg-emerald-50",
    dot: "bg-emerald-500",
    label: "ALLOW",
  },
  APPROVE: {
    bg: "bg-white",
    border: "border-amber-200",
    badge: "text-amber-700",
    badgeBg: "bg-amber-50",
    dot: "bg-amber-500",
    label: "REQUIRES APPROVAL",
  },
  BLOCK: {
    bg: "bg-white",
    border: "border-red-200",
    badge: "text-red-700",
    badgeBg: "bg-red-50",
    dot: "bg-red-500",
    label: "BLOCK",
  },
}

export function DecisionCard({
  agent = "claude-code / deploy-agent",
  action = "deploy_production",
  resource = "payments-api",
  policy = "production-change-v4",
  decision,
  reason,
  showButtons = false,
  compact = false,
}: DecisionCardProps) {
  const cfg = STATE_CONFIG[decision]
  const defaultReason =
    decision === "APPROVE"
      ? "Production deployment outside approved change window"
      : decision === "BLOCK"
      ? "Production network modifications require approved change record."
      : "Action within policy limits"

  const displayReason = reason ?? defaultReason

  return (
    <div
      className={`${cfg.bg} border ${cfg.border} rounded-xl shadow-sm font-mono text-xs overflow-hidden`}
    >
      {/* Header bar */}
      <div className={`${cfg.badgeBg} border-b ${cfg.border} px-4 py-2 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${cfg.dot}`} />
          <span className={`font-bold tracking-wider text-[10px] uppercase ${cfg.badge}`}>
            {cfg.label}
          </span>
        </div>
        <span className="text-stone-400 text-[10px]">Guard</span>
      </div>

      {/* Body */}
      <div className={`px-4 ${compact ? "py-3" : "py-4"} space-y-2`}>
        <Row label="Agent" value={agent} />
        <Row label="Action" value={action} />
        <Row label="Resource" value={resource} />
        {!compact && <Row label="Policy" value={policy} />}
        <Row label="Reason" value={displayReason} wrap />
      </div>

      {/* Approval buttons */}
      {showButtons && decision === "APPROVE" && (
        <div className="border-t border-amber-100 px-4 py-3 flex gap-2 bg-amber-50/50">
          <button className="rounded-lg bg-emerald-600 text-white px-4 py-1.5 text-xs font-semibold hover:bg-emerald-700 transition-colors">
            Approve
          </button>
          <button className="rounded-lg bg-white border border-stone-200 text-stone-600 px-4 py-1.5 text-xs font-semibold hover:bg-stone-50 transition-colors">
            Reject
          </button>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, wrap = false }: { label: string; value: string; wrap?: boolean }) {
  return (
    <div className={`flex ${wrap ? "flex-col gap-0.5" : "items-start gap-2"}`}>
      <span className="text-stone-400 text-[10px] uppercase tracking-wider shrink-0 w-16">{label}</span>
      <span className={`text-stone-700 text-[11px] ${wrap ? "" : "truncate"}`}>{value}</span>
    </div>
  )
}
