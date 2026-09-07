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
  imageSrc?: string
  imageAlt?: string
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
  imageSrc,
  imageAlt,
}: DecisionCardProps) {
  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={imageAlt ?? `Guard ${decision} decision`}
        loading="lazy"
        className="border border-stone-200 rounded-xl shadow-sm w-full h-auto"
      />
    )
  }

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
      className={`${cfg.bg} border ${cfg.border} rounded-xl shadow-md text-sm overflow-hidden`}
    >
      {/* Header bar */}
      <div className={`${cfg.badgeBg} border-b ${cfg.border} px-5 py-2.5 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${cfg.dot}`} />
          <span className={`font-mono font-bold tracking-widest text-[10px] uppercase ${cfg.badge}`}>
            {cfg.label}
          </span>
        </div>
        <span className="text-stone-400 text-[10px] font-mono tracking-wider uppercase">Guard</span>
      </div>

      {/* Body */}
      <div className={`px-5 ${compact ? "py-3.5" : "py-4"} space-y-2.5`}>
        <Row label="Agent" value={agent} mono />
        <Row label="Action" value={action} mono />
        <Row label="Resource" value={resource} mono />
        {!compact && <Row label="Policy" value={policy} mono />}
        <Row label="Reason" value={displayReason} wrap />
      </div>

      {/* Approval buttons */}
      {showButtons && decision === "APPROVE" && (
        <div className="border-t border-amber-100 px-5 py-3 flex gap-2 bg-amber-50/50">
          <button className="rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-semibold hover:bg-emerald-700 transition-colors">
            Approve
          </button>
          <button className="rounded-lg bg-white border border-stone-200 text-stone-600 px-4 py-2 text-sm font-semibold hover:bg-stone-50 transition-colors">
            Reject
          </button>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, wrap = false, mono = false }: { label: string; value: string; wrap?: boolean; mono?: boolean }) {
  return (
    <div className={`flex ${wrap ? "flex-col gap-0.5" : "items-baseline gap-3"}`}>
      <span className="text-stone-400 text-[10px] uppercase tracking-widest font-mono shrink-0 w-16">{label}</span>
      <span className={`text-stone-800 ${mono ? "font-mono text-[12px]" : "text-[13px] leading-snug"} ${wrap ? "" : "truncate"}`}>{value}</span>
    </div>
  )
}
