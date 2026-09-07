"use client"

/**
 * CompliancePackCard — Registry pack tile.
 * Category dot + name + description + rule-count pill + enforcement status.
 */

export type PackCategory = "compliance" | "automation"

export interface CompliancePackCardProps {
  name: string
  description?: string
  category?: PackCategory
  ruleCount?: number
  enforced?: boolean
  imageSrc?: string
  imageAlt?: string
}

const CATEGORY_COLOR: Record<PackCategory, string> = {
  compliance: "bg-indigo-500",
  automation: "bg-cyan-500",
}

export function CompliancePackCard({
  name,
  description = "",
  category = "compliance",
  ruleCount,
  enforced = true,
  imageSrc,
  imageAlt,
}: CompliancePackCardProps) {
  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={imageAlt ?? `${name} pack`}
        loading="lazy"
        className="border border-stone-200 rounded-xl shadow-sm w-full h-auto"
      />
    )
  }

  return (
    <div className="border border-stone-200 rounded-xl bg-white shadow-md p-5 text-sm flex flex-col gap-3 h-full">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${CATEGORY_COLOR[category]}`}
        />
        <span className="font-semibold text-stone-900 text-[15px] leading-tight">{name}</span>
      </div>

      {description && (
        <p className="text-stone-600 text-[13px] leading-relaxed line-clamp-3">{description}</p>
      )}

      <div className="flex items-center gap-2 mt-auto pt-3 border-t border-stone-100">
        {typeof ruleCount === "number" && (
          <span className="font-mono text-[11px] text-stone-500 bg-stone-50 border border-stone-200 rounded px-2 py-0.5 tracking-wide">
            {ruleCount} rules
          </span>
        )}
        {enforced && (
          <span className="font-mono text-[10px] uppercase tracking-widest text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5 ml-auto">
            Enforced
          </span>
        )}
      </div>
    </div>
  )
}
