import type { Edge, Node } from "@xyflow/react"
import { isAnnotation } from "./annotations"
import { SECRET_KEY, SECRET_VALUE } from "./secrets"

/** Marker so a paste only accepts payloads this canvas produced. */
const KIND = "conduct/canvas-selection"
const VERSION = 1

/** Live-run decoration that must never travel with a copied block. */
const RUNTIME_KEYS = new Set(["runStatus", "liveTurn", "reviewerDim"])

export function stripSecrets(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripSecrets)
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (RUNTIME_KEYS.has(k)) continue
      if (typeof v === "string" && (SECRET_KEY.test(k) || SECRET_VALUE.test(v))) continue
      out[k] = stripSecrets(v)
    }
    return out
  }
  return typeof value === "string" && SECRET_VALUE.test(value) ? "" : value
}

export interface ClipboardPayload {
  kind: typeof KIND
  v: number
  nodes: Node[]
  edges: Edge[]
}

/** Selected nodes plus only the edges whose endpoints are both selected. */
export function serializeSelection(nodes: Node[], edges: Edge[]): ClipboardPayload | null {
  const picked = nodes.filter(n => n.selected)
  if (picked.length === 0) return null
  const ids = new Set(picked.map(n => n.id))
  return {
    kind: KIND,
    v: VERSION,
    nodes: picked.map(({ id, type, position, data, width, height, zIndex, style }) =>
      ({ id, type, position, data: stripSecrets(data) as Record<string, unknown>, width, height, zIndex, style })),
    edges: edges
      .filter(e => ids.has(e.source) && ids.has(e.target))
      .map(({ id, source, target, sourceHandle, targetHandle, type, markerEnd, style }) =>
        ({ id, source, target, sourceHandle, targetHandle, type, markerEnd, style })),
  }
}

export function parsePayload(text: string): ClipboardPayload | null {
  try {
    const p = JSON.parse(text)
    if (p?.kind !== KIND || p.v !== VERSION || !Array.isArray(p.nodes) || !Array.isArray(p.edges)) return null
    return p as ClipboardPayload
  } catch {
    return null
  }
}

/**
 * Fresh ids, edges remapped to them, positions offset, pasted nodes selected.
 * Untrusted input (clipboard), so secrets are stripped again on the way in.
 * ponytail: `{{blocks.<id>…}}` references inside copied config are not
 * rewritten — ids like "triage" would make blind text replacement corrupt prompts.
 */
export function materializePaste(payload: ClipboardPayload, offset: number, newId: (n: Node) => string): { nodes: Node[]; edges: Edge[] } {
  const idMap = new Map<string, string>()
  const nodes = payload.nodes.map(n => {
    const id = newId(n)
    idMap.set(n.id, id)
    return {
      ...n,
      id,
      position: { x: (n.position?.x ?? 0) + offset, y: (n.position?.y ?? 0) + offset },
      data: stripSecrets(n.data) as Record<string, unknown>,
      selected: true,
    }
  })
  const edges = payload.edges
    .filter(e => idMap.has(e.source) && idMap.has(e.target))
    .map(e => {
      const source = idMap.get(e.source)!
      const target = idMap.get(e.target)!
      return { ...e, id: `e-${source}-${target}-${e.sourceHandle ?? ""}`, source, target }
    })
  return { nodes, edges }
}

export const pasteId = (n: Node) =>
  `${isAnnotation(n) ? "note" : "block"}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
