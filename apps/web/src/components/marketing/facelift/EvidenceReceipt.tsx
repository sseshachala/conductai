"use client"

/**
 * EvidenceReceipt — IMG-04 layout.
 * Canonical data from plan §10 / facelift plan §5.
 */

export interface EvidenceReceiptProps {
  decisionId?: string
  agent?: string
  action?: string
  resource?: string
  decision?: "ALLOW" | "APPROVE" | "BLOCK"
  rule?: string
  reason?: string
  user?: string
  timestamp?: string
  integrity?: "Verified" | "Failed" | "Pending"
  imageSrc?: string
  imageAlt?: string
}

export function EvidenceReceipt({
  decisionId = "CG-82177",
  agent = "cursor-agent-17",
  action = "update_terraform",
  resource = "prod-vpc",
  decision = "BLOCK",
  rule = "no-production-network-change",
  reason = "Production network modifications require approved change record.",
  user = "developer@acme.example",
  timestamp = "14:32:11 UTC · 2026-03-11",
  integrity = "Verified",
  imageSrc,
  imageAlt,
}: EvidenceReceiptProps) {
  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={imageAlt ?? `Evidence receipt for decision ${decisionId}`}
        loading="lazy"
        className="border border-stone-200 rounded-xl shadow-sm max-w-sm w-full h-auto"
      />
    )
  }

  return (
    <div className="border border-stone-200 rounded-xl overflow-hidden bg-white shadow-md text-sm max-w-sm">
      {/* Header */}
      <div className="bg-stone-900 px-5 py-3 flex items-center justify-between">
        <span className="text-white font-mono font-bold text-[11px] tracking-widest">DECISION #{decisionId}</span>
        <DecisionBadge decision={decision} />
      </div>

      {/* Fields */}
      <div className="divide-y divide-stone-100">
        <Field label="Agent" value={agent} mono />
        <Field label="Action" value={action} mono />
        <Field label="Resource" value={resource} mono />
        <Field label="Decision" value={decision} highlight={decision === "BLOCK"} mono />
        <Field label="Rule" value={rule} mono />
        <Field label="Reason" value={reason} wrap />
        <Field label="User" value={user} mono />
        <Field label="Timestamp" value={timestamp} mono />
      </div>

      {/* Integrity footer */}
      <div className="px-5 py-3 bg-stone-50 border-t border-stone-100 flex items-center justify-between">
        <span className="text-stone-400 text-[10px] uppercase tracking-widest font-mono">Integrity</span>
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              integrity === "Verified" ? "bg-emerald-500" : "bg-red-500"
            }`}
          />
          <span
            className={`text-[12px] font-semibold ${
              integrity === "Verified" ? "text-emerald-700" : "text-red-700"
            }`}
          >
            {integrity}
          </span>
        </div>
      </div>
    </div>
  )
}

function DecisionBadge({ decision }: { decision: "ALLOW" | "APPROVE" | "BLOCK" }) {
  const map = {
    ALLOW: "bg-emerald-500 text-white",
    APPROVE: "bg-amber-500 text-white",
    BLOCK: "bg-red-500 text-white",
  }
  return (
    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${map[decision]}`}>
      {decision}
    </span>
  )
}

function Field({
  label,
  value,
  highlight = false,
  wrap = false,
  mono = false,
}: {
  label: string
  value: string
  highlight?: boolean
  wrap?: boolean
  mono?: boolean
}) {
  return (
    <div className={`flex ${wrap ? "flex-col gap-0.5" : "items-baseline"} px-5 py-2.5 gap-3`}>
      <span className="text-stone-400 text-[10px] uppercase tracking-widest font-mono shrink-0 w-20">{label}</span>
      <span
        className={`${mono ? "font-mono text-[12px]" : "text-[13px] leading-snug"} ${
          highlight ? "text-red-600 font-bold" : "text-stone-800"
        } ${wrap ? "" : "truncate"}`}
      >
        {value}
      </span>
    </div>
  )
}
