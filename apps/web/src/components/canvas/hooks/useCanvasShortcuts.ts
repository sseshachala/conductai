import { useEffect, useRef } from "react"

interface Shortcuts {
  undo: () => void
  redo: () => void
  openSearch: () => void
  zOrder: (direction: "front" | "back") => void
  /** Viewers get search only; editing shortcuts are disabled. */
  editable: boolean
}

/**
 * Canvas keyboard shortcuts:
 *   Cmd/Ctrl+Z / Shift+Z / Y   undo / redo / redo
 *   Cmd/Ctrl+P                 node search
 *   Alt+Shift+] / Alt+Shift+[  bring to front / send to back
 * (Cmd+Shift+[ ] switch tabs and Cmd+[ is Back on macOS browsers, so z-order uses Alt.)
 */
export function useCanvasShortcuts(shortcuts: Shortcuts) {
  const ref = useRef(shortcuts)
  ref.current = shortcuts

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const { undo, redo, openSearch, zOrder, editable } = ref.current
      const meta = e.metaKey || e.ctrlKey
      const key = e.key.toLowerCase()
      if (meta && key === "p" && !e.shiftKey) { e.preventDefault(); openSearch(); return }
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return
      if (!editable) return
      // e.code, not e.key: Alt/Shift change the reported glyph per layout
      if (e.altKey && e.shiftKey && !meta && e.code === "BracketRight") { e.preventDefault(); zOrder("front"); return }
      if (e.altKey && e.shiftKey && !meta && e.code === "BracketLeft") { e.preventDefault(); zOrder("back"); return }
      if (!meta) return
      if (key === "z" && !e.shiftKey) { e.preventDefault(); undo() }
      else if ((key === "z" && e.shiftKey) || key === "y") { e.preventDefault(); redo() }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [])
}
