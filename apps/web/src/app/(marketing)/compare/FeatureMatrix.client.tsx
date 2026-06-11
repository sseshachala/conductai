"use client"

import { useState } from "react"
import { TOOLS, FEATURE_GROUPS } from "./compare-data"

export default function FeatureMatrix() {
  const [hoveredCol, setHoveredCol] = useState<string | null>(null)
  const toolIds = TOOLS.map(t => t.id)

  return (
    <div className="overflow-x-auto rounded-2xl border border-stone-200 bg-white">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-stone-200">
            <th className="text-left px-5 py-4 text-xs font-semibold text-stone-500 uppercase tracking-wider w-52 bg-stone-50">Feature</th>
            {TOOLS.map(t => (
              <th key={t.id}
                onMouseEnter={() => setHoveredCol(t.id)}
                onMouseLeave={() => setHoveredCol(null)}
                className={`px-4 py-4 text-center text-xs font-bold text-stone-900 transition-colors cursor-pointer min-w-[110px] ${t.id === "conduct" ? "bg-indigo-50" : hoveredCol === t.id ? "bg-stone-50" : ""}`}>
                <span className="block text-lg mb-1">{t.emoji}</span>
                {t.shortName}
              </th>
            ))}
          </tr>
        </thead>
        {FEATURE_GROUPS.map((group, gi) => (
          <tbody key={gi}>
            <tr className="bg-stone-50">
              <td colSpan={toolIds.length + 1} className="px-5 py-2.5 text-[10px] font-bold text-stone-400 uppercase tracking-widest">
                {group.label}
              </td>
            </tr>
            {group.features.map((feature, fi) => (
              <tr key={fi} className="border-t border-stone-100 hover:bg-stone-50 transition-colors">
                <td className="px-5 py-3.5">
                  <p className="font-medium text-stone-900 text-xs">{feature.name}</p>
                  {feature.note && <p className="text-[11px] text-stone-400 mt-0.5 leading-snug">{feature.note}</p>}
                </td>
                {toolIds.map(id => (
                  <td key={id}
                    onMouseEnter={() => setHoveredCol(id)}
                    onMouseLeave={() => setHoveredCol(null)}
                    className={`px-4 py-3.5 text-center text-base transition-colors ${id === "conduct" ? "bg-indigo-50" : hoveredCol === id ? "bg-stone-50" : ""}`}>
                    {(feature.values as Record<string, string>)[id]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}
