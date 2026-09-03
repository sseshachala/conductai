"use client"

/**
 * ThreatModelRow — Protected / Partial / Not protected row.
 */

export type ThreatCoverage = "Protected" | "Partial" | "Not protected"

export interface ThreatModelRowProps {
  threat: string
  coverage: ThreatCoverage
  detail?: string
}

const COVERAGE_STYLE: Record<ThreatCoverage, { badge: string; dot: string }> = {
  Protected: {
    badge: "text-emerald-700 bg-emerald-50 border-emerald-200",
    dot: "bg-emerald-500",
  },
  Partial: {
    badge: "text-amber-700 bg-amber-50 border-amber-200",
    dot: "bg-amber-500",
  },
  "Not protected": {
    badge: "text-stone-500 bg-stone-50 border-stone-200",
    dot: "bg-stone-300",
  },
}

export function ThreatModelRow({ threat, coverage, detail }: ThreatModelRowProps) {
  const cfg = COVERAGE_STYLE[coverage]
  return (
    <div className="flex items-start gap-4 py-3 border-b border-stone-100 last:border-0">
      <div className="flex items-center gap-2 min-w-[140px]">
        <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot}`} />
        <span
          className={`text-[10px] font-mono font-bold uppercase tracking-wider border rounded px-1.5 py-0.5 ${cfg.badge}`}
        >
          {coverage}
        </span>
      </div>
      <div>
        <p className="text-sm font-medium text-stone-800">{threat}</p>
        {detail && <p className="text-xs text-stone-400 mt-0.5">{detail}</p>}
      </div>
    </div>
  )
}

export interface ThreatModelTableProps {
  rows: ThreatModelRowProps[]
}

export function ThreatModelTable({ rows }: ThreatModelTableProps) {
  return (
    <div className="border border-stone-200 rounded-xl overflow-hidden bg-white">
      <div className="px-5 py-3 bg-stone-50 border-b border-stone-200">
        <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-stone-400">
          Guard threat coverage
        </p>
      </div>
      <div className="px-5">
        {rows.map((row) => (
          <ThreatModelRow key={row.threat} {...row} />
        ))}
      </div>
    </div>
  )
}
