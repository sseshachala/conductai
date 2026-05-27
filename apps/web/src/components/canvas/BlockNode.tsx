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

function handleClass(color: string) {
  return `!w-3 !h-3 !border-2 !border-white !shadow-sm !transition-all !opacity-0 group-hover:!opacity-100 hover:!scale-125 ${color}`
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
        style={{ top: -5 }}
      />

      {/* Type badge row */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={cn("text-[8px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded", style.label)}>
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
            style={{ left: "28%", bottom: -5 }} className={handleClass("!bg-green-400")} />
          <Handle id="fail" type="source" position={Position.Bottom}
            style={{ left: "72%", bottom: -5 }} className={handleClass("!bg-red-400")} />
        </>
      ) : isApproval ? (
        <>
          <div className="flex justify-between mt-2 px-0.5">
            <span className="text-[8px] font-semibold text-green-600 uppercase tracking-wide">approved</span>
            <span className="text-[8px] font-semibold text-red-500 uppercase tracking-wide">rejected</span>
          </div>
          <Handle id="approved" type="source" position={Position.Bottom}
            style={{ left: "28%", bottom: -5 }} className={handleClass("!bg-green-400")} />
          <Handle id="rejected" type="source" position={Position.Bottom}
            style={{ left: "72%", bottom: -5 }} className={handleClass("!bg-red-400")} />
        </>
      ) : (
        <Handle type="source" position={Position.Bottom}
          className={handleClass("!bg-stone-400")} style={{ bottom: -5 }} />
      )}
    </div>
  )
}

export default memo(BlockNode)
