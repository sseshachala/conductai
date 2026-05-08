"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AuthButton from "@/components/AuthButton"

interface Workflow {
  id: string
  name: string
  updated_at: string
  last_run_status: string | null
  last_run_at: string | null
}

const RUN_STATUS: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  succeeded: { label: "Last run succeeded", dot: "bg-green-400",  text: "text-green-700",  bg: "bg-green-50"  },
  failed:    { label: "Last run failed",    dot: "bg-red-400",    text: "text-red-600",    bg: "bg-red-50"    },
  running:   { label: "Running now",        dot: "bg-blue-400 animate-pulse", text: "text-blue-700", bg: "bg-blue-50" },
  pending:   { label: "Queued",             dot: "bg-stone-300",  text: "text-stone-500",  bg: "bg-stone-100" },
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function getActiveProject(): string | null {
  if (typeof document === "undefined") return null
  const match = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)
  return match ? match[1] : null
}

export default function WorkflowsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <WorkflowsWithAuth />
  return <WorkflowsContent getToken={null} />
}

function WorkflowsWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()

  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])

  if (!isLoaded) return null
  return <WorkflowsContent getToken={getToken} />
}

function WorkflowsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [projectId, setProjectId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const pid = getActiveProject()
    setProjectId(pid)
    loadWorkflows(pid)
  }, [])

  async function loadWorkflows(pid: string | null) {
    try {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      if (pid) headers["X-Workspace-ID"] = pid

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, { headers })
      if (res.ok) setWorkflows(await res.json())
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/projects" className="text-base font-bold text-stone-900 tracking-tight hover:text-stone-600 transition-colors">
            Delegator
          </Link>
          {projectId && (
            <>
              <span className="text-stone-300">/</span>
              <Link href="/projects" className="text-sm text-stone-500 hover:text-stone-800 transition-colors">
                Switch project
              </Link>
            </>
          )}
        </div>
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
          {clerkEnabled && <AuthButton afterSignOutUrl="/" />}
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-5">
          <h1 className="text-xl font-semibold text-stone-900">Agents</h1>
          <span className="text-xs text-stone-400">{workflows.length} agent{workflows.length !== 1 ? "s" : ""}</span>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 rounded-xl border border-stone-200 bg-white animate-pulse" />
            ))}
          </div>
        ) : workflows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
            <p className="text-stone-800 font-medium mb-1">No agents yet</p>
            <p className="text-stone-400 text-sm mb-6">Build your first AI agent on the canvas</p>
            <Link
              href="/workflows/new"
              className="inline-block rounded-lg bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
            >
              Create your first agent
            </Link>
          </div>
        ) : (
          <div className="grid gap-2">
            {workflows.map((w) => {
              const status = w.last_run_status ? RUN_STATUS[w.last_run_status] : null
              return (
                <Link
                  key={w.id}
                  href={`/workflows/${w.id}`}
                  className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group"
                >
                  <div>
                    <p className="font-semibold text-stone-900 group-hover:text-stone-700 transition-colors">{w.name}</p>
                    <p className="text-xs text-stone-400 mt-0.5">edited {timeAgo(w.updated_at)}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {status ? (
                      <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${status.bg} ${status.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
                        {status.label}
                      </span>
                    ) : (
                      <span className="text-xs text-stone-400 italic">never run</span>
                    )}
                    {w.last_run_at && <span className="text-xs text-stone-400">{timeAgo(w.last_run_at)}</span>}
                    <span className="text-stone-300 group-hover:text-stone-500 transition-colors text-sm">→</span>
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}
