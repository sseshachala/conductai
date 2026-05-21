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
  config?: { action?: string }
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
  github:       "bg-stone-800 text-white",
  slack:        "bg-purple-600 text-white",
  linear:       "bg-indigo-600 text-white",
  vercel:       "bg-stone-700 text-white",
  railway:      "bg-violet-600 text-white",
  digitalocean: "bg-blue-500 text-white",
  email:        "bg-emerald-600 text-white",
}

function handleClass(color: string) {
  return `!w-2.5 !h-2.5 !border-2 !border-white !shadow-sm !transition-transform hover:!scale-125 ${color}`
}

function BlockNode({ data, selected }: NodeProps) {
  const nodeData = data as BlockNodeData
  const style = BLOCK_STYLES[nodeData.type]
  const isLogic = nodeData.type === "logic"
  const missingCondition = isLogic && !(nodeData.config as Record<string, unknown>)?.condition
  const integration = nodeData.integration as string | undefined
  const action = nodeData.config?.action

  const effectiveIntegration = integration || (nodeData.type === "output" ? "slack" : undefined)
  const integrationLabel = effectiveIntegration ? INTEGRATION_LABELS[effectiveIntegration] ?? effectiveIntegration : null
  const integrationColor = effectiveIntegration ? (INTEGRATION_COLORS[effectiveIntegration] ?? "bg-stone-500 text-white") : ""
  const actionLabel = action
    ? action.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
    : null

  return (
    <div
      style={{ width: 200 }}
      className={cn(
        "rounded-xl border-2 px-3 py-2.5 cursor-pointer transition-all shadow-sm",
        style.bg,
        style.border,
        selected
          ? "ring-2 ring-indigo-400 ring-offset-2 shadow-md"
          : "hover:shadow-md hover:ring-1 hover:ring-stone-300 hover:ring-offset-1"
      )}
    >
      {/* Target handle (top) */}
      <Handle
        type="target"
        position={Position.Top}
        className={handleClass("!bg-stone-400")}
        style={{ top: -6 }}
      />

      {/* Block type badge row */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={cn("text-[8px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded", style.label)}>
          {style.labelText}
        </span>
        {nodeData.isAgentic && (
          <span className="text-[8px] font-bold bg-purple-600 text-white px-1.5 py-0.5 rounded">AI</span>
        )}
      </div>

      {/* Block label — trigger nodes show human-readable event name */}
      <p className="text-xs font-semibold text-stone-800 leading-tight truncate">
        {nodeData.type === "trigger"
          ? (nodeData.config as Record<string, string> | undefined)?.event_type === "webhook"
            ? "Webhook"
            : "GitHub Issue"
          : nodeData.label}
      </p>

      {/* Integration + action sub-label */}
      {integrationLabel && !(nodeData.type === "trigger" && (nodeData.config as Record<string, string> | undefined)?.event_type !== "github_issue_labeled") && (
        <div className="flex items-center gap-1 mt-1.5 flex-wrap">
          <span className={cn("text-[9px] font-semibold px-1.5 py-0.5 rounded", integrationColor)}>
            {integrationLabel}
          </span>
          {actionLabel && (
            <span className="text-[9px] text-stone-400 truncate">{actionLabel}</span>
          )}
        </div>
      )}

      {/* Description (no integration set, not a trigger) */}
      {!integrationLabel && nodeData.description && nodeData.type !== "trigger" && (
        <p className="text-[10px] text-stone-400 mt-0.5 leading-tight truncate">{nodeData.description}</p>
      )}

      {/* Logic condition warning */}
      {missingCondition && (
        <p className="text-[9px] text-amber-600 bg-amber-50 rounded px-1.5 py-0.5 mt-1.5">⚠ Set a condition</p>
      )}

      {/* Logic pass/fail handles */}
      {isLogic ? (
        <>
          <div className="flex justify-between mt-2 px-0.5">
            <span className="text-[8px] font-semibold text-green-600 uppercase tracking-wide">pass</span>
            <span className="text-[8px] font-semibold text-red-500 uppercase tracking-wide">fail</span>
          </div>
          <Handle
            id="pass"
            type="source"
            position={Position.Bottom}
            style={{ left: "28%", bottom: -6 }}
            className={handleClass("!bg-green-400")}
          />
          <Handle
            id="fail"
            type="source"
            position={Position.Bottom}
            style={{ left: "72%", bottom: -6 }}
            className={handleClass("!bg-red-400")}
          />
        </>
      ) : (
        <Handle
          type="source"
          position={Position.Bottom}
          className={handleClass("!bg-stone-400")}
          style={{ bottom: -6 }}
        />
      )}
    </div>
  )
}

export default memo(BlockNode)
