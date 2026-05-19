/**
 * Deterministic auto-layout for the workflow canvas.
 *
 * When nodes arrive from the YAML loader they have no meaningful positions
 * (the backend writes col*260 / row*0 placeholders). We want them rendered
 * cleanly — top-to-bottom or left-to-right, branches separated, edges
 * non-overlapping. dagre is the standard tool for this and is what every
 * "Auto layout" button in React Flow demos uses.
 */
import dagre from "@dagrejs/dagre"
import type { Edge, Node } from "@xyflow/react"

const NODE_WIDTH = 220
const NODE_HEIGHT = 96

export type LayoutDirection = "LR" | "TB"

export function autoLayout(
  nodes: Node[],
  edges: Edge[],
  direction: LayoutDirection = "LR",
): { nodes: Node[]; edges: Edge[] } {
  if (nodes.length === 0) return { nodes, edges }

  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: direction,
    nodesep: 60,        // gap between siblings
    ranksep: 80,        // gap between ranks
    marginx: 40,
    marginy: 40,
  })

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  // dagre returns the centre of each node; React Flow expects the top-left.
  const positionedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: (pos?.x ?? 0) - NODE_WIDTH / 2,
        y: (pos?.y ?? 0) - NODE_HEIGHT / 2,
      },
      // Tell React Flow where to anchor handles for LR vs TB layouts.
      targetPosition: direction === "LR" ? "left" : "top",
      sourcePosition: direction === "LR" ? "right" : "bottom",
    }
  }) as Node[]

  return { nodes: positionedNodes, edges }
}
