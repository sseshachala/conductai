"use client"

import { useEffect, useId, useRef, type ReactNode } from "react"
import { Maximize2 } from "lucide-react"
import { useLensResults } from "./LensResultsLayout"

export function ResultTableView({ children }: { children: ReactNode }) {
  const id = useId()
  const results = useLensResults()
  const trigger = useRef<HTMLButtonElement>(null)
  const update = results?.update
  const close = results?.close
  useEffect(() => { update?.(id, children) }, [id, children, update])
  useEffect(() => () => close?.(id), [id, close])
  return <div style={{ minWidth: 0, maxWidth: "100%", margin: "8px 0" }}>
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 4 }}>
      {results && <button ref={trigger} type="button" className="btn btn-ghost btn-sm" title="Expand table" aria-label="Expand table"
        aria-expanded={results.selectedId === id}
        onClick={() => { if (trigger.current) results.open({ id, content: children, trigger: trigger.current }) }}><Maximize2 size={16} /></button>}
    </div>
    <div role="region" aria-label="Result table" tabIndex={0} style={{ overflowX: "auto", maxWidth: "100%" }}>{children}</div>
  </div>
}
