import { ALL_COLUMNS, type ColumnKey } from "../common/GuardToolbar"

// Per-column grid weights — kept in one place so ActivityHeader and
// ActivityRow can't drift. Mirrors the historical 8-column template.
// Action cell inherits Input's former budget (1.2fr + 1.8fr = 3fr) so the
// merged cell shows both tool-call name and input_summary comfortably.
export const COL_WEIGHTS: Record<ColumnKey, string> = {
  time: "0.8fr",
  actor: "1.4fr",
  tool: "1fr",
  call: "3fr",
  decision: "0.9fr",
  rule: "0.8fr",
  blast: "0.9fr",
  lifecycle: "0.9fr",
  tokens: "1fr",
}

export function buildGridTemplate(visible: readonly ColumnKey[]): string {
  return visible.map(k => COL_WEIGHTS[k]).join(" ")
}

export function resolveVisible(
  visible: readonly ColumnKey[] | undefined,
  compact: boolean,
): { list: ColumnKey[]; set: Set<ColumnKey> } {
  let list: ColumnKey[]
  if (visible && visible.length > 0) {
    // Preserve canonical column order regardless of the incoming array.
    const inSet = new Set(visible)
    list = ALL_COLUMNS.map(c => c.key).filter(k => inSet.has(k))
    if (list.length === 0) list = ALL_COLUMNS.map(c => c.key)
  } else if (compact) {
    // Legacy compact mode: hide the Tool and Blast columns.
    list = ALL_COLUMNS.map(c => c.key).filter(k => k !== "tool" && k !== "blast")
  } else {
    list = ALL_COLUMNS.map(c => c.key)
  }
  return { list, set: new Set(list) }
}
