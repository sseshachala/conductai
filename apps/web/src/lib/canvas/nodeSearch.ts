import type { Node } from "@xyflow/react"

/** Lower is better; null = no match. Substring beats subsequence. */
function fuzzyScore(query: string, text: string): number | null {
  const idx = text.indexOf(query)
  if (idx >= 0) return idx
  let ti = 0
  let gaps = 0
  for (const ch of query) {
    const found = text.indexOf(ch, ti)
    if (found < 0) return null
    gaps += found - ti
    ti = found + 1
  }
  return 1000 + gaps
}

/** Fuzzy search over node label, block type, integration, description and id. */
export function searchNodes(nodes: Node[], query: string, limit = 20): Node[] {
  const q = query.trim().toLowerCase()
  if (!q) return nodes.slice(0, limit)
  const scored: Array<{ node: Node; score: number }> = []
  for (const node of nodes) {
    const d = node.data as Record<string, unknown>
    const fields = [d.label, d.type, d.integration, d.description, node.id]
    let best: number | null = null
    for (const f of fields) {
      if (typeof f !== "string" || !f) continue
      const s = fuzzyScore(q, f.toLowerCase())
      if (s !== null && (best === null || s < best)) best = s
    }
    if (best !== null) scored.push({ node, score: best })
  }
  return scored.sort((a, b) => a.score - b.score).slice(0, limit).map(s => s.node)
}
