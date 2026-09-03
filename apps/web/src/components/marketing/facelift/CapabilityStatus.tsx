"use client"

/**
 * CapabilityStatus — SHIPPED / PREVIEW / PLANNED chips.
 * Maps to product-truth-2026.md legend.
 */

export type CapStatus = "SHIPPED" | "PREVIEW" | "PLANNED"

export interface CapabilityItem {
  name: string
  status: CapStatus
  note?: string
}

export interface CapabilityStatusProps {
  items: CapabilityItem[]
  showLegend?: boolean
}

const STATUS_STYLE: Record<CapStatus, string> = {
  SHIPPED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  PREVIEW: "bg-amber-50 text-amber-700 border-amber-200",
  PLANNED: "bg-stone-50 text-stone-500 border-stone-200",
}

export function CapabilityStatus({ items, showLegend = false }: CapabilityStatusProps) {
  return (
    <div>
      {showLegend && (
        <div className="flex items-center gap-3 mb-4 text-[10px] font-mono uppercase tracking-wider">
          {(["SHIPPED", "PREVIEW", "PLANNED"] as CapStatus[]).map((s) => (
            <span key={s} className={`border rounded px-2 py-0.5 ${STATUS_STYLE[s]}`}>
              {s}
            </span>
          ))}
        </div>
      )}
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.name} className="flex items-center gap-3">
            <span
              className={`shrink-0 border rounded px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider ${
                STATUS_STYLE[item.status]
              }`}
            >
              {item.status}
            </span>
            <span className="text-sm text-stone-700 font-medium">{item.name}</span>
            {item.note && (
              <span className="text-xs text-stone-400 ml-auto">{item.note}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
