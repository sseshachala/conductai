"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"

const TEMPLATES = [
  {
    id: "autopilot_quick",
    label: "Autopilot Quick",
    description: "GitHub issue labeled → implement fix → open PR immediately. No test step — CI runs tests on the PR.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "autopilot_full",
    label: "Autopilot Full",
    description: "GitHub issue labeled → implement fix → run tests with retry → open PR.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "autopilot_approved",
    label: "Autopilot + Approval",
    description: "GitHub issue labeled → implement fix → run tests → human approves in Slack → open PR. Nothing ships without a gate.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "pr_reviewer",
    label: "PR Reviewer",
    description: "Any PR opened → AI reviews the diff for bugs, security issues, and style → posts a review comment on the PR.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "issue_triage",
    label: "Issue Triage",
    description: "New GitHub issue opened → AI classifies type and priority → adds labels → posts a clarifying comment if the issue is vague.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "release_notes",
    label: "Release Notes",
    description: "Git tag pushed → AI reads merged PRs since the last tag → groups by type → writes CHANGELOG entry → posts summary to Slack.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "ci_notify",
    label: "CI Failure Alert",
    description: "CI build fails → AI diagnoses the failed step → posts root cause and suggested fix to Slack. Skips silently on success.",
    tags: ["GitHub", "Slack"],
  },
  {
    id: "incident_responder",
    label: "Incident Responder",
    description: "PagerDuty or OpsGenie alert fires → AI correlates recent commits and deploys → posts root cause hypothesis to #incidents within 60 seconds.",
    tags: ["Slack"],
  },
  {
    id: "dependency_updater",
    label: "Dependency Updater",
    description: "Weekly cron webhook fires → AI scans for outdated patch/minor deps → bumps versions → opens a single clean PR. Never bumps major versions.",
    tags: ["GitHub", "Slack"],
  },
]

function getWorkspaceId(): string | null {
  return document.cookie
    .split("; ")
    .find(r => r.startsWith("delegator_project_id="))
    ?.split("=")[1] ?? null
}

export default function NewWorkflowPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <NewWorkflowWithAuth />
  return <NewWorkflowForm getToken={null} />
}

function NewWorkflowWithAuth() {
  const { getToken } = useAuth()
  return <NewWorkflowForm getToken={getToken} />
}

function NewWorkflowForm({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [name, setName] = useState("")
  const [template, setTemplate] = useState("autopilot_quick")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  async function handleCreate() {
    if (!name.trim()) return
    setLoading(true)
    setError(null)
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name: name.trim(), template }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setError(err.detail ?? `Error ${res.status}`)
        return
      }

      const workflow = await res.json()
      if (!workflow.id) {
        setError("Unexpected response from server")
        return
      }
      router.push(`/workflows/${workflow.id}`)
    } catch {
      setError("Network error — please try again")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center gap-3">
        <Link href="/workflows" className="text-stone-400 hover:text-stone-700 text-sm transition-colors">←</Link>
        <span className="font-semibold text-stone-900">New agent</span>
      </header>

      <main className="mx-auto max-w-xl px-6 py-12">

        {/* Name */}
        <div className="mb-8">
          <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2">
            Agent name
          </label>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
            placeholder="e.g. Story → PR agent"
            className="w-full rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 shadow-sm"
          />
        </div>

        {/* Template picker */}
        <div className="mb-10">
          <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-3">
            Choose a starting point
          </label>
          <div className="grid grid-cols-2 gap-3">
            {TEMPLATES.map(t => (
              <button
                key={t.id}
                onClick={() => setTemplate(t.id)}
                className={`text-left rounded-xl border p-4 transition-all ${
                  template === t.id
                    ? "border-stone-900 bg-white shadow-sm ring-1 ring-stone-900"
                    : "border-stone-200 bg-white hover:border-stone-300"
                }`}
              >
                <p className={`text-sm font-medium mb-1 ${template === t.id ? "text-stone-900" : "text-stone-700"}`}>
                  {t.label}
                </p>
                <p className="text-xs text-stone-400 leading-relaxed">{t.description}</p>
                {t.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2.5">
                    {t.tags.map(tag => (
                      <span key={tag} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="mb-4 text-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-2">{error}</p>
        )}

        {/* Create button */}
        <button
          onClick={handleCreate}
          disabled={!name.trim() || loading}
          className="w-full rounded-xl bg-stone-900 px-4 py-3 text-sm font-medium text-white hover:bg-stone-700 transition-colors disabled:opacity-40"
        >
          {loading ? "Creating…" : "Create agent"}
        </button>

      </main>
    </div>
  )
}
