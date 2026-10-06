import { useEffect, useRef } from "react"
import type { Edge, Node } from "@xyflow/react"
import { materializePaste, parsePayload, pasteId, serializeSelection, type ClipboardPayload } from "@/lib/canvas/clipboard"
import { withLockState } from "@/lib/canvas/annotations"

const OFFSET = 40

function isTextTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)
}

interface Options {
  nodes: Node[]
  edges: Edge[]
  setNodes: (updater: (nds: Node[]) => Node[]) => void
  setEdges: (updater: (eds: Edge[]) => Edge[]) => void
  /** Viewers may copy; only editors may cut / paste / duplicate. */
  editable: boolean
}

/**
 * Copy / cut / paste / duplicate for canvas selections via the native
 * clipboard events (no permission prompt). Each insert is one setNodes +
 * setEdges in the same tick, so it lands as a single undo entry.
 */
export function useCanvasClipboard(opts: Options) {
  const ref = useRef(opts)
  ref.current = opts
  const pasteCount = useRef(0)

  const insert = (payload: ClipboardPayload, offset: number) => {
    const { setNodes, setEdges } = ref.current
    const pasted = materializePaste(payload, offset, pasteId)
    setNodes(nds => [...nds.map(n => (n.selected ? { ...n, selected: false } : n)), ...pasted.nodes.map(withLockState)])
    setEdges(eds => [...eds, ...pasted.edges])
  }

  useEffect(() => {
    function onCopy(e: ClipboardEvent, cut = false) {
      if (isTextTarget(e.target) || window.getSelection()?.toString()) return
      const { nodes, edges, setNodes, setEdges, editable } = ref.current
      const payload = serializeSelection(nodes, edges)
      if (!payload || !e.clipboardData) return
      e.clipboardData.setData("text/plain", JSON.stringify(payload))
      e.preventDefault()
      pasteCount.current = 0
      if (cut && editable) {
        const ids = new Set(payload.nodes.map(n => n.id))
        setNodes(nds => nds.filter(n => !ids.has(n.id)))
        setEdges(eds => eds.filter(ed => !ids.has(ed.source) && !ids.has(ed.target)))
      }
    }
    function onPaste(e: ClipboardEvent) {
      if (!ref.current.editable || isTextTarget(e.target)) return
      const payload = parsePayload(e.clipboardData?.getData("text/plain") ?? "")
      if (!payload) return
      e.preventDefault()
      pasteCount.current += 1
      insert(payload, OFFSET * pasteCount.current)
    }
    const onCut = (e: ClipboardEvent) => onCopy(e, true)
    document.addEventListener("copy", onCopy)
    document.addEventListener("cut", onCut)
    document.addEventListener("paste", onPaste)
    return () => {
      document.removeEventListener("copy", onCopy)
      document.removeEventListener("cut", onCut)
      document.removeEventListener("paste", onPaste)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** Cmd/Ctrl+D — duplicate the selection in place without touching the clipboard. */
  const duplicate = () => {
    if (!ref.current.editable) return
    const payload = serializeSelection(ref.current.nodes, ref.current.edges)
    if (payload) insert(payload, OFFSET)
  }

  return { duplicate }
}
