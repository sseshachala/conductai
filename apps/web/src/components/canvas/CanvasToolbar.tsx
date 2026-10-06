"use client"

import type { ReactNode } from "react"
import { useReactFlow } from "@xyflow/react"
import { cn } from "@/lib/utils"

const svg = (children: ReactNode, strokeWidth = 2) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5" aria-hidden="true">{children}</svg>
)

interface Props {
  focusMode: boolean
  onOrganize: () => void
  onToggleFocus: () => void
  minimapOpen: boolean
  onToggleMinimap: () => void
  onSearch: () => void
  /** Z-order buttons appear only while editable nodes are selected. */
  canReorder: boolean
  onZOrder: (direction: "front" | "back") => void
}

/** Unified canvas toolbar — replaces ReactFlow Controls + custom buttons. */
export default function CanvasToolbar({ focusMode, onOrganize, onToggleFocus, minimapOpen, onToggleMinimap, onSearch, canReorder, onZOrder }: Props) {
  const { zoomIn, zoomOut, fitView } = useReactFlow()
  const buttons: Array<{ title: string; onClick: () => void; icon: ReactNode; active?: boolean }> = [
    { title: "Find block (⌘P / Ctrl+P)", onClick: onSearch, icon: svg(<><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>) },
    { title: "Zoom in", onClick: () => zoomIn({ duration: 200 }), icon: svg(<><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>, 2.5) },
    { title: "Zoom out", onClick: () => zoomOut({ duration: 200 }), icon: svg(<line x1="5" y1="12" x2="19" y2="12" />, 2.5) },
    { title: "Fit view", onClick: () => fitView({ padding: 0.2, duration: 400 }), icon: svg(<><path d="M8 3H5a2 2 0 00-2 2v3" /><path d="M21 8V5a2 2 0 00-2-2h-3" /><path d="M3 16v3a2 2 0 002 2h3" /><path d="M16 21h3a2 2 0 002-2v-3" /></>) },
    { title: "Organize — auto-layout all blocks", onClick: onOrganize, icon: svg(<><polygon points="11 2 2 7 11 12 20 7 11 2" /><polyline points="2 17 11 22 20 17" /><polyline points="2 12 11 17 20 12" /></>) },
    {
      title: focusMode ? "Exit focus mode" : "Focus — hide panels, fit all blocks",
      onClick: onToggleFocus,
      active: focusMode,
      icon: focusMode
        ? svg(<><path d="M8 3H5a2 2 0 00-2 2v3" /><path d="M21 8V5a2 2 0 00-2-2h-3" /><path d="M3 16v3a2 2 0 002 2h3" /><path d="M16 21h3a2 2 0 002-2v-3" /><line x1="9" y1="9" x2="15" y2="15" /><line x1="15" y1="9" x2="9" y2="15" /></>)
        : svg(<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />),
    },
    { title: minimapOpen ? "Hide minimap" : "Show minimap", onClick: onToggleMinimap, active: minimapOpen, icon: svg(<><rect x="3" y="3" width="18" height="18" rx="2" /><rect x="12" y="12" width="6" height="6" /></>) },
    ...(canReorder ? [
      { title: "Bring to front (Alt+Shift+])", onClick: () => onZOrder("front"), icon: svg(<><rect x="8" y="8" width="13" height="13" rx="2" fill="currentColor" /><path d="M16 4H5a2 2 0 00-2 2v10" /></>) },
      { title: "Send to back (Alt+Shift+[)", onClick: () => onZOrder("back"), icon: svg(<><rect x="3" y="3" width="13" height="13" rx="2" fill="currentColor" /><path d="M20 8v11a2 2 0 01-2 2H8" /></>) },
    ] : []),
  ]
  return (
    <div role="toolbar" aria-label="Canvas controls" aria-orientation="vertical" className="absolute top-3 right-3 z-10 flex flex-col bg-white border border-stone-200 rounded-xl shadow-sm overflow-hidden">
      {buttons.map((btn, i) => (
        <button
          key={btn.title}
          onClick={btn.onClick}
          title={btn.title}
          aria-label={btn.title}
          aria-pressed={btn.active}
          className={cn(
            "flex items-center justify-center w-9 h-9 transition-colors",
            i < buttons.length - 1 && "border-b border-stone-100",
            btn.active
              ? "bg-stone-900 text-white"
              : "text-stone-500 hover:text-stone-900 hover:bg-stone-50"
          )}
        >
          {btn.icon}
        </button>
      ))}
    </div>
  )
}
