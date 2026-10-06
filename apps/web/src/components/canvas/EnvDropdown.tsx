"use client"

import { useEffect, useRef, useState } from "react"
import type { Node } from "@xyflow/react"
import type { BlockNodeData } from "./BlockNode"

export default function EnvDropdown({
  environments, selectedEnvId, credentials, nodes, disabled, onChange,
}: {
  environments: Array<{ id: string; name: string }>
  selectedEnvId: string
  credentials: Array<{ handle: string; service: string }>
  nodes: Node[]
  disabled: boolean
  onChange: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as HTMLElement)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  const connectedServices = new Set(credentials.map(c => c.service.toLowerCase()))
  if (connectedServices.has("git")) connectedServices.add("github")

  const usedServices = Array.from(new Set(
    nodes.map(n => (n.data as BlockNodeData).integration as string | undefined)
      .filter((s): s is string => !!s && s in SERVICE_META)
  ))

  const selectedEnv = environments.find(e => e.id === selectedEnvId)

  // Summary dots shown in the trigger button
  const summaryDots = usedServices.slice(0, 4).map(svc => ({
    svc,
    ok: connectedServices.has(svc),
    meta: SERVICE_META[svc],
  }))

  return (
    <div ref={ref} className="relative ml-2">
      <button
        onClick={() => !disabled && setOpen(o => !o)}
        disabled={disabled}
        className="flex items-center gap-1.5 text-xs border border-stone-200 rounded-lg px-2.5 py-1 text-stone-600 bg-white hover:border-stone-300 disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-violet-200"
      >
        <span>{selectedEnv ? selectedEnv.name : "— select environment —"}</span>
        {selectedEnvId && summaryDots.length > 0 && (
          <span className="flex items-center gap-0.5 ml-1">
            {summaryDots.map(d => (
              <span key={d.svc} title={`${d.meta.label}: ${d.ok ? "connected" : "not connected"}`}
                className={`w-1.5 h-1.5 rounded-full ${d.ok ? "bg-emerald-400" : "bg-amber-400"}`} />
            ))}
          </span>
        )}
        <svg width={10} height={10} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="ml-0.5 opacity-40">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div className="absolute top-full mt-1 left-0 z-50 w-64 bg-white border border-stone-200 rounded-xl shadow-lg overflow-hidden">
          {/* No environment option */}
          <button
            onClick={() => { onChange(""); setOpen(false) }}
            className={`w-full text-left px-3 py-2 text-xs text-stone-400 hover:bg-stone-50 ${!selectedEnvId ? "bg-stone-50 font-medium" : ""}`}
          >
            — no vault —
          </button>

          {environments.map(env => (
            <button
              key={env.id}
              onClick={() => { onChange(env.id); setOpen(false) }}
              className={`w-full text-left px-3 py-2.5 hover:bg-stone-50 border-t border-stone-100 ${env.id === selectedEnvId ? "bg-violet-50" : ""}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-stone-800">{env.name}</span>
                {env.id === selectedEnvId && (
                  <span className="text-[9px] font-semibold text-violet-600 bg-violet-100 px-1.5 py-0.5 rounded-full">active</span>
                )}
              </div>
              {usedServices.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {usedServices.map(svc => {
                    const ok = connectedServices.has(svc)
                    const meta = SERVICE_META[svc]
                    return (
                      <span key={svc} className={`flex items-center gap-1 text-[9px] font-medium px-1.5 py-0.5 rounded-full border ${ok ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-amber-50 border-amber-200 text-amber-700"}`}>
                        <span className={`w-1 h-1 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`} />
                        {meta.label}
                      </span>
                    )
                  })}
                </div>
              ) : (
                <span className="text-[10px] text-stone-400">No integrations used</span>
              )}
            </button>
          ))}

          <div className="border-t border-stone-100 px-3 py-2">
            <a href="/settings" className="text-[10px] text-violet-600 hover:underline font-medium">
              Manage Vault →
            </a>
          </div>
        </div>
      )}
    </div>
  )
}

const SERVICE_META: Record<string, { label: string; abbr: string; color: string }> = {
  github:       { label: "GitHub",       abbr: "GH", color: "bg-stone-800 text-white" },
  slack:        { label: "Slack",        abbr: "SL", color: "bg-purple-600 text-white" },
  linear:       { label: "Linear",       abbr: "LN", color: "bg-indigo-600 text-white" },
  digitalocean: { label: "DigitalOcean", abbr: "DO", color: "bg-blue-500 text-white" },
  email:        { label: "Email",        abbr: "EM", color: "bg-emerald-600 text-white" },
}
