"use client"

import type { Node } from "@xyflow/react"
import type { BlockNodeData } from "./BlockNode"

/** Non-interactive canvas chrome: error/notice toast, loading skeleton, repo badges, empty state. */
export default function CanvasOverlays({ notice, onDismissNotice, canvasLoading, nodes, githubHookRepo }: {
  notice: string | null
  onDismissNotice: () => void
  canvasLoading: boolean
  nodes: Node[]
  githubHookRepo: string | null
}) {
  return (
    <>
      {notice && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-red-50 border border-red-200 text-red-800 text-xs font-medium px-4 py-2.5 rounded-xl shadow-md max-w-sm">
          <span className="shrink-0">✕</span>
          <span className="flex-1">{notice}</span>
          <button onClick={onDismissNotice} aria-label="Dismiss" className="shrink-0 opacity-50 hover:opacity-100 transition-opacity ml-1">✕</button>
        </div>
      )}
      {canvasLoading && (
        <div className="absolute inset-0 z-10 bg-stone-50 flex items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="flex flex-col gap-1">
                <div className="rounded-xl bg-stone-200 animate-pulse h-14" style={{ width: 212 }} />
                {i < 3 && (
                  <div className="w-0.5 h-4 bg-stone-200 animate-pulse mx-auto" />
                )}
              </div>
            ))}
            <p className="text-xs text-stone-400 mt-3">Loading canvas…</p>
          </div>
        </div>
      )}
      {/* Declarative repo badges — one per allowlisted repo */}
      {(() => {
        const triggerNode = nodes.find(n => (n.data as BlockNodeData).type === "trigger")
        const cfg = triggerNode ? (triggerNode.data as BlockNodeData).config as Record<string, unknown> : null
        const allowlist = (cfg?.repo_allowlist as string) || githubHookRepo || ""
        const repos = allowlist.split(",").map(s => s.trim()).filter(Boolean)
        if (!repos.length) return null
        return (
          <div className="absolute top-3 left-3 z-10 flex flex-col gap-1">
            {repos.map(repo => (
              <a
                key={repo}
                href={`https://github.com/${repo}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 bg-white border border-stone-200 rounded-lg px-2.5 py-1.5 shadow-sm text-stone-600 hover:border-stone-400 hover:text-stone-900 transition-colors"
              >
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5 shrink-0">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
                </svg>
                <span className="font-mono text-[11px] leading-none">{repo}</span>
              </a>
            ))}
          </div>
        )
      })()}
      {!canvasLoading && nodes.length === 0 && (
        <div className="absolute inset-0 z-10 pointer-events-none flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="w-12 h-12 rounded-xl border-2 border-dashed border-stone-300 flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5 text-stone-400"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            </div>
            <p className="text-sm font-medium text-stone-500">Drag a Trigger block to get started</p>
            <p className="text-xs text-stone-400 max-w-[200px]">Blocks are in the left panel — drag them onto the canvas to build your workflow.</p>
          </div>
        </div>
      )}

    </>
  )
}
