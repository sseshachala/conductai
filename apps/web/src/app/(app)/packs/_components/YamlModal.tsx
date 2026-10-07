"use client"

import type { Dispatch, SetStateAction } from "react"
import { type MouseEvent as ReactMouseEvent } from "react"
import { FRIENDLY_NAMES } from "./catalog"

// YAML preview modal
export function YamlModal({
  yamlSlug, setYamlSlug, yamlCache, yamlLoading, openInstallModal,
}: {
  yamlSlug: string
  setYamlSlug: Dispatch<SetStateAction<string | null>>
  yamlCache: Map<string, string>
  yamlLoading: boolean
  openInstallModal: (slug: string) => Promise<void>
}) {
  return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setYamlSlug(null)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 flex flex-col max-h-[80vh]" onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
              <div>
                <p className="text-sm font-semibold text-stone-900">{FRIENDLY_NAMES[yamlSlug] ?? yamlSlug}</p>
                <p className="text-[10px] text-stone-400 font-mono mt-0.5">{yamlSlug}.yaml</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => openInstallModal(yamlSlug)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 transition-colors"
                >
                  + Install
                </button>
                <button onClick={() => setYamlSlug(null)} className="text-stone-400 hover:text-stone-600 text-lg leading-none px-1">×</button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1 p-5">
              {yamlLoading ? (
                <div className="h-48 rounded-lg bg-stone-100 animate-pulse" />
              ) : (
                <pre className="text-[11px] font-mono text-stone-700 leading-relaxed whitespace-pre-wrap break-words">
                  {yamlCache.get(yamlSlug) ?? "YAML not available."}
                </pre>
              )}
            </div>
          </div>
        </div>
  )
}
