"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { X } from "lucide-react"
import styles from "./LensResultsLayout.module.css"

type Selection = { id: string; content: ReactNode; trigger: HTMLButtonElement }
const ResultsContext = createContext<{
  selectedId?: string
  open: (selection: Selection) => void
  update: (id: string, content: ReactNode) => void
  close: (id?: string) => void
} | null>(null)

export const useLensResults = () => useContext(ResultsContext)

export function LensResultsLayout({ children, resetKey, onExpandedChange }: {
  children: ReactNode; resetKey?: string | null; onExpandedChange?: (expanded: boolean) => void
}) {
  const [selection, setSelection] = useState<Selection | null>(null)
  const selectionRef = useRef(selection)
  selectionRef.current = selection
  const closeButton = useRef<HTMLButtonElement>(null)
  const open = useCallback((value: Selection) => setSelection(value), [])
  const update = useCallback((id: string, content: ReactNode) => {
    setSelection(prev => prev?.id === id && prev.content !== content ? { ...prev, content } : prev)
  }, [])
  const close = useCallback((id?: string) => {
    const current = selectionRef.current
    if (!current || (id && current.id !== id)) return
    setSelection(null)
    if (current.trigger.isConnected) current.trigger.focus()
  }, [])
  useEffect(() => { setSelection(null) }, [resetKey])
  useEffect(() => { onExpandedChange?.(!!selection) }, [!!selection, onExpandedChange])
  useEffect(() => { if (selection) closeButton.current?.focus() }, [selection?.id])

  return <ResultsContext.Provider value={{ selectedId: selection?.id, open, update, close }}>
    <div className={styles.root}>
      <div className={`${styles.layout} ${selection ? styles.expanded : ""}`}>
        <div className={styles.chat}>{children}</div>
        {selection && <aside className={styles.results} aria-label="Expanded result table"
          onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); close() } }}>
          <div className={styles.header}>
            <strong>Results</strong>
            <button ref={closeButton} type="button" className="btn btn-ghost btn-sm" aria-label="Close results pane" title="Close results pane"
              onClick={() => close()}><X size={18} /></button>
          </div>
          <div role="region" aria-label="Expanded table contents" tabIndex={0} className={styles.content}>{selection.content}</div>
        </aside>}
      </div>
    </div>
  </ResultsContext.Provider>
}
