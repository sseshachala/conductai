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
 * Canvas keyboard shortcuts (Cmd on macOS, Ctrl elsewhere):
 *   Z / Shift+Z / Y  undo / redo / redo
 *   P                node search
 *   Shift+] / Shift+[  bring to front / send to back
 */
export function useCanvasShortcuts(shortcuts: Shortcuts) {
  const ref = useRef(shortcuts)
  ref.current = shortcuts

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      const { undo, redo, openSearch, zOrder, editable } = ref.current
      const key = e.key.toLowerCase()
      if (key === "p" && !e.shiftKey) { e.preventDefault(); openSearch(); return }
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return
      if (!editable) return
      if (key === "z" && !e.shiftKey) { e.preventDefault(); undo() }
      else if ((key === "z" && e.shiftKey) || key === "y") { e.preventDefault(); redo() }
      // e.code, not e.key: Shift+] reports "}" on US layouts and other glyphs elsewhere
      else if (e.shiftKey && e.code === "BracketRight") { e.preventDefault(); zOrder("front") }
      else if (e.shiftKey && e.code === "BracketLeft") { e.preventDefault(); zOrder("back") }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [])
}
