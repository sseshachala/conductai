"use client"

/**
 * PlaybookTile — playbook card: name, category, block sequence preview.
 */

export type PlaybookCategory =
  | "code-review"
  | "ci-cd"
  | "security"
  | "incident"
  | "monitoring"
  | "onboarding"

const CATEGORY_LABEL: Record<PlaybookCategory, string> = {
  "code-review": "Code Review",
  "ci-cd": "CI / CD",
  security: "Security",
  incident: "Incident",
  monitoring: "Monitoring",
  onboarding: "Onboarding",
}

const CATEGORY_STYLE: Record<PlaybookCategory, string> = {
  "code-review": "bg-sky-50 text-sky-700 border-sky-200",
  "ci-cd": "bg-violet-50 text-violet-700 border-violet-200",
  security: "bg-red-50 text-red-700 border-red-200",
  incident: "bg-orange-50 text-orange-700 border-orange-200",
  monitoring: "bg-teal-50 text-teal-700 border-teal-200",
  onboarding: "bg-stone-50 text-stone-600 border-stone-200",
}

export type BlockType = "trigger" | "brain" | "guard" | "approval" | "tool" | "output"

const BLOCK_COLOUR: Record<BlockType, string> = {
  trigger: "bg-stone-700 text-white",
  brain: "bg-violet-600 text-white",
  guard: "bg-emerald-600 text-white",
  approval: "bg-amber-500 text-white",
  tool: "bg-sky-600 text-white",
  output: "bg-stone-300 text-stone-700",
}

export interface PlaybookTileProps {
  name: string
  category: PlaybookCategory
  description?: string
  blocks?: BlockType[]
}

export function PlaybookTile({
  name,
  category,
  description,
  blocks = ["trigger", "brain", "guard"],
}: PlaybookTileProps) {
  return (
    <div className="border border-stone-200 rounded-xl p-4 bg-white hover:border-stone-300 hover:shadow-sm transition-all">
      {/* Category badge */}
      <div className="mb-3">
        <span
          className={`text-[10px] font-mono font-bold uppercase tracking-wider border rounded px-2 py-0.5 ${CATEGORY_STYLE[category]}`}
        >
          {CATEGORY_LABEL[category]}
        </span>
      </div>

      {/* Name */}
      <p className="text-sm font-semibold text-stone-900 mb-1 font-mono">{name}</p>
      {description && <p className="text-xs text-stone-500 mb-3 leading-relaxed">{description}</p>}

      {/* Block sequence */}
      <div className="flex items-center gap-1 flex-wrap">
        {blocks.map((block, i) => (
          <span key={i} className="flex items-center gap-1">
            <span
              className={`text-[9px] font-mono font-bold uppercase tracking-wider rounded px-1.5 py-0.5 ${BLOCK_COLOUR[block]}`}
            >
              {block}
            </span>
            {i < blocks.length - 1 && (
              <span className="text-stone-300 text-[10px]">→</span>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}
