import type { Node } from "@xyflow/react"

/**
 * Bring-to-front / send-to-back via React Flow's node `zIndex`. Presentation
 * only — the runtime orders blocks by edges, never by zIndex.
 */
export function reorderZ(nodes: Node[], ids: Set<string>, direction: "front" | "back"): Node[] {
  if (ids.size === 0) return nodes
  const others = nodes.filter(n => !ids.has(n.id)).map(n => n.zIndex ?? 0)
  const target = direction === "front"
    ? (others.length ? Math.max(...others) : 0) + 1
    : (others.length ? Math.min(...others) : 0) - 1
  return nodes.map(n => (ids.has(n.id) ? { ...n, zIndex: target } : n))
}
