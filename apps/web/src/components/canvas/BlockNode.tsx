"use client"

import { memo } from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import { BLOCK_STYLES, type BlockType } from "@/lib/block-types"
import { cn } from "@/lib/utils"

export interface BlockNodeData {
  type: BlockType
  label: string
  description?: string
  isAgentic?: boolean
  integration?: string
  config?: { action?: string; channel?: string; event_type?: string; label?: string; repo_allowlist?: string }
  [key: string]: unknown
}

const INTEGRATION_LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  linear: "Linear",
  vercel: "Vercel",
  railway: "Railway",
  digitalocean: "DigitalOcean",
  email: "Email",
}

const INTEGRATION_COLORS: Record<string, string> = {
  github:       "bg-stone-900 text-white",
  slack:        "bg-purple-600 text-white",
  linear:       "bg-indigo-600 text-white",
  vercel:       "bg-stone-700 text-white",
  railway:      "bg-violet-600 text-white",
  digitalocean: "bg-blue-500 text-white",
  email:        "bg-emerald-600 text-white",
}

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
    </svg>
  )
}

// Block type icons — Lucide-style 24px viewBox, rendered at 9px
function BlockIcon({ type, className }: { type: string; className?: string }) {
  const cls = className ?? "w-[9px] h-[9px]"
  const props = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, className: cls }
  switch (type) {
    case "trigger":  return <svg {...props}><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
    case "brain":    return <svg {...props}><path d="M12 2a4 4 0 014 4c0 .34-.04.67-.1 1H17a3 3 0 010 6h-.5M12 2a4 4 0 00-4 4c0 .34.04.67.1 1H7a3 3 0 000 6h.5"/><path d="M12 2v18M8.5 13h7"/></svg>
    case "tool":     return <svg {...props}><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
    case "logic":    return <svg {...props}><path d="M16 3h5v5M4 20L21 3"/><path d="M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>
    case "memory":   return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/></svg>
    case "approval": return <svg {...props}><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
    case "output":   return <svg {...props}><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
    case "cleanup":  return <svg {...props}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
    case "guard":    return <svg {...props}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
    default:         return null
  }
}

function handleClass(color: string) {
  return `!w-3 !h-3 !border-0 !bg-transparent !shadow-none !opacity-0 !transition-none ${color}`
}

// Derive intent-oriented trigger label from config
function triggerLabel(config: BlockNodeData["config"]): string {
  const et = config?.event_type
  if (et === "webhook")             return "Webhook"
  if (et === "schedule")            return "Schedule"
  if (et === "github_issue_labeled") return "Issue labeled"
  if (et === "github_issue")        return "GitHub issue"
  if (et === "pull_request")        return "Pull request"
  return "Trigger"
}

// Derive trigger secondary context line (e.g. "label = autopilot-ready")
function triggerContext(config: BlockNodeData["config"]): string | null {
  const label = config?.label
  if (label) return `label = ${label}`
  return null
}

// For brain blocks, hide prompt internals and show description only if intent-oriented
function brainDescription(desc: string | undefined): string | null {
  if (!desc) return null
  if (desc.startsWith("You are") || desc.startsWith("you are")) return null
  return desc
}

