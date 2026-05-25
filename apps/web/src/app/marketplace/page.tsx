"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  featured: boolean
}

interface Project {
  id: string
  name: string
}

interface Environment {
  id: string
  name: string
}

interface PlaybookInput {
  label: string
  default: string
  type: "string" | "select"
  options?: string[]
  hint?: string
}

interface Repo {
  full_name: string
}

// Playbooks that need a GitHub webhook registered on a specific repo
const GITHUB_WEBHOOK_SLUGS = new Set([
  "pr_reviewer", "copilot_reviewer", "issue_triage",
  "ci_notify", "release_notes", "security_scanner",
  "autopilot_quick", "autopilot_full", "autopilot_approved",
])

// Playbooks that need manual webhook setup (show instructions instead)
const MANUAL_WEBHOOK_SLUGS = new Set(["incident_responder", "dependency_updater"])

const ALL_TAGS = ["all", "github", "code", "code-review", "ops", "notifications", "approval"]

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

const FRIENDLY_NAMES: Record<string, string> = {
  autopilot_quick:    "Autopilot Quick",
  autopilot_full:     "Autopilot Full",
  autopilot_approved: "Autopilot + Approval",
  pr_reviewer:        "PR Reviewer",
  issue_triage:       "Issue Triage",
  release_notes:      "Release Notes",
  ci_notify:          "CI Failure Alert",
  incident_responder: "Incident Responder",
  dependency_updater: "Dependency Updater",
  copilot_reviewer:   "Copilot / AI PR Reviewer",
  security_scanner:   "Security Scanner",
}

export default function MarketplacePage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <MarketplaceWithAuth />
  return <MarketplaceContent getToken={null} />
}

function MarketplaceWithAuth() {
  const { getToken } = useAuth()
  return <MarketplaceContent getToken={getToken} />
}

function MarketplaceContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const router = useRouter()
  const [playbooks, setPlaybooks] = useState<Playbook[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTag, setActiveTag] = useState("all")
  const [installing, setInstalling] = useState(false)
  // slug → count of installs in this workspace
  const [installedCount, setInstalledCount] = useState<Map<string, number>>(new Map())

  // Install modal state
  const [pendingSlug, setPendingSlug] = useState<string | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>("")
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [selectedEnvId, setSelectedEnvId] = useState<string>("")
  const [playbookInputs, setPlaybookInputs] = useState<Record<string, PlaybookInput>>({})
  const [inputValues, setInputValues] = useState<Record<string, string>>({})
  const [repos, setRepos] = useState<Repo[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>("")
  const [reposLoading, setReposLoading] = useState(false)
  const [webhookError, setWebhookError] = useState<string | null>(null)
  const [lastInstalledId, setLastInstalledId] = useState<string | null>(null)
  const [conflictWarning, setConflictWarning] = useState<string | null>(null)

  async function authHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    return headers
  }

  useEffect(() => {
    async function load() {
      const headers = await authHeaders()
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [pbRes, wfRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks`),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, { headers }),
      ])

      if (pbRes.ok) setPlaybooks(await pbRes.json())

      if (wfRes.ok) {
        const workflows: { id: string; name: string; workspace_id: string }[] = await wfRes.json()
        const counts = new Map<string, number>()
        for (const [slug, friendlyName] of Object.entries(FRIENDLY_NAMES)) {
          const n = workflows.filter(w => w.name === friendlyName).length
          if (n > 0) counts.set(slug, n)
        }
        setInstalledCount(counts)
      }

      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openInstallModal(slug: string) {
    setPendingSlug(slug)
    setProjectsLoading(true)
    try {
      const headers = await authHeaders()
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const promises: Promise<void>[] = [
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${workspaceId}/projects`, { headers }).then(async res => {
          if (res.ok) {
            const data: Project[] = await res.json()
            setProjects(data)
            setSelectedProjectId(data[0]?.id ?? "")
          }
        }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers }).then(async res => {
          if (res.ok) {
            const data: Environment[] = await res.json()
            setEnvironments(data)
            setSelectedEnvId(data[0]?.id ?? "")
          }
        }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks/${slug}`).then(async res => {
          if (res.ok) {
            const data = await res.json()
            const inputs: Record<string, PlaybookInput> = data.inputs ?? {}
            setPlaybookInputs(inputs)
            setInputValues(Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, String(v.default ?? "")])))
          }
        }),
      ]

      if (GITHUB_WEBHOOK_SLUGS.has(slug)) {
        setReposLoading(true)
        promises.push(
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/github/repos`, { headers }).then(async res => {
            if (res.ok) {
              const data: Repo[] = await res.json()
              setRepos(data)
              setSelectedRepo(data[0]?.full_name ?? "")
            }
          }).finally(() => setReposLoading(false))
        )
      }

      await Promise.all(promises)
    } finally {
      setProjectsLoading(false)
    }
  }

  function closeInstallModal() {
    setPendingSlug(null)
    setProjects([])
    setSelectedProjectId("")
    setEnvironments([])
    setSelectedEnvId("")
    setPlaybookInputs({})
    setInputValues({})
    setRepos([])
    setSelectedRepo("")
    setWebhookError(null)
    setConflictWarning(null)
  }

  useEffect(() => {
    if (!pendingSlug || !selectedRepo) { setConflictWarning(null); return }
    const triggerLabel = inputValues["trigger_label"] ?? ""
    authHeaders().then(async headers => {
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId
      const params = new URLSearchParams({ template: pendingSlug, repo: selectedRepo })
      if (triggerLabel) params.set("trigger_label", triggerLabel)
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/conflict-check?${params}`,
        { headers }
      )
      if (res.ok) {
        const data = await res.json()
        if (data.conflicts.length > 0) {
          const msg = data.conflict_type === "label"
            ? `An agent is already watching the "${triggerLabel}" label on ${selectedRepo}. Select a different trigger label above — you can have up to 3 agents on the same repo using different labels.`
            : `This playbook is already installed on ${selectedRepo}. Installing again will run two independent agents on the same events.`
          setConflictWarning(msg)
        } else {
          setConflictWarning(null)
        }
      }
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepo, pendingSlug, inputValues["trigger_label"]])

  async function confirmInstall() {
    if (!pendingSlug) return
    setInstalling(true)
    try {
      const headers = await authHeaders()
      headers["Content-Type"] = "application/json"
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const needsRepo = GITHUB_WEBHOOK_SLUGS.has(pendingSlug)
      const body: Record<string, unknown> = {
        name: FRIENDLY_NAMES[pendingSlug] ?? pendingSlug,
        template: pendingSlug,
      }
      if (selectedProjectId) body.project_id = selectedProjectId
      if (selectedEnvId) body.environment_id = selectedEnvId
      if (needsRepo && selectedRepo) body.repo = selectedRepo
      if (Object.keys(inputValues).length > 0) body.inputs = inputValues

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setWebhookError(`Install failed: ${err.detail ?? res.status}`)
        return
      }
      const wf = await res.json()
      setInstalledCount(prev => new Map(prev).set(pendingSlug, (prev.get(pendingSlug) ?? 0) + 1))
      setLastInstalledId(wf.id)
      if (wf.webhook_error) {
        setWebhookError(wf.webhook_error)
      } else {
        closeInstallModal()
        router.push(`/workflows/${wf.id}`)
      }
    } finally {
      setInstalling(false)
    }
  }

  const filtered = activeTag === "all" ? playbooks : playbooks.filter(p => p.tags.includes(activeTag))

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-xl font-semibold text-stone-900">Playbooks</h1>
          <p className="text-xs text-stone-400 mt-0.5">Pre-built agent workflows — install in one click, configure and run</p>
        </div>

        {/* Tag filters */}
        <div className="flex flex-wrap gap-2 mb-8">
          {ALL_TAGS.map(tag => (
            <button
              key={tag}
              onClick={() => setActiveTag(tag)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                activeTag === tag
                  ? "bg-stone-900 text-white"
                  : "bg-stone-100 text-stone-500 hover:bg-stone-200"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="grid grid-cols-3 gap-4">
            {[1,2,3,4,5,6,7,8,9].map(i => <div key={i} className="h-48 rounded-xl bg-stone-100 animate-pulse" />)}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {filtered.map(p => (
              <PlaybookCard
                key={p.slug}
                playbook={p}
                installing={false}
                installCount={installedCount.get(p.slug) ?? 0}
                onInstall={openInstallModal}
              />
            ))}
          </div>
        )}
      </div>

      {/* Install modal */}
      {pendingSlug && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-5">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Install to project</h2>
              <p className="text-xs text-stone-400 mt-1">
                Choose where to install <span className="font-medium text-stone-600">{FRIENDLY_NAMES[pendingSlug] ?? pendingSlug}</span>.
              </p>
            </div>

            {/* Project picker */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">Project</label>
              {projectsLoading ? (
                <div className="h-9 rounded-lg bg-stone-100 animate-pulse" />
              ) : (
                <select
                  value={selectedProjectId}
                  onChange={e => setSelectedProjectId(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                >
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Environment picker */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">Environment</label>
              {environments.length === 0 ? (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  No environments found. <a href="/settings/environments" className="underline font-medium">Create one first</a>.
                </div>
              ) : (
                <select
                  value={selectedEnvId}
                  onChange={e => setSelectedEnvId(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                >
                  {environments.map(e => (
                    <option key={e.id} value={e.id}>{e.name}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Playbook inputs */}
            {Object.entries(playbookInputs).map(([key, input]) => (
              <div key={key} className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">
                  {input.label ?? key}
                  {input.hint && <span className="ml-1 font-normal text-stone-400">— {input.hint}</span>}
                </label>
                {input.type === "select" && input.options ? (
                  <select
                    value={inputValues[key] ?? String(input.default ?? "")}
                    onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                    className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                  >
                    {input.options.map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={inputValues[key] ?? String(input.default ?? "")}
                    onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                    className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                  />
                )}
              </div>
            ))}

            {/* Repo picker — GitHub webhook playbooks */}
            {GITHUB_WEBHOOK_SLUGS.has(pendingSlug) && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">
                  GitHub repo
                  <span className="ml-1 text-stone-400 font-normal">— webhook registered automatically on install</span>
                </label>
                {reposLoading ? (
                  <div className="h-9 rounded-lg bg-stone-100 animate-pulse" />
                ) : repos.length === 0 ? (
                  <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    No repos found. Connect GitHub in{" "}
                    <a href="/settings/integrations" className="underline font-medium">Settings → Integrations</a>{" "}
                    then re-open this modal.
                  </div>
                ) : (
                  <select
                    value={selectedRepo}
                    onChange={e => setSelectedRepo(e.target.value)}
                    className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                  >
                    {repos.map(r => (
                      <option key={r.full_name} value={r.full_name}>{r.full_name}</option>
                    ))}
                  </select>
                )}
              </div>
            )}

            {/* Manual setup instructions — non-GitHub webhook playbooks */}
            {MANUAL_WEBHOOK_SLUGS.has(pendingSlug) && (
              <div className="bg-stone-50 border border-stone-200 rounded-lg px-3 py-3 flex flex-col gap-1.5">
                <p className="text-xs font-medium text-stone-700">Manual webhook setup required</p>
                <p className="text-xs text-stone-500 leading-relaxed">
                  After installing, copy the webhook URL from the workflow settings and paste it into your{" "}
                  {pendingSlug === "incident_responder" ? "PagerDuty or OpsGenie" : "GitHub Actions"} configuration.
                </p>
              </div>
            )}

            {conflictWarning && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-3 flex gap-2">
                <span className="text-amber-500 text-sm">⚠️</span>
                <p className="text-xs text-amber-700 leading-relaxed">{conflictWarning}</p>
              </div>
            )}

            {webhookError && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-3">
                <p className="text-xs font-semibold text-red-700 mb-1">Webhook registration failed</p>
                <p className="text-xs text-red-600 leading-relaxed">{webhookError}</p>
                <p className="text-xs text-red-500 mt-2">Agent was installed. Add <strong>Administration (read &amp; write)</strong> permission to your GitHub PAT in Settings → Environments, then reinstall.</p>
                <button onClick={() => { closeInstallModal(); router.push(`/workflows/${lastInstalledId ?? ""}`) }}
                  className="mt-2 text-xs underline text-red-700">Open agent anyway →</button>
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={closeInstallModal}
                className="px-4 py-2 text-xs text-stone-500 hover:text-stone-700 rounded-lg hover:bg-stone-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmInstall}
                disabled={installing || projectsLoading || (GITHUB_WEBHOOK_SLUGS.has(pendingSlug ?? "") && !selectedRepo)}
                className="px-4 py-2 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 disabled:opacity-40 transition-colors"
              >
                {installing ? "Installing…" : "Install"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}

function PlaybookCard({ playbook, installing, installCount, onInstall }: {
  playbook: Playbook
  installing: boolean
  installCount: number
  onInstall: (slug: string) => void
}) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5 flex flex-col gap-3 hover:border-stone-300 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <span className="text-2xl leading-none">{playbook.icon}</span>
        <div className="flex flex-wrap gap-1 justify-end">
          {installCount > 0 && (
            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-medium">
              {installCount} installed
            </span>
          )}
          {playbook.tags.map(tag => (
            <span key={tag} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold text-stone-900 mb-1">
          {FRIENDLY_NAMES[playbook.slug] ?? playbook.name}
        </p>
        <p className="text-xs text-stone-500 leading-relaxed">{playbook.description}</p>
      </div>
      <button
        onClick={() => onInstall(playbook.slug)}
        disabled={installing}
        className="mt-auto w-full rounded-lg px-3 py-2 text-xs font-medium bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-40 transition-colors"
      >
        {installing ? "Installing…" : "+ Install"}
      </button>
    </div>
  )
}
