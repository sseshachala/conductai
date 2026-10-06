import type { Node } from "@xyflow/react"
import type { BlockNodeData } from "@/components/canvas/BlockNode"

export interface ValidationError {
  blockId: string
  label: string
  message: string
}

export function validateNodes(nodes: Node[]): ValidationError[] {
  const errors: ValidationError[] = []

  for (const node of nodes) {
    const data = node.data as BlockNodeData
    const blockType = data.type
    const label = data.label || node.id
    const config = (data.config as Record<string, unknown>) ?? {}
    const integration = data.integration as string | undefined

    if (blockType === "tool" || blockType === "cleanup") {
      if (!integration) {
        errors.push({ blockId: node.id, label, message: "No integration selected" })
        continue
      }
      const action = (config.action as string) || ""
      if (!action) {
        errors.push({ blockId: node.id, label, message: `No action selected for ${integration}` })
        continue
      }
      // Check required params (non-empty, no defaultValue)
      const params = (config.params as Record<string, unknown>) ?? {}
      const requiredEmpty: string[] = []
      for (const [key, val] of Object.entries(params)) {
        if ((val === "" || val === null || val === undefined) && !String(val ?? "").startsWith("{{")) {
          requiredEmpty.push(key)
        }
      }
      if (requiredEmpty.length > 0) {
        errors.push({ blockId: node.id, label, message: `Missing: ${requiredEmpty.join(", ")}` })
      }
    }

    if (blockType === "output") {
      const via = integration || "slack"
      if ((via === "slack" || via === "both") && !config.channel) {
        errors.push({ blockId: node.id, label, message: "Slack channel is required (e.g. #general)" })
      }
      if ((via === "email" || via === "both") && !(config.to as string)) {
        errors.push({ blockId: node.id, label, message: "Email address (To) is required" })
      }
    }

    if (blockType === "approval") {
      if (!config.message) {
        errors.push({ blockId: node.id, label, message: "Approval message is required" })
      }
    }
  }

  return errors
}
