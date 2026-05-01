import Link from "next/link"

interface Run {
  id: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

async function getRuns(workflowId: string): Promise<Run[]> {
  try {
    const res = await fetch(
      `${process.env.API_URL}/workflows/${workflowId}/runs`,
      { cache: "no-store" }
    )
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
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

const STATUS_STYLES: Record<string, string> = {
  pending:   "bg-stone-100 text-stone-500",
  running:   "bg-blue-100 text-blue-700",
  succeeded: "bg-green-100 text-green-700",
  failed:    "bg-red-100 text-red-700",
}

export default async function RunsPage({ params }: { params: { id: string } }) {
  const [workflow, runs] = await Promise.all([
    getWorkflow(params.id),
    getRuns(params.id),
  ])

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href={`/workflows/${params.id}`} className="text-stone-400 hover:text-stone-700 text-sm">←</Link>
          <span className="font-semibold text-stone-900">{workflow?.name ?? "Agent"}</span>
          <span className="text-xs text-stone-400">/ Runs</span>
        </div>
        <Link
          href={`/workflows/${params.id}`}
          className="rounded-lg bg-stone-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
        >
          Edit agent
        </Link>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <h2 className="text-xl font-semibold text-stone-900 mb-6">Run history</h2>

        {runs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
            <p className="text-stone-500 text-sm">No runs yet.</p>
            <Link
              href={`/workflows/${params.id}`}
              className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:underline"
            >
              Open canvas to start a test run
            </Link>
          </div>
        ) : (
          <div className="grid gap-2">
            {runs.map((run) => (
              <Link
                key={run.id}
                href={`/workflows/${params.id}/runs/${run.id}`}
                className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[run.status] ?? STATUS_STYLES.pending}`}>
                    {run.status}
                  </span>
                  <span className="text-sm text-stone-700 font-mono">{run.id.slice(0, 8)}…</span>
                  {run.triggered_by && (
                    <span className="text-xs text-stone-400">{run.triggered_by}</span>
                  )}
                </div>
                <span className="text-xs text-stone-400">
                  {new Date(run.created_at).toLocaleString()}
                </span>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
