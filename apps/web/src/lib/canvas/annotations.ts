import type { Node } from "@xyflow/react"

/**
 * Sticky-note annotations. They live in React Flow state alongside blocks so
 * they pan/select/undo/copy like any node, but persist under
 * `graph.annotations` — never `graph.nodes` — because every backend reader
 * (compiler, dag_runner, webhooks) iterates `graph.nodes` as executable blocks.
 */
export const ANNOTATION_TYPE = "annotation"

export const ANNOTATION_COLORS = ["yellow", "blue", "green", "pink", "gray"] as const
export type AnnotationColor = (typeof ANNOTATION_COLORS)[number]

export interface AnnotationData extends Record<string, unknown> {
  title: string
  text: string
  color: AnnotationColor
  locked: boolean
}

export const isAnnotation = (n: Node) => n.type === ANNOTATION_TYPE

/** Split React Flow state into what the graph stores in `nodes` vs `annotations`. */
export function splitAnnotations(nodes: Node[]): { blocks: Node[]; annotations: Node[] } {
  const blocks: Node[] = []
  const annotations: Node[] = []
  for (const n of nodes) (isAnnotation(n) ? annotations : blocks).push(n)
  return { blocks, annotations }
}

/** Locked notes can't be dragged; React Flow reads `draggable` per node. */
export function withLockState(n: Node): Node {
  return isAnnotation(n) ? { ...n, draggable: !(n.data as AnnotationData).locked } : n
}

export function newAnnotation(id: string, position: { x: number; y: number }): Node {
  return {
    id,
    type: ANNOTATION_TYPE,
    position,
    width: 240,
    height: 160,
    zIndex: -1, // behind blocks by default; z-order controls can raise it
    data: { title: "", text: "", color: "yellow", locked: false } satisfies AnnotationData,
  }
}
