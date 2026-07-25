"use client"

import { useEffect, useState } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import {
  Zap, Sparkles, Plug, GitBranch, ShieldCheck, Bell, RefreshCw, Database, Network,
} from "lucide-react"
import { BLOCK_LIBRARY, BLOCK_STYLES, type BlockType } from "@/lib/block-types"
import { cn } from "@/lib/utils"
import { credentials } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"

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
    case "mcp":      return <Network {...props} />
  }
}

const INTEGRATION_LIST = [
  { handle: "github",       label: "GitHub" },
  { handle: "slack",        label: "Slack" },
  { handle: "linear",       label: "Linear" },
  { handle: "digitalocean", label: "DigitalOcean" },
]

export default function Sidebar({ getToken }: { getToken?: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const [connectedHandles, setConnectedHandles] = useState<Set<string>>(new Set())

  useEffect(() => {
    ;(async () => {
      try {
        const wsId = activeWorkspace?.id ?? null
        const authFetch: AuthFetch = async (url, opts) => {
          const headers: Record<string, string> = {
            ...(opts?.headers as Record<string, string> | undefined),
          }
          if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
          if (wsId) headers["X-Workspace-ID"] = wsId
          return fetch(url, { ...opts, headers })
        }
        const creds = await credentials.list(authFetch)
        setConnectedHandles(new Set(creds.map((c: { handle: string }) => c.handle.toLowerCase())))
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
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="text-[12px] font-semibold leading-none text-stone-800">{block.title}</p>
                    {block.preferred && <span className="text-[8px] font-bold uppercase tracking-wide px-1 py-0.5 rounded bg-cyan-100 text-cyan-700 leading-none">preferred</span>}
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
