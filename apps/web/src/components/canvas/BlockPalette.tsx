"use client"

import {
  Zap,
  Sparkles,
  Plug,
  GitBranch,
  ShieldCheck,
  Bell,
  RefreshCw,
  Database,
  Network,
} from "lucide-react"
import { BLOCK_LIBRARY, BLOCK_STYLES, type BlockType } from "@/lib/block-types"
import { cn } from "@/lib/utils"

function BlockIcon({ type, className }: { type: BlockType; className?: string }) {
  const props = { size: 14, className, strokeWidth: 1.75 }
  switch (type) {
    case "trigger":  return <Zap {...props} />
    case "brain":    return <Sparkles {...props} />
    case "tool":     return <Plug {...props} />
    case "logic":    return <GitBranch {...props} />
    case "approval": return <ShieldCheck {...props} />
    case "output":   return <Bell {...props} />
    case "cleanup":  return <RefreshCw {...props} />
    case "memory":   return <Database {...props} />
    case "guard":    return <ShieldCheck {...props} />
    case "mcp":      return <Network {...props} />
  }
}

export default function BlockPalette({
  collapsed,
}: {
  getToken?: (() => Promise<string | null>) | null
  collapsed?: boolean
}) {
  if (collapsed) {
    return (
      <aside className="w-12 bg-white border-r border-stone-100 flex flex-col items-center py-3 gap-1 overflow-y-auto shrink-0 h-full">
        {BLOCK_LIBRARY.map((block) => {
          const style = BLOCK_STYLES[block.type]
          return (
            <div
              key={block.type}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("application/marshal-block-type", block.type)
                e.dataTransfer.setData("application/marshal-block-title", block.title)
                e.dataTransfer.effectAllowed = "move"
              }}
              title={`${block.title} — ${block.sub}`}
              className={cn(
                "w-8 h-8 flex items-center justify-center rounded-lg border cursor-grab active:cursor-grabbing select-none transition-all hover:shadow-sm",
                style.buttonClass
              )}
            >
              <BlockIcon type={block.type} />
            </div>
          )
        })}
      </aside>
    )
  }

  return (
    <aside className="w-[212px] bg-white border-r border-stone-100 flex flex-col overflow-y-auto shrink-0 h-full">
      <div className="px-3 pt-3 pb-2">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Blocks</p>
        <div className="flex flex-col gap-1">
          {BLOCK_LIBRARY.map((block) => {
            return (
              <div
                key={block.type}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/marshal-block-type", block.type)
                  e.dataTransfer.setData("application/marshal-block-title", block.title)
                  e.dataTransfer.effectAllowed = "move"
                }}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border-2 cursor-grab active:cursor-grabbing select-none transition-shadow hover:shadow-sm bk-${block.type}`}
              >
                <div className="shrink-0">
                  <BlockIcon type={block.type} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="text-[12px] font-semibold leading-none text-stone-800">{block.title}</p>
                    {block.preferred && <span className="text-[8px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded leading-none" style={{ color: "var(--accent-text)", background: "var(--accent-weak)" }}>NEW</span>}
                  </div>
                  <p className="text-[10px] leading-none mt-0.5 opacity-60">{block.sub}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
