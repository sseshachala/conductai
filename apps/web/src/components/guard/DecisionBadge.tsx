"use client"

const DECISION: Record<string, { cls: string; label: string }> = {
  allowed:  { cls: "sbadge ok",   label: "Allowed"  },
  blocked:  { cls: "sbadge err",  label: "Blocked"  },
  warned:   { cls: "sbadge warn", label: "Warned"   },
  audited:  { cls: "sbadge info", label: "Audited"  },
  approval: { cls: "sbadge warn", label: "Approval" },
}

export function DecisionBadge({ decision }: { decision: string }) {
  const d = DECISION[decision?.toLowerCase()]
  if (!d) return <span className="sbadge warn">{decision}</span>
  return <span className={d.cls}>{d.label}</span>
}
