"use client"

import RunInputsModal from "./RunInputsModal"
import type { CanvasRuns, GetToken } from "./hooks/useCanvasRuns"

/** Run-launch modals and the floating test-run status toast. */
export default function RunModals({ workflowId, getToken, wsId, runs }: {
  workflowId: string
  getToken: GetToken
  wsId: string | null
  runs: CanvasRuns
}) {
  const { webhookModal } = runs
  return (
    <>
      {/* #734 pre-run inputs modal — opens when /trigger returns 422 missing_required_inputs */}
      {runs.inputsModalPayload && (
        <RunInputsModal
          open
          workflowId={workflowId}
          getToken={getToken ?? null}
          workspaceId={wsId ?? ""}
          initialInputs={(runs.inputsModalPayload.inputs as Record<string, unknown>) ?? {}}
          onCancel={runs.cancelInputs}
          onConfirm={runs.confirmInputs}
        />
      )}
      {/* Webhook test modal */}
      {webhookModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-4">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Test with a pull request</h2>
              <p className="text-xs text-stone-400 mt-1">
                {runs.webhookRepo ? <>Repo: <span className="font-mono text-stone-600">{runs.webhookRepo}</span></> : "Provide a PR to review."}
              </p>
            </div>
            {!runs.webhookRepo && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">GitHub repo</label>
                <input
                  placeholder="owner/repo"
                  value={runs.webhookRepo}
                  onChange={e => runs.setWebhookRepo(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                />
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">PR number <span className="font-normal text-stone-400">(from the PR URL — e.g. /pull/42)</span></label>
              <input
                autoFocus
                placeholder="42"
                value={runs.webhookPrNumber}
                onChange={e => runs.setWebhookPrNumber(e.target.value)}
                onKeyDown={e => e.key === "Enter" && runs.webhookRepo && runs.webhookPrNumber && runs.startWebhookRun(webhookModal.dryRun, runs.webhookRepo, runs.webhookPrNumber)}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => runs.setWebhookModal(null)}
                className="px-4 py-2 text-xs text-stone-500 hover:text-stone-700 rounded-lg hover:bg-stone-100 transition-colors"
              >Cancel</button>
              <button
                onClick={() => runs.startWebhookRun(webhookModal.dryRun, runs.webhookRepo, runs.webhookPrNumber)}
                disabled={!runs.webhookRepo.includes("/") || !runs.webhookPrNumber}
                className="px-4 py-2 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 disabled:opacity-40 transition-colors"
              >Run review</button>
            </div>
          </div>
        </div>
      )}

      {runs.testRunId && (() => {
        const failed = runs.testRunStatus === "failed" || runs.testRunStatus === "cancelled"
        const done = runs.testRunStatus === "succeeded"
        const active = runs.testRunStatus === "pending" || runs.testRunStatus === "running"
        const color = failed ? "red" : done ? "emerald" : "indigo"
        const statusLabel = runs.testRunStatus === "pending" ? "Queued…"
          : runs.testRunStatus === "running" ? "Running…"
          : runs.testRunStatus === "succeeded" ? "Succeeded"
          : runs.testRunStatus === "failed" ? "Failed"
          : runs.testRunStatus ?? "Starting…"
        return (
          <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 bg-${color}-50 border border-${color}-200 rounded-xl px-4 py-3 shadow-lg max-w-sm`}>
            <span className="text-base shrink-0">
              {active ? <span className="inline-block animate-spin">⚙</span> : done ? "✓" : "✕"}
            </span>
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-semibold text-${color}-800`}>⚗ Test run · {statusLabel}</p>
              <p className={`text-xs text-${color}-600 truncate font-mono`}>{runs.testRunId.slice(0, 8)}…</p>
            </div>
            <a
              href={`/workflows/${workflowId}/runs/${runs.testRunId}`}
              className={`shrink-0 text-xs font-medium text-${color}-700 hover:text-${color}-900 underline underline-offset-2`}
            >
              View →
            </a>
            <button
              onClick={runs.dismissTestRun}
              className={`shrink-0 text-${color}-400 hover:text-${color}-700 text-sm`}
            >✕</button>
          </div>
        )
      })()}

      {runs.testTriggerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-4">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">⚗ Dry Run</h2>
              <p className="text-xs text-stone-500 mt-1">
                This fires a real run using a built-in dummy payload. All artifacts (branches, PRs, files) are prefixed with <span className="font-mono font-medium text-stone-700">[TEST]</span> — safe to close without merging.
              </p>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs text-amber-800">
              The agent will execute against your connected repo using your vault credentials.
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-700">PR number <span className="text-stone-400 font-normal">(optional — overrides test payload)</span></label>
              <input
                type="number"
                min="1"
                placeholder="e.g. 246"
                value={runs.testPrNumber}
                onChange={e => runs.setTestPrNumber(e.target.value)}
                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-xs text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-400"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-700">
                Turn budget <span className="text-stone-400 font-normal">(optional — overrides default)</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="1"
                  max="200"
                  placeholder={`default${runs.preflight ? ` · est. ${runs.preflight.suggestedTurns}` : ""}`}
                  value={runs.testMaxTurns}
                  onChange={e => runs.setTestMaxTurns(e.target.value)}
                  className="w-full border border-stone-200 rounded-lg px-3 py-2 text-xs text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-400"
                />
              </div>
              {runs.preflight && (
                <p className="text-xs text-stone-400">Estimated {runs.preflight.suggestedTurns} turns based on payload complexity.</p>
              )}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => runs.setTestTriggerModal(false)}
                className="px-4 py-2 text-xs text-stone-500 hover:text-stone-700 rounded-lg hover:bg-stone-100 transition-colors"
              >Cancel</button>
              <button
                onClick={runs.startTestTrigger}
                className="px-4 py-2 text-xs font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors"
              >Fire test run</button>
            </div>
          </div>
        </div>
      )}

    </>
  )
}
