import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react"
import type { Edge, Node } from "@xyflow/react"

type Snapshot = { nodes: Node[]; edges: Edge[] }

/**
 * Identity of an undoable state: structure, config, position, explicit size
 * (note resizing), z-order and lock state. Selection and measured size are excluded so clicking around never creates
 * history entries. Mid-drag positions are collapsed by the snapshot debounce.
 */
export function historyKey(nodes: Node[], edges: Edge[]): string {
  const nodeKey = nodes.map(n =>
    `${n.id}:${Math.round(n.position.x)},${Math.round(n.position.y)}:${n.width ?? ""}x${n.height ?? ""}:${n.zIndex ?? 0}:${n.draggable ?? ""}:${JSON.stringify(n.data)}`,
  ).join("|")
  const edgeKey = edges.map(e => `${e.id}:${e.source}:${e.target}`).join("|")
  return nodeKey + "||" + edgeKey
}

export function useUndoHistory(
  nodes: Node[],
  edges: Edge[],
  setNodes: (nodes: Node[]) => void,
  setEdges: (edges: Edge[]) => void,
  { disabled, isFirstLoad }: { disabled: boolean; isFirstLoad: MutableRefObject<boolean> },
) {
  const historyRef = useRef<Snapshot[]>([])
  const historyIdxRef = useRef(-1)
  const skipHistoryRef = useRef(false)
  const historyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)

  const latestRef = useRef<Snapshot>({ nodes, edges })
  latestRef.current = { nodes, edges }

  const commit = useCallback(({ nodes, edges }: Snapshot) => {
    const prev = historyRef.current[historyIdxRef.current]
    if (prev && historyKey(nodes, edges) === historyKey(prev.nodes, prev.edges)) return
    // Truncate redo branch
    const trimmed = historyRef.current.slice(0, historyIdxRef.current + 1)
    trimmed.push({ nodes: [...nodes], edges: [...edges] })
    if (trimmed.length > 50) trimmed.shift()
    historyRef.current = trimmed
    historyIdxRef.current = trimmed.length - 1
    setCanUndo(historyIdxRef.current > 0)
    setCanRedo(false)
  }, [])

  /** Commit an edit still inside the debounce window, so undo/redo act on it. */
  const flushPending = useCallback(() => {
    if (!historyTimerRef.current) return
    clearTimeout(historyTimerRef.current)
    historyTimerRef.current = null
    commit(latestRef.current)
  }, [commit])

  // History snapshot — debounced 400ms so one drag / paste / layout = one entry
  useEffect(() => {
    if (disabled || skipHistoryRef.current) return
    if (isFirstLoad.current) {
      // Seed the loaded graph as the baseline so the first edit is undoable.
      historyRef.current = [{ nodes, edges }]
      historyIdxRef.current = 0
      return
    }
    if (historyTimerRef.current) clearTimeout(historyTimerRef.current)
    historyTimerRef.current = setTimeout(() => {
      historyTimerRef.current = null
      commit({ nodes, edges })
    }, 400)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges])

  const restore = useCallback((idx: number) => {
    skipHistoryRef.current = true
    historyIdxRef.current = idx
    const snap = historyRef.current[idx]
    setNodes([...snap.nodes])
    setEdges([...snap.edges])
    setCanUndo(idx > 0)
    setCanRedo(idx < historyRef.current.length - 1)
    requestAnimationFrame(() => { skipHistoryRef.current = false })
  }, [setNodes, setEdges])

  const undo = useCallback(() => {
    flushPending()
    if (historyIdxRef.current > 0) restore(historyIdxRef.current - 1)
  }, [flushPending, restore])

  const redo = useCallback(() => {
    flushPending()
    if (historyIdxRef.current < historyRef.current.length - 1) restore(historyIdxRef.current + 1)
  }, [flushPending, restore])

  return { undo, redo, canUndo, canRedo }
}
