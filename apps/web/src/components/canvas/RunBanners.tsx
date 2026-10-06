"use client"

import { useRouter } from "next/navigation"
import type { CanvasRuns } from "./hooks/useCanvasRuns"

/** Bottom banners: missing vault, preflight turn budget, validation errors. */
export default function RunBanners({ workflowId, selectedEnvId, runs, onFocusNode }: {
  workflowId: string
  selectedEnvId: string
  runs: CanvasRuns
  onFocusNode: (nodeId: string) => void
}) {
  const router = useRouter()
  return (
    <>
      {/* No-environment warning banner — only shown when no higher-priority banner is active */}
      {!selectedEnvId && runs.validationErrors.length === 0 && !runs.preflight && (
        <div className="shrink-0 border-t border-amber-200 bg-amber-50 px-5 py-2.5 flex items-center gap-2">
          <span className="text-amber-600 text-sm">⚠</span>
          <p className="text-xs text-amber-800 flex-1">
            <span className="font-semibold">No vault assigned</span> — credentials won&apos;t be available when this workflow runs.{" "}
            Select one from the dropdown above, or{" "}
            <a href="/settings" className="underline font-medium hover:text-amber-900">add a vault in Settings</a> first.
          </p>
        </div>
      )}

      {/* Preflight turn-budget banner — only shown when no validation errors override it */}
      {runs.preflight && runs.validationErrors.length === 0 && (
        <div className="shrink-0 border-t border-amber-200 bg-amber-50 px-5 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-amber-800 mb-1">
                ⚠ Estimated {runs.preflight.suggestedTurns} turns needed — default is 25
              </p>
              {runs.preflight.files.length > 0 && (
                <p className="text-xs text-amber-700 mb-2 font-mono truncate">
                  Files likely to be modified: {runs.preflight.files.join(", ")}
                </p>
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => runs.confirmPreflight(runs.preflight!.suggestedTurns)}
                  className="text-xs font-semibold bg-amber-600 text-white px-3 py-1.5 rounded-lg hover:bg-amber-700 transition-colors"
                >
                  Run with {runs.preflight.suggestedTurns} turns
                </button>
                <button
                  onClick={() => runs.confirmPreflight(undefined)}
                  className="text-xs text-amber-700 hover:text-amber-900 px-2 py-1.5"
                >
                  Run anyway (25 turns)
                </button>
                <button onClick={runs.cancelPreflight} className="text-xs text-amber-400 hover:text-amber-600 ml-auto">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Validation errors */}
      {runs.validationErrors.length > 0 && (
        <div className="shrink-0 border-t border-red-200 bg-red-50 px-5 py-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold text-red-700 mb-1.5">
                Fix {runs.validationErrors.length} issue{runs.validationErrors.length > 1 ? "s" : ""} before running
              </p>
              <div className="flex flex-wrap gap-x-5 gap-y-1">
                {runs.validationErrors.map((e) => (
                  <button
                    key={e.blockId}
                    onClick={() => {
                      if (e.blockId === "__env__") {
                        router.push(`/workflows/${workflowId}/settings`)
                        return
                      }
                      onFocusNode(e.blockId)
                    }}
                    className="text-xs text-red-600 hover:text-red-800 hover:underline text-left"
                  >
                    <span className="font-medium">{e.label}</span>
                    <span className="text-red-400"> — {e.message}</span>
                  </button>
                ))}
              </div>
            </div>
            <button onClick={() => runs.setValidationErrors([])} aria-label="Close" className="text-red-300 hover:text-red-500 text-lg leading-none shrink-0 mt-0.5">×</button>
          </div>
        </div>
      )}
    </>
  )
}
