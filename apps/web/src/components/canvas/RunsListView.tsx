"use client"

import { useRouter } from "next/navigation"
import StatusBadge from "@/components/runs/StatusBadge"
import { effectiveStatus } from "@/lib/runUtils"
import type { CanvasRuns } from "./hooks/useCanvasRuns"

export default function RunsListView({ workflowId, workflowName, runs }: {
  workflowId: string
  workflowName: string
  runs: CanvasRuns
}) {
  const router = useRouter()
  return (
    <div className="flex-1 overflow-auto px-6 py-8">
      <div className="mx-auto max-w-3xl flex items-center justify-between mb-4">
        <p className="text-sm font-semibold text-stone-700">{workflowName}</p>
        <button
          onClick={runs.fetchRuns}
          className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 hover:border-stone-300 rounded-lg px-2.5 py-1 transition-colors"
        >
          Refresh
        </button>
      </div>
      {runs.runsLoading ? (
        <p className="text-sm text-stone-400">Loading…</p>
      ) : runs.runs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
          <p className="text-stone-500 text-sm">No runs yet.</p>
        </div>
      ) : (
        <div className="mx-auto max-w-3xl grid gap-2">
          {runs.runs.map(run => {
            return (
              <button
                key={run.id}
                onClick={() => router.push(`/workflows/${workflowId}/runs/${run.id}`)}
                className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all text-left w-full"
              >
                <div className="flex items-center gap-3">
                  <StatusBadge status={effectiveStatus(run)} />
                  <span className="text-sm text-stone-700 font-mono">{run.id.slice(0, 8)}…</span>
                  {run.triggered_by && (
                    <span className="text-xs text-stone-400">{run.triggered_by}</span>
                  )}
                </div>
                <span className="text-xs text-stone-400">
                  {new Date(run.created_at).toLocaleString()}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
