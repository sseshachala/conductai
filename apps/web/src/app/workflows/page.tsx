import Link from "next/link"
import AuthButton from "@/components/AuthButton"

async function getWorkflows() {
  try {
    const res = await fetch(`${process.env.API_URL}/workflows`, { cache: "no-store" })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export default async function WorkflowsPage() {
  const workflows = await getWorkflows()

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center justify-between">
        <span className="font-semibold text-stone-900">Delegator</span>
        <div className="flex items-center gap-3">
          <Link href="/settings" className="text-sm text-stone-500 hover:text-stone-800 transition-colors">
            Integrations
          </Link>
          <Link
            href="/workflows/new"
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
          >
            + New agent
          </Link>
          <AuthButton afterSignOutUrl="/sign-in" />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-stone-900">Agents</h1>
          <span className="text-xs text-stone-400">{workflows.length} agent{workflows.length !== 1 ? "s" : ""}</span>
        </div>

        {workflows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
            <p className="text-stone-500 text-sm mb-4">No agents yet.</p>
            <Link
              href="/workflows/new"
              className="inline-block rounded-lg bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
            >
              Create your first agent
            </Link>
          </div>
        ) : (
          <div className="grid gap-2">
            {workflows.map((w: { id: string; name: string; default_mode: string; updated_at: string }) => (
              <Link
                key={w.id}
                href={`/workflows/${w.id}`}
                className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group"
              >
                <div>
                  <p className="font-medium text-stone-900 group-hover:text-indigo-700 transition-colors">{w.name}</p>
                  <p className="text-xs text-stone-400 mt-0.5">{w.default_mode} mode</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-stone-400">
                    {new Date(w.updated_at).toLocaleDateString()}
                  </span>
                  <span className="text-stone-300 group-hover:text-stone-500 transition-colors text-sm">→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
