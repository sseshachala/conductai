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
}: EvidenceReceiptProps) {
  return (
    <div className="border border-stone-200 rounded-xl overflow-hidden bg-white shadow-sm font-mono text-xs max-w-sm">
      {/* Header */}
      <div className="bg-stone-900 px-5 py-3 flex items-center justify-between">
        <span className="text-white font-bold text-[11px] tracking-wider">DECISION #{decisionId}</span>
        <DecisionBadge decision={decision} />
      </div>

      {/* Fields */}
      <div className="divide-y divide-stone-100">
        <Field label="Agent" value={agent} />
        <Field label="Action" value={action} />
        <Field label="Resource" value={resource} />
        <Field label="Decision" value={decision} highlight={decision === "BLOCK"} />
        <Field label="Rule" value={rule} />
        <Field label="Reason" value={reason} wrap />
        <Field label="User" value={user} />
        <Field label="Timestamp" value={timestamp} />
      </div>

      {/* Integrity footer */}
      <div className="px-5 py-3 bg-stone-50 border-t border-stone-100 flex items-center justify-between">
        <span className="text-stone-400 text-[10px] uppercase tracking-wider">Integrity</span>
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              integrity === "Verified" ? "bg-emerald-500" : "bg-red-500"
            }`}
          />
          <span
            className={`text-[11px] font-semibold ${
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
}: {
  label: string
  value: string
  highlight?: boolean
  wrap?: boolean
}) {
  return (
    <div className={`flex ${wrap ? "flex-col gap-0.5" : "items-start"} px-5 py-2`}>
      <span className="text-stone-400 text-[10px] uppercase tracking-wider shrink-0 w-20">{label}</span>
      <span
        className={`text-[11px] ${
          highlight ? "text-red-600 font-bold" : "text-stone-700"
        } ${wrap ? "" : "truncate"}`}
      >
        {value}
      </span>
    </div>
  )
}
