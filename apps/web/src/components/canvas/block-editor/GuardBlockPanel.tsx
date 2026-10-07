"use client"

import { useState, useEffect } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { guard } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"
import { getNestedValue } from "./field-utils"

// ── Guard block panel ─────────────────────────────────────────────────────────

interface GuardPolicy {
  id: string
  rule_id: string
  description: string | null
  action: string
  enabled: boolean
  builtin: boolean
}

const MODE_LABELS: Record<string, { label: string; sub: string; color: string; dot: string }> = {
  block: { label: "Block on violation",  sub: "Halts the run immediately when a policy fires.",     color: "text-red-700",    dot: "bg-red-500"    },
  warn:  { label: "Warn and continue",   sub: "Logs the violation but lets the run finish.",         color: "text-amber-700",  dot: "bg-amber-400"  },
  audit: { label: "Audit only",          sub: "Records violations silently — no run impact.",        color: "text-stone-600",  dot: "bg-stone-400"  },
}

export function GuardBlockPanel({
  getToken,
  config,
  onChange,
  isAdmin = false,
  isViewer = false,
}: {
  getToken?: (() => Promise<string | null>) | null
  config: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  isAdmin?: boolean
  isViewer?: boolean
}) {
  const { activeWorkspace } = useWorkspace()
  const [installed, setInstalled] = useState<boolean | null>(null)
  const [teamId, setTeamId] = useState<string | null>(null)
  const [policies, setPolicies] = useState<GuardPolicy[]>([])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const ws = activeWorkspace?.id ?? ""
        const token = await getToken?.()
        const authFetch: AuthFetch = async (url, opts) => {
          const headers: Record<string, string> = { ...(opts?.headers as Record<string, string> | undefined) }
          if (token) headers["Authorization"] = `Bearer ${token}`
          if (ws) headers["X-Workspace-ID"] = ws
          return fetch(url, { ...opts, headers })
        }

        const installData = await guard.config.installed(authFetch, ws || undefined)
        if (cancelled) return
        if (!installData.installed) { setInstalled(false); return }

        setInstalled(true)
        setTeamId(ws ?? installData.workspace_id)

        const polData: GuardPolicy[] = await guard.policies.list(authFetch, ws || undefined)
        if (!cancelled) setPolicies(polData.filter((p: GuardPolicy) => p.enabled))
      } catch {
        if (!cancelled) setInstalled(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [getToken])

  const mode = (getNestedValue(config, "config.enforcement_mode") as string) || "block"
  const modeInfo = MODE_LABELS[mode] ?? MODE_LABELS.block
  const modePolicies = policies.filter(p => p.action === mode)

  if (installed === null) {
    return <div className="px-4 py-3 text-[11px] text-stone-400">Checking Guard status…</div>
  }

  if (!installed) {
    return (
      <div className="mx-4 my-3 rounded-lg border border-red-200 bg-red-50 px-3 py-3 space-y-2">
        <p className="text-[11px] font-semibold text-red-700">ConductGuard not installed</p>
        {isAdmin ? (
          <>
            <p className="text-[10px] text-red-600 leading-relaxed">
              This block enforces spend caps, tool blocks, and audit policies — but Guard is not set up for your organization.
            </p>
            <a
              href="/packs?tab=modules"
              className="inline-block text-[10px] font-semibold text-red-700 border border-red-300 rounded px-2 py-1 hover:bg-red-100 transition-colors"
            >
              Install Guard →
            </a>
          </>
        ) : (
          <p className="text-[10px] text-red-600 leading-relaxed">
            Guard is not set up for your organization. Ask your workspace admin to install it in Settings → Modules.
          </p>
        )}
      </div>
    )
  }

  const spendCap = (getNestedValue(config, "config.spend_cap_usd") as string) || ""
  const monitoredTools = (getNestedValue(config, "config.monitored_tools") as string[]) || []
  const AI_TOOLS = [
    { id: "claude_code", label: "Claude Code" },
    { id: "cursor",      label: "Cursor"      },
    { id: "codex",       label: "Codex"       },
    { id: "windsurf",    label: "Windsurf"    },
  ]

  function toggleTool(toolId: string) {
    if (isViewer) return
    const next = monitoredTools.includes(toolId)
      ? monitoredTools.filter(t => t !== toolId)
      : [...monitoredTools, toolId]
    onChange("config.monitored_tools", next)
  }

  return (
    <div className="px-4 py-3 space-y-4">
      {/* Enforcement mode */}
      <div>
        <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1.5">Enforcement mode</span>
        <select
          value={mode}
          onChange={e => !isViewer && onChange("config.enforcement_mode", e.target.value)}
          disabled={isViewer}
          className="w-full text-[11px] border border-stone-200 rounded-lg px-2.5 py-1.5 bg-white text-stone-800 focus:outline-none focus:ring-1 focus:ring-stone-300 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <option value="block">Block on violation</option>
          <option value="warn">Warn and continue</option>
          <option value="audit">Audit only</option>
        </select>
        <p className={`text-[10px] mt-1 ${modeInfo.color}`}>{modeInfo.sub}</p>
      </div>

      {/* Spend cap */}
      <div>
        <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1.5">Spend cap (USD)</span>
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[11px] text-stone-400">$</span>
          <input
            type="number"
            min="0"
            step="0.01"
            placeholder="e.g. 5.00"
            value={spendCap}
            onChange={e => !isViewer && onChange("config.spend_cap_usd", e.target.value)}
            disabled={isViewer}
            className="w-full text-[11px] border border-stone-200 rounded-lg pl-6 pr-2.5 py-1.5 bg-white text-stone-800 focus:outline-none focus:ring-1 focus:ring-stone-300 disabled:opacity-60 disabled:cursor-not-allowed"
          />
        </div>
        <p className="text-[10px] text-stone-400 mt-1">Trigger enforcement when spend exceeds this amount per run.</p>
      </div>

      {/* AI tools to monitor */}
      <div>
        <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1.5">Monitor AI tools</span>
        <div className="grid grid-cols-2 gap-1.5">
          {AI_TOOLS.map(tool => (
            <label
              key={tool.id}
              className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 cursor-pointer text-[11px] transition-colors ${
                monitoredTools.includes(tool.id)
                  ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                  : "border-stone-200 bg-stone-50 text-stone-500 hover:border-stone-300"
              } ${isViewer ? "cursor-not-allowed opacity-60" : ""}`}
            >
              <input
                type="checkbox"
                className="w-3 h-3 rounded accent-indigo-600"
                checked={monitoredTools.includes(tool.id)}
                onChange={() => toggleTool(tool.id)}
                disabled={isViewer}
              />
              {tool.label}
            </label>
          ))}
        </div>
        {monitoredTools.length === 0 && (
          <p className="text-[10px] text-stone-400 mt-1">No tools selected — Guard will monitor all tools.</p>
        )}
      </div>

      {/* Policies active for selected mode */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
            {mode} policies
          </span>
          {isAdmin && (
            <a href="/theguard/policies" className="text-[10px] text-stone-400 hover:text-stone-600 underline">
              Manage →
            </a>
          )}
        </div>
        {modePolicies.length === 0 ? (
          <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-2.5 text-[10px] text-stone-400">
            No {mode} policies configured.{" "}
            <a href="/theguard/policies" className="underline hover:text-stone-600">Add one →</a>
          </div>
        ) : (
          <ul className="space-y-1">
            {modePolicies.map(p => (
              <li key={p.id} className="flex items-start gap-2 rounded-lg border border-stone-100 bg-stone-50 px-2.5 py-2">
                <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${modeInfo.dot}`} />
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold text-stone-700 truncate">{p.rule_id}</p>
                  {p.description && (
                    <p className="text-[9px] text-stone-400 leading-snug mt-0.5 line-clamp-2">{p.description}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
