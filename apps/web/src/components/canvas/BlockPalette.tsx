"use client"

import { BLOCK_LIBRARY, BLOCK_STYLES } from "@/lib/block-types"
import { cn } from "@/lib/utils"

export default function BlockPalette({
  getToken,
  collapsed,
}: {
  getToken?: (() => Promise<string | null>) | null
  collapsed?: boolean
}) {
  if (collapsed) {
    return (
      <aside className="w-12 bg-white flex flex-col items-center py-3 gap-1 overflow-y-auto shrink-0 h-full">
        {BLOCK_LIBRARY.map((block) => {
          const style = BLOCK_STYLES[block.type]
          return (
            <div
              key={block.title}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("application/marshal-block-type", block.type)
                e.dataTransfer.setData("application/marshal-block-title", block.title)
                e.dataTransfer.effectAllowed = "move"
              }}
              title={block.title}
              className={cn(
                "w-8 h-8 flex items-center justify-center rounded-lg border-2 cursor-grab active:cursor-grabbing select-none transition-all hover:shadow-sm text-base",
                style.buttonClass
              )}
            >
              {style.icon}
            </div>
          )
        })}
      </aside>
    )
  }

  return (
    <aside className="w-44 bg-white flex flex-col overflow-y-auto shrink-0 h-full">
      <div className="px-3 py-3">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Blocks</p>
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
                <span className="text-base leading-none">{style.icon}</span>
                <span className="text-[11px] font-semibold text-stone-800 leading-tight">{shortName}</span>
              </div>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
