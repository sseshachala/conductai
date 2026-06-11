"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Submission {
  slug: string
  structural_score: number
  quality_score: number
  grade: string
  status: "pending" | "promoted" | "needs_work"
  eval_run_at: string | null
}

const GRADE_STYLES: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-700",
  B: "bg-blue-100  text-blue-700",
  C: "bg-amber-100  text-amber-700",
  D: "bg-orange-100 text-orange-700",
  F: "bg-red-100    text-red-700",
}

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

export default function PlaybookQueuePage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <PlaybookQueueWithAuth />
  return <PlaybookQueueContent getToken={null} />
}

function PlaybookQueueWithAuth() {
  const { getToken } = useAuth()
  return <PlaybookQueueContent getToken={getToken} />
}

function PlaybookQueueContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [loading, setLoading] = useState(true)
  const [actionInFlight, setActionInFlight] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function authHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const workspaceId = getWorkspaceId()
    if (workspaceId) headers["X-Workspace-Id"] = workspaceId
    return headers
  }

  const loadSubmissions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const headers = await authHeaders()
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/playbooks/submissions?status=pending`,
        { headers }
      )
      if (!res.ok) {
        setError(`Could not load submissions (${res.status})`)
        return
      }
      const data: Submission[] = await res.json()
      setSubmissions(data)
    } catch {
      setError("Network error loading submissions.")
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { loadSubmissions() }, [loadSubmissions])

  async function updateStatus(slug: string, status: "promoted" | "needs_work") {
    setActionInFlight(slug)
    try {
      const headers = await authHeaders()
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/playbooks/${slug}/submission`,
        {
          method: "PATCH",
          headers,
          body: JSON.stringify({ status }),
        }
      )
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setError(`Action failed: ${err.detail ?? res.status}`)
        return
      }
      // Remove from pending list immediately
      setSubmissions(prev => prev.filter(s => s.slug !== slug))
    } catch {
      setError("Network error. Please try again.")
    } finally {
      setActionInFlight(null)
    }
  }

  const pending = submissions.filter(s => s.status === "pending")

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">

        <div className="mb-8">
          <h1 className="text-xl font-semibold text-stone-900">Playbook Queue</h1>
          <p className="text-xs text-stone-400 mt-0.5">
            Review evaluated playbooks and promote or send back for rework.
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-center justify-between gap-3">
            <p className="text-xs text-red-700">{error}</p>
            <button
              onClick={() => setError(null)}
              className="text-xs text-red-500 hover:text-red-700"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        )}

        {loading ? (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 rounded-xl bg-stone-100 animate-pulse" />
            ))}
          </div>
        ) : pending.length === 0 ? (
          <div className="rounded-xl border border-stone-200 bg-white px-6 py-12 text-center">
            <p className="text-sm font-medium text-stone-900 mb-1">Queue is clear</p>
            <p className="text-xs text-stone-400">No playbooks are pending review right now.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {pending.map(sub => (
              <SubmissionRow
                key={sub.slug}
                submission={sub}
                inFlight={actionInFlight === sub.slug}
                onApprove={() => updateStatus(sub.slug, "promoted")}
                onReject={() => updateStatus(sub.slug, "needs_work")}
              />
            ))}
          </div>
        )}

        <p className="mt-4 text-[10px] text-stone-300 text-right">
          {pending.length > 0 ? `${pending.length} pending` : ""}
        </p>
      </div>
    </AppShell>
  )
}

function SubmissionRow({
  submission,
  inFlight,
  onApprove,
  onReject,
}: {
  submission: Submission
  inFlight: boolean
  onApprove: () => void
  onReject: () => void
}) {
  const gradeStyle = GRADE_STYLES[submission.grade] ?? "bg-stone-100 text-stone-500"
  const evalDate = submission.eval_run_at
    ? new Date(submission.eval_run_at).toLocaleDateString("en-GB", {
        day: "numeric", month: "short", year: "numeric",
      })
    : null

  return (
    <div className="rounded-xl border border-stone-200 bg-white px-5 py-4 flex items-center gap-4 hover:border-stone-300 transition-colors">

      {/* Grade badge */}
      <span
        className={`text-sm font-bold px-2.5 py-1 rounded-lg tabular-nums shrink-0 ${gradeStyle}`}
        title={`Quality grade: ${submission.grade}`}
      >
        {submission.grade}
      </span>

      {/* Slug and scores */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-stone-900 truncate">{submission.slug}</p>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-[10px] text-stone-400">
            Structural <span className="text-stone-600 font-medium">{submission.structural_score}</span>
          </span>
          <span className="text-[10px] text-stone-400">
            Quality <span className="text-stone-600 font-medium">{submission.quality_score}</span>
          </span>
          {evalDate && (
            <span className="text-[10px] text-stone-300">Evaluated {evalDate}</span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={onReject}
          disabled={inFlight}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 hover:border-stone-300 disabled:opacity-40 transition-colors"
        >
          Needs work
        </button>
        <button
          onClick={onApprove}
          disabled={inFlight}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-40 transition-colors"
        >
          {inFlight ? "Saving…" : "Promote"}
        </button>
      </div>
    </div>
  )
}
