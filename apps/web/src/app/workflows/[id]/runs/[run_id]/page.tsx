import Link from "next/link"
import RunTrace from "@/components/runs/RunTrace"

async function getRun(workflowId: string, runId: string) {
  try {
    const res = await fetch(
      `${process.env.API_URL}/workflows/${workflowId}/runs/${runId}`,
      { cache: "no-store" }
    )
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

async function getWorkflow(workflowId: string) {
  try {
    const res = await fetch(
      `${process.env.API_URL}/workflows/${workflowId}`,
      { cache: "no-store" }
    )
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export default async function RunDetailPage({
  params,
}: {
  params: { id: string; run_id: string }
}) {
  const [workflow, run] = await Promise.all([
    getWorkflow(params.id),
    getRun(params.id, params.run_id),
  ])

  if (!run) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <p className="text-stone-500">Run not found.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href={`/workflows/${params.id}/runs`} className="text-stone-400 hover:text-stone-700 text-sm">←</Link>
          <span className="font-semibold text-stone-900">{workflow?.name ?? "Agent"}</span>
          <span className="text-xs text-stone-400">/ Runs /</span>
          <span className="font-mono text-xs text-stone-500">{run.id.slice(0, 8)}…</span>
        </div>
        <Link
          href={`/workflows/${params.id}`}
          className="text-xs text-stone-500 hover:text-stone-800 transition-colors"
        >
          Edit agent
        </Link>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-stone-900">Run trace</h2>
          <p className="text-sm text-stone-400 mt-1 font-mono">{run.id}</p>
        </div>

        <div className="bg-white rounded-xl border border-stone-200 p-6">
          <RunTrace
            workflowId={params.id}
            runId={params.run_id}
            initialStatus={run.status}
            initialMeta={{
              triggered_by: run.triggered_by,
              started_at: run.started_at,
              completed_at: run.completed_at,
              paused_at: run.paused_at,
              current_block_id: run.current_block_id,
              workflow_version_id: run.workflow_version_id,
            }}
          />
        </div>
      </main>
    </div>
  )
}
