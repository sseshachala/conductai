"use client"

import { BLOCK_LIBRARY, BLOCK_STYLES } from "@/lib/block-types"
import { cn } from "@/lib/utils"

const INTEGRATIONS = [
  { name: "GitHub",       status: "connect" },
  { name: "Slack",        status: "connect" },
  { name: "Linear",       status: "connect" },
  { name: "DigitalOcean", status: "connect" },
  { name: "Vercel",       status: "connect" },
  { name: "Postgres",     status: "add" },
]

export default function Sidebar() {
  return (
    <aside className="w-52 border-l border-stone-200 bg-white flex flex-col overflow-y-auto shrink-0">
      {/* Integrations */}
      <div className="px-3 py-3 border-b border-stone-100">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Integrations</p>
        <div className="space-y-1.5">
          {INTEGRATIONS.map((i) => (
            <div key={i.name} className="flex items-center justify-between">
              <span className="text-xs text-stone-600">{i.name}</span>
              <button className="text-[10px] font-medium text-indigo-500 hover:underline">{i.status}</button>
            </div>
          ))}
        </div>
      </div>

      {/* Block Library — 2-column square grid */}
      <div className="px-3 py-3">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Block Library</p>
        <div className="grid grid-cols-2 gap-1.5">
          {BLOCK_LIBRARY.map((block) => {
            const style = BLOCK_STYLES[block.type]
            const shortName = block.title.split(" · ")[1] ?? block.title
            return (
              <div
                key={block.title}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/marshal-block-type", block.type)
                  e.dataTransfer.setData("application/marshal-block-title", block.title)
                  e.dataTransfer.effectAllowed = "move"
                }}
                style={{ aspectRatio: "1 / 1" }}
                className={cn(
                  "flex flex-col justify-between p-2 rounded-lg border-2 cursor-grab active:cursor-grabbing select-none transition-all hover:shadow-sm",
                  style.buttonClass
                )}
              >
                <span className={cn("text-[8px] font-bold tracking-widest uppercase", style.text)}>
                  {style.labelText}
                </span>
                <span className="text-[11px] font-semibold text-stone-800 leading-tight">{shortName}</span>
              </div>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
