import { SECRET_KEY, SECRET_VALUE } from "./secrets"

type GraphNode = { id: string; type?: string; data?: Record<string, unknown> }
type GraphEdge = { source: string; target: string; sourceHandle?: string | null }
export type StoredGraph = { nodes?: GraphNode[]; edges?: GraphEdge[]; annotations?: GraphNode[] }

export interface FieldChange {
  path: string
  before: string
  after: string
  /** Guard / identity / persona / gateway / model routing — reviewers should look twice. */
  governance: boolean
}

export interface NodeChange { id: string; label: string; fields: FieldChange[] }

export interface GraphDiff {
  blocks: { added: NodeChange[]; removed: NodeChange[]; changed: NodeChange[] }
  edges: { added: string[]; removed: string[] }
  notes: { added: NodeChange[]; removed: NodeChange[]; changed: NodeChange[] }
}

const IGNORED = new Set(["runStatus", "liveTurn", "reviewerDim"])
const GOVERNANCE = /guard|identity|persona|gateway|approval|model|provider|budget|max_turns|sandbox|allowlist|permission/i
export const MASK = "••••••"

/** Show secret *references* ({{secrets.X}}) but never secret values. */
function display(path: string, value: string | undefined): string {
  if (value === undefined) return ""
  const key = path.split(".").pop() ?? ""
  return value && !value.startsWith("{{") && (SECRET_KEY.test(key) || SECRET_VALUE.test(value)) ? MASK : value
}

/** Flatten node data to dotted paths (raw values; masking happens at display). */
function flatten(value: unknown, prefix = "", out: Record<string, string> = {}): Record<string, string> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (IGNORED.has(k)) continue
      const path = prefix ? `${prefix}.${k}` : k
      flatten(v, path, out)
    }
  } else if (prefix) {
    out[prefix] = typeof value === "string" ? value : JSON.stringify(value ?? null)
  }
  return out
}

const label = (n: GraphNode) => (n.data?.label as string) || (n.data?.title as string) || n.id
const edgeKey = (e: GraphEdge) => `${e.source} → ${e.target}${e.sourceHandle ? ` (${e.sourceHandle})` : ""}`

function diffNodes(before: GraphNode[] = [], after: GraphNode[] = []) {
  const prev = new Map(before.map(n => [n.id, n]))
  const next = new Map(after.map(n => [n.id, n]))
  const whole = (n: GraphNode): NodeChange => ({ id: n.id, label: label(n), fields: [] })
  const changed: NodeChange[] = []
  for (const [id, n] of next) {
    const p = prev.get(id)
    if (!p) continue
    const a = flatten(p.data)
    const b = flatten(n.data)
    const fields = [...new Set([...Object.keys(a), ...Object.keys(b)])]
      .filter(path => a[path] !== b[path])
      .sort()
      .map(path => ({ path, before: display(path, a[path]), after: display(path, b[path]), governance: GOVERNANCE.test(path) }))
    if (fields.length) changed.push({ id, label: label(n), fields })
  }
  return {
    added: after.filter(n => !prev.has(n.id)).map(whole),
    removed: before.filter(n => !next.has(n.id)).map(whole),
    changed,
  }
}

/** What changed going from `before` to `after` (positions and live-run state ignored). */
export function diffGraphs(before: StoredGraph, after: StoredGraph): GraphDiff {
  const eb = new Set((before.edges ?? []).map(edgeKey))
  const ea = new Set((after.edges ?? []).map(edgeKey))
  return {
    blocks: diffNodes(before.nodes, after.nodes),
    edges: { added: [...ea].filter(k => !eb.has(k)), removed: [...eb].filter(k => !ea.has(k)) },
    notes: diffNodes(before.annotations, after.annotations),
  }
}

export const isEmptyDiff = (d: GraphDiff) =>
  [d.blocks.added, d.blocks.removed, d.blocks.changed, d.edges.added, d.edges.removed, d.notes.added, d.notes.removed, d.notes.changed]
    .every(list => list.length === 0)
