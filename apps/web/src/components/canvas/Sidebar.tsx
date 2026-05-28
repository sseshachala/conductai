"use client"

import { useEffect, useState } from "react"
import {
  Zap, Sparkles, Plug, GitBranch, ShieldCheck, Bell, RefreshCw, Database,
} from "lucide-react"
import { BLOCK_LIBRARY, BLOCK_STYLES, type BlockType } from "@/lib/block-types"
import { cn } from "@/lib/utils"

function BlockIcon({ type, className }: { type: BlockType; className?: string }) {
  const props = { size: 13, className, strokeWidth: 1.75 }
  switch (type) {
    case "trigger":  return <Zap {...props} />
    case "brain":    return <Sparkles {...props} />
    case "tool":     return <Plug {...props} />
    case "logic":    return <GitBranch {...props} />
    case "approval": return <ShieldCheck {...props} />
    case "output":   return <Bell {...props} />
    case "cleanup":  return <RefreshCw {...props} />
    case "memory":   return <Database {...props} />
  }
}

const INTEGRATION_LIST = [
  { handle: "github",       label: "GitHub" },
  { handle: "slack",        label: "Slack" },
  { handle: "linear",       label: "Linear" },
  { handle: "digitalocean", label: "DigitalOcean" },
]

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)
  return m ? m[1] : null
}

export default function Sidebar({ getToken }: { getToken?: (() => Promise<string | null>) | null }) {
  const [connectedHandles, setConnectedHandles] = useState<Set<string>>(new Set())

  useEffect(() => {
    ;(async () => {
      try {
        const headers: Record<string, string> = {}
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
        const ws = getWorkspaceId()
        if (ws) headers["X-Workspace-Id"] = ws
        const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`, { headers })
        if (r.ok) {
          const creds: { handle: string }[] = await r.json()
          setConnectedHandles(new Set(creds.map(c => c.handle.toLowerCase())))
        }
      } catch { /* network error — leave as disconnected */ }
    })()
  }, [])

  return (
    <aside className="w-52 border-l border-stone-200 bg-white flex flex-col overflow-y-auto shrink-0">
      {/* Integrations */}
      <div className="px-3 py-3 border-b border-stone-100">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Integrations</p>
        <div className="space-y-1.5">
          {INTEGRATION_LIST.map((i) => {
            const connected = connectedHandles.has(i.handle)
            return (
              <div key={i.handle} className="flex items-center justify-between">
                <span className="text-xs text-stone-600">{i.label}</span>
                {connected ? (
                  <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                    connected
                  </span>
                ) : (
                  <a href="/settings" className="text-[10px] font-medium text-indigo-500 hover:underline">
                    connect →
                  </a>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Block Library — single-column list */}
      <div className="px-3 py-3">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Blocks</p>
        <div className="flex flex-col gap-1">
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
                className={cn(
                  "flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg border cursor-grab active:cursor-grabbing select-none transition-all hover:shadow-sm",
                  style.buttonClass
                )}
              >
                <BlockIcon type={block.type} className="shrink-0" />
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold leading-none text-stone-800">{block.title}</p>
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
