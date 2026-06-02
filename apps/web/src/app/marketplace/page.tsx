"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  category: string
  featured: boolean
}

interface PlaybookScore {
  slug: string
  structural_score: number
  quality_score: number
  grade: string
  status: string
  eval_run_at: string | null
}

const GRADE_STYLES: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-700",
  B: "bg-blue-100  text-blue-700",
  C: "bg-amber-100  text-amber-700",
  D: "bg-orange-100 text-orange-700",
  F: "bg-red-100    text-red-700",
}

interface Project {
  id: string
  name: string
}

interface Environment {
  id: string
  name: string
}

const MODEL_HINTS: Record<string, string> = {
  "claude-haiku-4-5-20251001": "Fastest & cheapest — great for simple fixes and triage tasks",
  "claude-sonnet-4-6": "Balanced speed and capability — recommended for most autopilot tasks",
  "claude-opus-4-7": "Most capable — best for complex multi-file refactors, slower and costlier",
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

// Playbooks that show the GitHub repo selector on install (webhook registered automatically).
const GITHUB_WEBHOOK_SLUGS = new Set([
  "pr_reviewer", "copilot_reviewer", "issue_triage",
  "ci_notify", "release_notes", "security_scanner",
  "autopilot_quick", "autopilot_full", "autopilot_approved",
  "security_patch_updater", "dependency_updater", "incident_responder",
  "flaky_test_detective", "release_readiness", "docs_drift_detector",
  "terraform_reviewer", "factory",
])

// Playbooks that need manual webhook setup (show instructions instead).
const MANUAL_WEBHOOK_SLUGS = new Set(["postmortem_drafter"])

const CATEGORY_ORDER = [
  "All",
  "Issue to PR",
  "Code Review",
  "Issue Triage",
  "CI/CD",
  "Release Management",
  "Incidents & Ops",
  "Security",
  "Docs",
  "Platform & Infra",
]

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

const FRIENDLY_NAMES: Record<string, string> = {
  autopilot_quick:      "Autopilot Quick",
  autopilot_full:       "Autopilot Full",
  autopilot_approved:   "Autopilot + Approval",
  pr_reviewer:          "PR Reviewer",
  issue_triage:         "Issue Triage",
  release_notes:        "Release Notes",
  ci_notify:            "CI Failure Alert",
  incident_responder:   "Incident Responder",
  dependency_updater:   "Dependency Updater",
  copilot_reviewer:     "Copilot / AI PR Reviewer",
  security_scanner:     "Security Scanner",
  flaky_test_detective: "Flaky Test Detective",
  release_readiness:    "Release Readiness Reviewer",
  postmortem_drafter:   "Postmortem Drafter",
  docs_drift_detector:  "Docs Drift Detector",
  terraform_reviewer:   "Terraform Plan Reviewer",
  factory:              "Software Factory",
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
  const [activeCategory, setActiveCategory] = useState("All")
  const [installing, setInstalling] = useState(false)
  const [installedCount, setInstalledCount] = useState<Map<string, number>>(new Map())
  const [scores, setScores] = useState<Map<string, PlaybookScore>>(new Map())

  // YAML preview modal
  const [yamlSlug, setYamlSlug] = useState<string | null>(null)
  const [yamlCache, setYamlCache] = useState<Map<string, string>>(new Map())
  const [yamlLoading, setYamlLoading] = useState(false)

  async function openYamlModal(slug: string) {
    setYamlSlug(slug)
    if (yamlCache.has(slug)) return
    setYamlLoading(true)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks/${slug}`)
      if (res.ok) {
        const data = await res.json()
        if (data.yaml_source) {
          setYamlCache(prev => new Map(prev).set(slug, data.yaml_source))
        }
      }
    } finally {
      setYamlLoading(false)
    }
  }

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
  const [agentName, setAgentName] = useState<string>("")

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

      let loadedPlaybooks: Playbook[] = []
      if (pbRes.ok) {
        loadedPlaybooks = await pbRes.json()
        setPlaybooks(loadedPlaybooks)
      }

      if (wfRes.ok) {
        const workflows: { id: string; name: string; playbook_slug?: string }[] = await wfRes.json()
        const counts = new Map<string, number>()
        for (const wf of workflows) {
          if (wf.playbook_slug) {
            counts.set(wf.playbook_slug, (counts.get(wf.playbook_slug) ?? 0) + 1)
          }
        }
        setInstalledCount(counts)
      }

      // Fetch quality scores — graceful if endpoint not yet available
      if (loadedPlaybooks.length > 0) {
        const scoreResults = await Promise.allSettled(
          loadedPlaybooks.map(p =>
            fetch(`${process.env.NEXT_PUBLIC_API_URL}/playbooks/${p.slug}/score`)
              .then(r => (r.ok ? r.json() as Promise<PlaybookScore> : null))
              .catch(() => null)
          )
        )
        const scoreMap = new Map<string, PlaybookScore>()
        scoreResults.forEach((result, idx) => {
          if (result.status === "fulfilled" && result.value) {
            scoreMap.set(loadedPlaybooks[idx].slug, result.value)
          }
        })
        setScores(scoreMap)
      }

      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openInstallModal(slug: string) {
    setPendingSlug(slug)
    setAgentName(FRIENDLY_NAMES[slug] ?? slug)
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
  }

  useEffect(() => {
    if (!pendingSlug || !selectedRepo) { return }
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
        name: agentName.trim() || (FRIENDLY_NAMES[pendingSlug] ?? pendingSlug),
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

  // Build category list from loaded playbooks, maintaining defined order
  const availableCategories = ["All", ...CATEGORY_ORDER.filter(c =>
    c !== "All" && playbooks.some(p => p.category === c)
  )]

  const filtered = activeCategory === "All"
    ? playbooks
    : playbooks.filter(p => p.category === activeCategory)

  // Group filtered playbooks by category for "All" view
  const grouped: Record<string, Playbook[]> = {}
  if (activeCategory === "All") {
    for (const cat of CATEGORY_ORDER.filter(c => c !== "All")) {
      const items = playbooks.filter(p => p.category === cat)
      if (items.length > 0) grouped[cat] = items
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Header */}
        <div className="mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Playbooks</h1>
            <p className="text-xs text-stone-400 mt-0.5">YAML-based agent recipes — install one into a project, configure it, and run it.</p>
          </div>
          <Link
            href="/playbooks/submit"
            className="text-sm text-indigo-600 border border-indigo-200 rounded-lg px-4 py-2 hover:bg-indigo-50 transition-colors whitespace-nowrap"
          >
            + Submit a playbook
          </Link>
        </div>

        {/* Category tabs */}
        <div className="flex flex-wrap gap-1.5 mb-8 border-b border-stone-100 pb-4">
          {availableCategories.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeCategory === cat
                  ? "bg-stone-900 text-white"
                  : "bg-stone-100 text-stone-500 hover:bg-stone-200"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="grid grid-cols-3 gap-4">
            {[1,2,3,4,5,6,7,8,9].map(i => <div key={i} className="h-48 rounded-xl bg-stone-100 animate-pulse" />)}
          </div>
        ) : activeCategory === "All" ? (
          // Grouped by category
          <div className="flex flex-col gap-10">
            {Object.entries(grouped).map(([cat, items]) => (
              <div key={cat}>
                <div className="flex items-center gap-3 mb-4">
                  <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">{cat}</h2>
                  <div className="flex-1 h-px bg-stone-100" />
                  <span className="text-[10px] text-stone-300">{items.length}</span>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  {items.map(p => (
                    <PlaybookCard
                      key={p.slug}
                      playbook={p}
                      installing={false}
                      installCount={installedCount.get(p.slug) ?? 0}
                      grade={scores.get(p.slug)?.grade}
                      onInstall={openInstallModal}
                      onViewYaml={openYamlModal}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          // Single category flat grid
          <div className="grid grid-cols-3 gap-4">
            {filtered.map(p => (
              <PlaybookCard
                key={p.slug}
                playbook={p}
                installing={false}
                installCount={installedCount.get(p.slug) ?? 0}
                grade={scores.get(p.slug)?.grade}
                onInstall={openInstallModal}
                onViewYaml={openYamlModal}
              />
            ))}
          </div>
        )}
      </div>

      {/* YAML preview modal */}
      {yamlSlug && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setYamlSlug(null)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 flex flex-col max-h-[80vh]" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
              <div>
                <p className="text-sm font-semibold text-stone-900">{FRIENDLY_NAMES[yamlSlug] ?? yamlSlug}</p>
                <p className="text-[10px] text-stone-400 font-mono mt-0.5">{yamlSlug}.yaml</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => openInstallModal(yamlSlug)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 transition-colors"
                >
                  + Install
                </button>
                <button onClick={() => setYamlSlug(null)} className="text-stone-400 hover:text-stone-600 text-lg leading-none px-1">×</button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1 p-5">
              {yamlLoading ? (
                <div className="h-48 rounded-lg bg-stone-100 animate-pulse" />
              ) : (
                <pre className="text-[11px] font-mono text-stone-700 leading-relaxed whitespace-pre-wrap break-words">
                  {yamlCache.get(yamlSlug) ?? "YAML not available."}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Install modal */}
      {pendingSlug && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-5 max-h-[90vh] overflow-y-auto">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Install to project</h2>
              <p className="text-xs text-stone-400 mt-1">
                Choose where to install <span className="font-medium text-stone-600">{FRIENDLY_NAMES[pendingSlug] ?? pendingSlug}</span>.
              </p>
            </div>

            {/* Agent name */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">Agent name</label>
              <input
                type="text"
                value={agentName}
                onChange={e => setAgentName(e.target.value)}
                placeholder={FRIENDLY_NAMES[pendingSlug ?? ""] ?? pendingSlug ?? ""}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
              />
              <p className="text-[10px] text-stone-400">Give this instance a name — e.g. "Autopilot — conductai prod"</p>
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
                  <>
                    <select
                      value={inputValues[key] ?? String(input.default ?? "")}
                      onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                      className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                    >
                      {input.options.map(opt => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                    {key === "model" && (
                      <p className="text-xs text-stone-400">
                        {MODEL_HINTS[inputValues["model"] ?? String(input.default ?? "")] ?? ""}
                      </p>
                    )}
                  </>
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

            {/* Manual setup instructions — inbound webhook playbooks */}
            {MANUAL_WEBHOOK_SLUGS.has(pendingSlug) && (
              <div className="bg-stone-50 border border-stone-200 rounded-lg px-3 py-3 flex flex-col gap-1.5">
                <p className="text-xs font-medium text-stone-700">Manual webhook setup required</p>
                <p className="text-xs text-stone-500 leading-relaxed">
                  After installing, copy the webhook URL from the workflow settings and paste it into your{" "}
                  PagerDuty, OpsGenie, or incident management tool.
                </p>
              </div>
            )}



            {webhookError && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-3">
                <p className="text-xs font-semibold text-red-700 mb-1">Webhook not registered</p>
                <p className="text-xs text-red-600 leading-relaxed">{webhookError}</p>
                <p className="text-xs text-stone-400 mt-2">The agent was installed — the webhook can be added once the token is updated.</p>
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
                disabled={installing || projectsLoading || environments.length === 0 || (GITHUB_WEBHOOK_SLUGS.has(pendingSlug ?? "") && !selectedRepo)}
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

function PlaybookCard({ playbook, installing, installCount, grade, onInstall, onViewYaml }: {
  playbook: Playbook
  installing: boolean
  installCount: number
  grade?: string
  onInstall: (slug: string) => void
  onViewYaml: (slug: string) => void
}) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5 flex flex-col gap-3 hover:border-stone-300 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <span className="text-2xl leading-none">{playbook.icon}</span>
        <div className="flex items-center gap-1.5">
          {grade && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-semibold tabular-nums ${GRADE_STYLES[grade] ?? "bg-stone-100 text-stone-500"}`}
              title={`Quality grade: ${grade}`}
            >
              {grade}
            </span>
          )}
          {installCount > 0 && (
            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-medium">
              {installCount} installed
            </span>
          )}
          <Link
            href={`/playbooks/${playbook.slug}`}
            className="text-[10px] bg-stone-100 text-stone-500 hover:bg-stone-200 px-1.5 py-0.5 rounded font-medium transition-colors"
            title="Public shareable page"
          >
            ↗ Share
          </Link>
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold text-stone-900 mb-1">
          {FRIENDLY_NAMES[playbook.slug] ?? playbook.name}
        </p>
        <p className="text-xs text-stone-500 leading-relaxed">{playbook.description}</p>
      </div>
      <div className="mt-auto flex gap-2">
        <button
          onClick={() => onViewYaml(playbook.slug)}
          className="flex-1 rounded-lg px-3 py-2 text-xs font-medium border border-stone-200 text-stone-600 hover:bg-stone-50 transition-colors"
        >
          View YAML
        </button>
        <button
          onClick={() => onInstall(playbook.slug)}
          disabled={installing}
          className="flex-1 rounded-lg px-3 py-2 text-xs font-medium bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-40 transition-colors"
        >
          {installing ? "Installing…" : "+ Install"}
        </button>
      </div>
    </div>
  )
}
