"use client"

import { useEffect, useMemo, useState } from "react"
import type { Node } from "@xyflow/react"
import { searchNodes } from "@/lib/canvas/nodeSearch"

/** Cmd/Ctrl+P palette: fuzzy-find a block and jump to it. Keyboard-only usable. */
export default function NodeSearch({ nodes, onSelect, onClose }: {
  nodes: Node[]
  onSelect: (nodeId: string) => void
  onClose: () => void
}) {
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const results = useMemo(() => searchNodes(nodes, query), [nodes, query])
  const activeIdx = Math.min(active, Math.max(results.length - 1, 0))

  // Return focus to whatever opened the palette (toolbar button or canvas).
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    return () => opener?.focus?.()
  }, [])

  const choose = (node: Node | undefined) => {
    if (!node) return
    onSelect(node.id)
    onClose()
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((activeIdx + 1) % Math.max(results.length, 1)) }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((activeIdx - 1 + results.length) % Math.max(results.length, 1)) }
    else if (e.key === "Enter") { e.preventDefault(); choose(results[activeIdx]) }
    else if (e.key === "Escape") { e.preventDefault(); onClose() }
    // The input is the dialog's only focusable element — keep focus inside (aria-modal).
    else if (e.key === "Tab") { e.preventDefault() }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/20" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Find block"
        className="w-full max-w-md mx-4 bg-white border border-stone-200 rounded-xl shadow-xl overflow-hidden"
        onMouseDown={e => e.stopPropagation()}
      >
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls="node-search-results"
          aria-activedescendant={results[activeIdx] ? `node-search-${results[activeIdx].id}` : undefined}
          aria-label="Search blocks by name, type, integration or id"
          placeholder="Find block…"
          value={query}
          onChange={e => { setQuery(e.target.value); setActive(0) }}
          onKeyDown={onKeyDown}
          className="w-full px-4 py-3 text-sm text-stone-900 border-b border-stone-100 outline-none"
        />
        <ul id="node-search-results" role="listbox" aria-label="Matching blocks" className="max-h-72 overflow-y-auto py-1">
          {results.length === 0 && <li className="px-4 py-3 text-xs text-stone-400">No matching blocks</li>}
          {results.map((node, i) => {
            const d = node.data as Record<string, unknown>
            return (
              <li
                key={node.id}
                id={`node-search-${node.id}`}
                role="option"
                aria-selected={i === activeIdx}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(node)}
                className={`flex items-center justify-between gap-3 px-4 py-2 cursor-pointer ${i === activeIdx ? "bg-stone-100" : ""}`}
              >
                <span className="text-sm text-stone-800 truncate">{(d.label as string) || node.id}</span>
                <span className="shrink-0 text-[11px] text-stone-400 font-mono">
                  {[d.type, d.integration].filter(Boolean).join(" · ")}
                </span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
