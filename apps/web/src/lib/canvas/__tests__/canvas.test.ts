import { describe, expect, it, vi } from "vitest"
import type { Edge, Node } from "@xyflow/react"
import { searchNodes } from "../nodeSearch"
import { reorderZ } from "../zOrder"
import { autoLayout, findCycleNodeIds } from "@/lib/auto-layout"
import { historyKey } from "@/components/canvas/hooks/useUndoHistory"

const node = (id: string, data: Record<string, unknown> = {}, extra: Partial<Node> = {}): Node =>
  ({ id, type: "block", position: { x: 0, y: 0 }, data: { label: id, ...data }, ...extra })
const edge = (source: string, target: string): Edge => ({ id: `${source}-${target}`, source, target })

describe("searchNodes", () => {
  const nodes = [
    node("a", { label: "Triage issue", type: "brain" }),
    node("b", { label: "Post summary", type: "output", integration: "slack" }),
    node("c", { label: "Open PR", type: "tool", integration: "github", description: "creates a branch" }),
  ]

  it("matches label, type, integration, description and id", () => {
    expect(searchNodes(nodes, "triage").map(n => n.id)).toEqual(["a"])
    expect(searchNodes(nodes, "slack").map(n => n.id)).toEqual(["b"])
    expect(searchNodes(nodes, "branch").map(n => n.id)).toEqual(["c"])
    expect(searchNodes(nodes, "tool").map(n => n.id)).toEqual(["c"])
  })

  it("fuzzy-matches subsequences and ranks substrings first", () => {
    expect(searchNodes(nodes, "pst sum").map(n => n.id)).toEqual(["b"])
    expect(searchNodes(nodes, "p")[0].id).toBe("b") // "Post…" starts with p; "Open PR" has p at 1
  })

  it("returns everything for an empty query and nothing for a miss", () => {
    expect(searchNodes(nodes, "  ")).toHaveLength(3)
    expect(searchNodes(nodes, "zzz")).toEqual([])
  })
})

describe("reorderZ", () => {
  const nodes = [node("a", {}, { zIndex: 2 }), node("b"), node("c", {}, { zIndex: -1 })]

  it("brings selected nodes above every other node", () => {
    const out = reorderZ(nodes, new Set(["b"]), "front")
    expect(out.find(n => n.id === "b")!.zIndex).toBe(3)
  })

  it("sends selected nodes below every other node", () => {
    const out = reorderZ(nodes, new Set(["a"]), "back")
    expect(out.find(n => n.id === "a")!.zIndex).toBe(-2)
  })

  it("is a no-op for an empty selection", () => {
    expect(reorderZ(nodes, new Set(), "front")).toBe(nodes)
  })
})

describe("cycle-aware layout", () => {
  it("reports no cycle for a DAG", () => {
    expect(findCycleNodeIds([node("a"), node("b"), node("c")], [edge("a", "b"), edge("a", "c")])).toEqual([])
  })

  it("reports blocks in and downstream of a cycle, like the runtime", () => {
    const nodes = [node("t"), node("a"), node("b"), node("d")]
    const edges = [edge("t", "a"), edge("a", "b"), edge("b", "a"), edge("b", "d")]
    expect(findCycleNodeIds(nodes, edges)).toEqual(["a", "b", "d"])
  })

  it("still lays out a cyclic graph and returns the cycle", () => {
    const laid = autoLayout([node("a"), node("b")], [edge("a", "b"), edge("b", "a")])
    expect(laid.cycleNodeIds).toEqual(["a", "b"])
    expect(laid.nodes.every(n => Number.isFinite(n.position.x) && Number.isFinite(n.position.y))).toBe(true)
  })
})

describe("historyKey", () => {
  const base = [node("a")]

  it("changes when a node moves or changes z-order", () => {
    const k = historyKey(base, [])
    expect(historyKey([{ ...base[0], position: { x: 40, y: 0 } }], [])).not.toBe(k)
    expect(historyKey([{ ...base[0], zIndex: 5 }], [])).not.toBe(k)
  })

  it("ignores selection and measured size", () => {
    expect(historyKey([{ ...base[0], selected: true, measured: { width: 10, height: 10 } }], [])).toBe(historyKey(base, []))
  })
})

describe("useUndoHistory", () => {
  it("undo inside the debounce window reverts the pending edit, not the one before it", async () => {
    const { renderHook, act } = await import("@testing-library/react")
    const { useUndoHistory } = await import("@/components/canvas/hooks/useUndoHistory")
    vi.useFakeTimers()
    const isFirstLoad = { current: true }
    const setNodes = vi.fn()
    const setEdges = vi.fn()
    const at = (x: number) => [node("a", {}, { position: { x, y: 0 } })]
    const { result, rerender } = renderHook(
      ({ nodes }) => useUndoHistory(nodes, [], setNodes, setEdges, { disabled: false, isFirstLoad }),
      { initialProps: { nodes: at(0) } },
    )
    isFirstLoad.current = false
    rerender({ nodes: at(100) })
    act(() => { vi.advanceTimersByTime(500) }) // committed: x=100
    rerender({ nodes: at(200) })               // pending: x=200
    act(() => { result.current.undo() })
    expect(setNodes).toHaveBeenLastCalledWith(at(100))
    act(() => { vi.advanceTimersByTime(500) }) // stale timer must not resurrect x=200
    expect(result.current.canRedo).toBe(true)
    vi.useRealTimers()
  })
})
