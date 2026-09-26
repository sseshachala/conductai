"use client"

import { useRef, type ReactNode } from "react"
import { Maximize2, X } from "lucide-react"

export function ResultTableView({ children }: { children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  return <div style={{ minWidth: 0, maxWidth: "100%", margin: "8px 0" }}>
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 4 }}>
      <button ref={trigger} type="button" className="btn btn-ghost btn-sm" title="Expand table" aria-label="Expand table"
        onClick={() => dialog.current?.showModal()}><Maximize2 size={16} /></button>
    </div>
    <div role="region" aria-label="Result table" tabIndex={0} style={{ overflowX: "auto", maxWidth: "100%" }}>{children}</div>
    <dialog ref={dialog} aria-label="Expanded result table" onClose={() => trigger.current?.focus()}
      onCancel={e => e.stopPropagation()}
      onKeyDown={e => { if (e.key === "Escape") e.stopPropagation() }}
      style={{ width: "calc(100vw - 32px)", maxWidth: "1600px", maxHeight: "calc(100dvh - 32px)", padding: 16,
        border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <strong>Results</strong>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Close expanded table" title="Close expanded table"
          onClick={() => dialog.current?.close()}><X size={18} /></button>
      </div>
      <div role="region" aria-label="Expanded table contents" tabIndex={0} style={{ overflow: "auto", maxHeight: "calc(100dvh - 140px)" }}>{children}</div>
    </dialog>
  </div>
}