function BlockNode({ data, selected }: NodeProps) {
  const nodeData = data as BlockNodeData
  const style = BLOCK_STYLES[nodeData.type]
  const isLogic    = nodeData.type === "logic"
  const isApproval = nodeData.type === "approval"
  const isTrigger  = nodeData.type === "trigger"
  const isBrain    = nodeData.type === "brain"
  const isOutput   = nodeData.type === "output"
  const isMemory   = nodeData.type === "memory"
  const memoryAction = isMemory ? ((nodeData.config as Record<string, string>)?.action || "read") : null

  const missingCondition = isLogic && !(nodeData.config as Record<string, unknown>)?.condition

  const integration = nodeData.integration as string | undefined
  const effectiveIntegration = integration || (isOutput ? "slack" : undefined)
  const integrationLabel = effectiveIntegration ? (INTEGRATION_LABELS[effectiveIntegration] ?? effectiveIntegration) : null
  const integrationColor = effectiveIntegration ? (INTEGRATION_COLORS[effectiveIntegration] ?? "bg-stone-500 text-white") : ""

  // Slack channel context: "Slack · #engineering"
  const channel = nodeData.config?.channel
  const integrationSuffix = isOutput && channel ? ` · ${channel}` : ""

  // Primary label
  const primaryLabel = isTrigger ? triggerLabel(nodeData.config) : nodeData.label

  // Secondary line
  const secondary: string | null = (() => {
    if (isTrigger)   return triggerContext(nodeData.config)
    if (isBrain)     return brainDescription(nodeData.description)
    if (!integrationLabel && nodeData.description) return nodeData.description
    return null
  })()

  return (
    <div
      style={{ width: 196 }}
      className={cn(
        "group rounded-xl border-2 px-3 py-2.5 cursor-pointer transition-all shadow-sm",
        style.bg,
        style.border,
        selected
          ? "ring-1 ring-indigo-400 shadow-md"
          : "hover:shadow-md hover:ring-1 hover:ring-stone-200"
      )}
    >
      {/* Target handle */}
      <Handle
        type="target"
        position={Position.Top}
        className={handleClass("!bg-stone-400")}
        style={{ top: 0 }}
      />

      {/* Type badge row */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={cn("inline-flex items-center gap-1 text-[8px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded", style.label)}>
          <BlockIcon type={nodeData.type} />
          {style.labelText}
        </span>
        {nodeData.isAgentic && (
          <span className="text-[8px] font-bold bg-violet-600 text-white px-1.5 py-0.5 rounded">AI</span>
        )}
      </div>

      {/* Primary label */}
      <p className="text-xs font-semibold text-stone-800 leading-tight truncate">
        {primaryLabel}
      </p>

      {/* Memory READ/WRITE badge */}
      {isMemory && (
        <div className="flex items-center gap-1 mt-1.5">
          <span className={cn(
            "text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide",
            memoryAction === "write"
              ? "bg-amber-600 text-white"
              : "bg-amber-100 text-amber-800"
          )}>
            {memoryAction === "write" ? "WRITE" : "READ"}
          </span>
        </div>
      )}

      {/* Provider badge — only badge, no redundant action text */}
      {integrationLabel && !isTrigger && (
        <div className="flex items-center gap-1 mt-1.5">
          <span className={cn("flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded", integrationColor)}>
            {effectiveIntegration === "github" && <GitHubMark className="w-2.5 h-2.5" />}
            {integrationLabel}{integrationSuffix}
          </span>
        </div>
      )}

      {/* Trigger provider badge */}
      {isTrigger && (
        <div className="flex items-center gap-1 mt-1.5">
          <span className={cn("flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded", INTEGRATION_COLORS.github)}>
            <GitHubMark className="w-2.5 h-2.5" />
            GitHub
          </span>
        </div>
      )}

      {/* Secondary / context line */}
      {secondary && (
        <p className="text-[10px] text-stone-400 mt-1 leading-tight truncate">{secondary}</p>
      )}

      {/* Logic condition warning */}
      {missingCondition && (
        <p className="text-[9px] text-amber-600 bg-amber-50 rounded px-1.5 py-0.5 mt-1.5">Set a condition</p>
      )}

      {/* Logic pass/fail handles */}
      {isLogic ? (
        <>
          <div className="flex justify-between mt-2 px-0.5">
            <span className="text-[8px] font-semibold text-green-600 uppercase tracking-wide">pass</span>
            <span className="text-[8px] font-semibold text-red-500 uppercase tracking-wide">fail</span>
          </div>
          <Handle id="pass" type="source" position={Position.Bottom}
            style={{ left: "28%", bottom: 0 }} className={handleClass("!bg-green-400")} />
          <Handle id="fail" type="source" position={Position.Bottom}
            style={{ left: "72%", bottom: 0 }} className={handleClass("!bg-red-400")} />
        </>
      ) : isApproval ? (
        <>
          <div className="flex justify-between mt-2 px-0.5">
            <span className="text-[8px] font-semibold text-green-600 uppercase tracking-wide">approved</span>
            <span className="text-[8px] font-semibold text-red-500 uppercase tracking-wide">rejected</span>
          </div>
          <Handle id="approved" type="source" position={Position.Bottom}
            style={{ left: "28%", bottom: 0 }} className={handleClass("!bg-green-400")} />
          <Handle id="rejected" type="source" position={Position.Bottom}
            style={{ left: "72%", bottom: 0 }} className={handleClass("!bg-red-400")} />
        </>
      ) : (
        <Handle type="source" position={Position.Bottom}
          className={handleClass("!bg-stone-400")} style={{ bottom: 0 }} />
      )}
    </div>
  )
}

export default memo(BlockNode)
