"use client"

/**
 * LensTranscript — user query bubble + assistant response as a compact
 * result table. Meant for Evidence/Lens marketing sections where the
 * response is structured (counts, decisions, rules), not free prose.
 */

export type LensDecision = "ALLOW" | "APPROVE" | "BLOCK"

export interface LensTranscriptRow {
  action?: string
  decision?: LensDecision
  count?: number
  rule?: string
}

export interface LensTranscriptProps {
  query?: string
  answerHeadline?: string
  rows?: LensTranscriptRow[]
  imageSrc?: string
  imageAlt?: string
}

const DECISION_COLOR: Record<LensDecision, string> = {
  ALLOW: "text-emerald-700 bg-emerald-50 border-emerald-200",
  APPROVE: "text-amber-700 bg-amber-50 border-amber-200",
  BLOCK: "text-red-700 bg-red-50 border-red-200",
}

const DEFAULT_ROWS: LensTranscriptRow[] = [
  { action: "process_refund", decision: "BLOCK", count: 12, rule: "refund-cap-500" },
  { action: "issue_credit", decision: "BLOCK", count: 3, rule: "credit-cap-1000" },
  { action: "deploy_production", decision: "APPROVE", count: 4, rule: "prod-change-v4" },
]

export function LensTranscript({
  query = "Show me every block against payments this month",
  answerHeadline = "Every block against payments · Sep 2026",
  rows = DEFAULT_ROWS,
  imageSrc,
  imageAlt,
}: LensTranscriptProps) {
  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={imageAlt ?? `Lens transcript: ${query}`}
        loading="lazy"
        className="border border-stone-200 rounded-xl shadow-md w-full h-auto"
      />
    )
  }

  return (
    <div className="border border-stone-200 rounded-xl overflow-hidden bg-white shadow-md text-sm">
      {/* User query bubble */}
      <div className="px-5 py-3 bg-indigo-600">
        <p className="text-white text-[13px] leading-snug">{query}</p>
      </div>

      {/* Assistant answer */}
      <div className="px-5 py-4 space-y-3">
        <p className="font-semibold text-stone-900 text-[14px]">{answerHeadline}</p>
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-stone-400 text-[10px] uppercase tracking-widest font-mono">
              <th className="text-left font-medium py-1">Action</th>
              <th className="text-left font-medium py-1">Decision</th>
              <th className="text-right font-medium py-1">Count</th>
              <th className="text-right font-medium py-1">Rule</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="py-2 font-mono text-stone-800 truncate">{r.action}</td>
                <td className="py-2">
                  {r.decision && (
                    <span
                      className={`inline-block font-mono text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded border ${DECISION_COLOR[r.decision]}`}
                    >
                      {r.decision}
                    </span>
                  )}
                </td>
                <td className="py-2 text-right font-mono text-stone-700">{r.count}</td>
                <td className="py-2 text-right font-mono text-stone-500 text-[11px]">{r.rule}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
