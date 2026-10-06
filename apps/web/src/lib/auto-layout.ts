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

const NODE_WIDTH = 240
const NODE_HEIGHT = 110

export type LayoutDirection = "LR" | "TB"

/**
 * Kahn's algorithm, mirroring the runtime's `_topological_sort`
 * (apps/api/app/runtime/dag_runner.py). Returns the ids it could not order —
 * blocks in, or downstream of, a cycle. Empty means the graph is a DAG.
 */
export function findCycleNodeIds(nodes: Node[], edges: Edge[]): string[] {
  const inDegree = new Map(nodes.map(n => [n.id, 0]))
  const adjacency = new Map<string, string[]>()
  for (const e of edges) {
    if (!inDegree.has(e.source) || !inDegree.has(e.target)) continue
    inDegree.set(e.target, inDegree.get(e.target)! + 1)
    adjacency.set(e.source, [...(adjacency.get(e.source) ?? []), e.target])
  }
  const queue = nodes.filter(n => inDegree.get(n.id) === 0).map(n => n.id)
  const ordered = new Set<string>()
  while (queue.length) {
    const id = queue.shift()!
    ordered.add(id)
    for (const next of adjacency.get(id) ?? []) {
      inDegree.set(next, inDegree.get(next)! - 1)
      if (inDegree.get(next) === 0) queue.push(next)
    }
  }
  return nodes.filter(n => !ordered.has(n.id)).map(n => n.id)
}

export function autoLayout(
  nodes: Node[],
  edges: Edge[],
  direction: LayoutDirection = "TB",
): { nodes: Node[]; edges: Edge[]; cycleNodeIds: string[] } {
  if (nodes.length === 0) return { nodes, edges, cycleNodeIds: [] }
  // Cycles are laid out anyway (dagre's greedy acyclicer reverses a minimal
  // edge set) but reported, because the runtime refuses to execute them.
  const cycleNodeIds = findCycleNodeIds(nodes, edges)

  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: direction,
    nodesep: 60,        // horizontal gap between siblings in TB mode
    ranksep: 70,        // vertical gap between ranks
    marginx: 60,
    marginy: 60,
    acyclicer: "greedy",
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

  return { nodes: positionedNodes, edges, cycleNodeIds }
}
