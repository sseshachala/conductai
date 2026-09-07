"use client"

/**
 * ActivityRow — compact single-row activity/consequential-actions entry.
 * Renders inline: decision dot + label + action + actor + timestamp.
 * Meant for feed lists. For a full standalone card use DecisionCard.
 */

import type { DecisionState } from "./DecisionCard"

export interface ActivityRowProps {
  decision: DecisionState
  action?: string
  actor?: string
  timestamp?: string
  imageSrc?: string
  imageAlt?: string
}

const DOT: Record<DecisionState, string> = {
  ALLOW: "bg-emerald-500",
  APPROVE: "bg-amber-500",
  BLOCK: "bg-red-500",
}

const LABEL_COLOR: Record<DecisionState, string> = {
  ALLOW: "text-emerald-700",
  APPROVE: "text-amber-700",
  BLOCK: "text-red-700",
}

export function ActivityRow({
  decision,
  action = "deploy_production",
  actor = "cursor-agent-17",
  timestamp = "14:32 UTC",
  imageSrc,
  imageAlt,
}: ActivityRowProps) {
  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={imageAlt ?? `Guard ${decision} activity on ${action}`}
        loading="lazy"
        className="border border-stone-200 rounded-lg shadow-sm w-full h-auto"
      />
    )
  }

  return (
    <div className="flex items-center gap-3 border border-stone-200 rounded-lg bg-white shadow-sm px-4 py-3 text-sm">
      <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${DOT[decision]}`} />
      <span
        className={`font-mono text-[10px] font-bold uppercase tracking-widest shrink-0 w-16 ${LABEL_COLOR[decision]}`}
      >
        {decision}
      </span>
      <span className="font-mono text-[12px] text-stone-800 truncate flex-1">{action}</span>
      <span className="hidden sm:inline font-mono text-[11px] text-stone-500 truncate">
        {actor}
      </span>
      <span className="font-mono text-[10px] text-stone-400 shrink-0">{timestamp}</span>
    </div>
  )
}
