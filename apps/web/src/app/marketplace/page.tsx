"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureLoopIcon } from "@/app/secure/_components"

interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  category: string
  featured: boolean
  trigger?: string
  block_count?: number
  install_count?: number
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

// Display labels for category chips — maps internal category to design label
const CATEGORY_LABELS: Record<string, string> = {
  "Issue to PR": "Issue → PR",
  "Issue Triage": "Triage",
  "Release Management": "Release",
  "Incidents & Ops": "Incidents",
  "Platform & Infra": "Infra",
}

const CAT_BLOCK: Record<string, string> = {
  "Issue to PR":       "brain",
  "Issue → PR":        "brain",
  "Code Review":       "tool",
  "Issue Triage":      "trigger",
  "Triage":            "trigger",
  "CI/CD":             "logic",
  "Release Management":"output",
  "Release":           "output",
  "Incidents & Ops":   "approval",
  "Incidents":         "approval",
  "Security":          "guard",
  "Docs":              "memory",
  "Platform & Infra":  "mcp",
  "Infra":             "mcp",
  "Testing":           "cleanup",
}

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
  const [search, setSearch] = useState("")
  const [installing, setInstalling] = useState(false)
  const [installedCount, setInstalledCount] = useState<Map<string, number>>(new Map())
  const [scores, setScores] = useState<Map<string, PlaybookScore>>(new Map())
  const [secureInstalling, setSecureInstalling] = useState(false)
  const [secureInstalled, setSecureInstalled] = useState(false)
  const [secureDismissed, setSecureDismissed] = useState(false)

  // Check if Security Loop is already installed
  useEffect(() => {
    const wsId = getWorkspaceId()
    if (!wsId) return
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/secure/installed?workspace_id=${wsId}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.installed) setSecureInstalled(true) })
      .catch(() => {})
  }, [])

  async function installSecureModule() {
    const wsId = getWorkspaceId()
    if (!wsId || secureInstalling) return
    setSecureInstalling(true)
    try {
      const token = getToken ? await getToken() : null
      const h: Record<string, string> = { "Content-Type": "application/json" }
      if (token) h["Authorization"] = `Bearer ${token}`
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/secure/install?workspace_id=${wsId}`, {
        method: "POST", headers: h,
      })
      if (res.ok) {
        setSecureInstalled(true)
        window.dispatchEvent(new CustomEvent("secure-install-changed", { detail: { installed: true } }))
        setTimeout(() => setSecureDismissed(true), 1500)
      }
    } catch {}
    finally { setSecureInstalling(false) }
  }

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

  // Search filter
  const searchActive = search.trim().length > 0
  const searchFiltered = searchActive
    ? playbooks.filter(p =>
        (FRIENDLY_NAMES[p.slug] ?? p.name).toLowerCase().includes(search.toLowerCase()) ||
        p.description.toLowerCase().includes(search.toLowerCase())
      )
    : playbooks

  // Category filter (applied after search)
  const filtered = activeCategory === "All"
    ? searchFiltered
    : searchFiltered.filter(p => p.category === activeCategory)

  // Featured playbooks (shown only when no category filter and no search)
  const featuredPlaybooks = playbooks.filter(p => p.featured)
  const showFeatured = activeCategory === "All" && !searchActive && featuredPlaybooks.length > 0

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Page header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", marginBottom: 5 }}>
            Marketplace
          </h1>
          <p style={{ fontSize: 13.5, color: "var(--text-3)", lineHeight: 1.5 }}>
            22 ready-made agent templates. Install in one click, connect credentials, and run.
          </p>
        </div>

        {/* Search + submit row */}
        <div style={{ display: "flex", gap: 10, marginBottom: 22, alignItems: "center" }}>
          <div style={{ position: "relative", maxWidth: 420, flex: "0 0 420px" }}>
            <svg
              width={16} height={16}
              viewBox="0 0 16 16"
              fill="none"
              style={{ position: "absolute", left: 12, top: 11, color: "var(--text-muted)", pointerEvents: "none" }}
            >
              <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <input
              type="text"
              placeholder="Search agent templates…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{
                width: "100%",
                height: 38,
                padding: "0 12px 0 36px",
                borderRadius: 9,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text)",
                fontSize: 13.5,
                outline: "none",
              }}
            />
          </div>
          <Link
            href="/playbooks/submit"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              height: 38,
              padding: "0 14px",
              fontSize: 13,
              fontWeight: 600,
              color: "var(--text-2)",
              border: "1px solid var(--border)",
              borderRadius: 9,
              background: "transparent",
              textDecoration: "none",
              transition: "background .12s, color .12s",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text)" }}
            onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-2)" }}
          >
            <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
            Submit agent template
          </Link>
        </div>

        {loading ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 14 }}>
            {[1,2,3,4,5,6].map(i => (
              <div key={i} style={{ height: 190, borderRadius: 12, background: "var(--surface-3)", animation: "pulse 2s cubic-bezier(0.4,0,0.6,1) infinite" }} />
            ))}
          </div>
        ) : (
          <>
            {/* Security Loop module install card */}
            {(activeCategory === "All" || activeCategory === "Security") && !searchActive && !secureDismissed && (
              <div style={{ marginBottom: 28 }}>
                <div className="eyebrow" style={{ marginBottom: 11 }}>Modules</div>
                <div style={{
                  background: "linear-gradient(135deg, #fef2f2 0%, #fff7ed 100%)",
                  border: "1px solid #fecaca",
                  borderRadius: 14,
                  padding: "20px 24px",
                  display: "flex",
                  alignItems: "center",
                  gap: 20,
                }}>
                  <span style={{ width: 44, height: 44, borderRadius: 12, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                    <SecureLoopIcon size={22} />
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 15, color: "#991b1b", marginBottom: 3 }}>Security Loop — for Claude Code</div>
                    <div style={{ fontSize: 13, color: "#b91c1c", lineHeight: 1.5 }}>
                      Passive security classifier on every Claude Code tool call. Findings surface in your team's Secure feed automatically — secrets, injections, path traversal, crypto issues. Zero developer action.
                    </div>
                    <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                      {["passive", "claude-code", "security", "bughunter"].map(tag => (
                        <span key={tag} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 20, background: "rgba(220,38,38,.12)", color: "#dc2626", fontWeight: 500 }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  {secureInstalled ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                      <Link href="/secure" style={{ textDecoration: "none" }}>
                        <button className="btn btn-ghost btn-sm">Open Secure →</button>
                      </Link>
                      <button
                        onClick={() => setSecureDismissed(true)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "#b91c1c", fontSize: 16, lineHeight: 1, padding: "0 4px", opacity: 0.6 }}
                        title="Dismiss"
                      >×</button>
                    </div>
                  ) : (
                    <button
                      className="btn btn-primary btn-sm"
                      style={{ flexShrink: 0 }}
                      disabled={secureInstalling}
                      onClick={installSecureModule}
                    >
                      {secureInstalling ? "Installing…" : "Install"}
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Featured section */}
            {showFeatured && (
              <div style={{ marginBottom: 30 }}>
                <div className="eyebrow" style={{ marginBottom: 11 }}>Featured · Issue → PR</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
                  {featuredPlaybooks.map(p => (
                    <PlaybookCard
                      key={p.slug}
                      playbook={p}
                      installing={installing}
                      installCount={installedCount.get(p.slug) ?? 0}
                      isInstalled={(installedCount.get(p.slug) ?? 0) > 0}
                      grade={scores.get(p.slug)?.grade}
                      onInstall={openInstallModal}
                      onViewYaml={openYamlModal}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Category chips */}
            <div style={{ display: "flex", gap: 7, marginBottom: 18, flexWrap: "wrap" }}>
              {availableCategories.map(cat => {
                const isActive = activeCategory === cat
                return (
                  <button
                    key={cat}
                    onClick={() => setActiveCategory(cat)}
                    style={{
                      height: 30,
                      padding: "0 13px",
                      borderRadius: 20,
                      border: `1px solid ${isActive ? "var(--accent-ring)" : "var(--border)"}`,
                      background: isActive ? "var(--accent-weak)" : "var(--surface)",
                      color: isActive ? "var(--accent-text)" : "var(--text-2)",
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all .12s",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {CATEGORY_LABELS[cat] ?? cat}
                  </button>
                )
              })}
            </div>

            {/* Playbooks grid */}
            {filtered.length === 0 ? (
              <div style={{ padding: "48px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 13.5 }}>
                No agent templates match your search.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 14 }}>
                {filtered.map(p => (
                  <PlaybookCard
                    key={p.slug}
                    playbook={p}
                    installing={installing}
                    installCount={installedCount.get(p.slug) ?? 0}
                    isInstalled={(installedCount.get(p.slug) ?? 0) > 0}
                    grade={scores.get(p.slug)?.grade}
                    onInstall={openInstallModal}
                    onViewYaml={openYamlModal}
                  />
                ))}
              </div>
            )}
          </>
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

function PlaybookCard({
  playbook,
  installing,
  installCount,
  isInstalled,
  grade,
  onInstall,
  onViewYaml,
}: {
  playbook: Playbook
  installing: boolean
  installCount: number
  isInstalled: boolean
  grade?: string
  onInstall: (slug: string) => void
  onViewYaml: (slug: string) => void
}) {
  const blockType = CAT_BLOCK[playbook.category] ?? "brain"
  const displayName = FRIENDLY_NAMES[playbook.slug] ?? playbook.name
  const catLabel = CATEGORY_LABELS[playbook.category] ?? playbook.category
  const blockCount = playbook.block_count ?? playbook.tags?.length ?? 0
  const installCountDisplay = playbook.install_count ?? installCount

  return (
    <div
      className="card"
      style={{
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        transition: "border-color .14s, box-shadow .14s",
        position: "relative",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-md)"
        ;(e.currentTarget as HTMLDivElement).style.borderColor = "var(--border-2)"
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = ""
        ;(e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)"
      }}
    >
      {/* Grade badge — top right */}
      {grade && (
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded font-semibold tabular-nums ${GRADE_STYLES[grade] ?? "bg-stone-100 text-stone-500"}`}
          title={`Quality grade: ${grade}`}
          style={{ position: "absolute", top: 14, right: 14 }}
        >
          {grade}
        </span>
      )}

      {/* Category chip + popular badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 10 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            height: 21,
            padding: "0 9px",
            borderRadius: 20,
            fontSize: 9.5,
            fontWeight: 700,
            letterSpacing: ".05em",
            textTransform: "uppercase",
            background: `var(--blk-${blockType}-bg)`,
            color: `var(--blk-${blockType}-tx)`,
            border: `1px solid var(--blk-${blockType}-bd)`,
          }}
        >
          {catLabel}
        </span>
        {playbook.featured && (
          <span style={{ fontSize: 9.5, fontWeight: 800, color: "var(--accent-text)", letterSpacing: ".05em" }}>
            ★ POPULAR
          </span>
        )}
      </div>

      {/* Name */}
      <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 5, letterSpacing: "-.01em", color: "var(--text)", paddingRight: grade ? 32 : 0 }}>
        {displayName}
      </div>

      {/* Description */}
      <p style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.45, margin: "0 0 14px", flex: 1 }}>
        {playbook.description}
      </p>

      {/* Meta row: trigger · blocks · installs */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 11.5, color: "var(--text-muted)", marginBottom: 13 }}>
        {playbook.trigger && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0, overflow: "hidden" }}>
            <svg width={13} height={13} viewBox="0 0 13 13" fill="none" style={{ flexShrink: 0 }}>
              <path d="M7 1L3 7.5h4L5.5 12 10 5.5H6.5L7 1z" fill="currentColor" />
            </svg>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "ui-monospace, monospace", fontSize: 11 }}>
              {playbook.trigger}
            </span>
          </span>
        )}
        {blockCount > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
            <svg width={13} height={13} viewBox="0 0 13 13" fill="none">
              <rect x="1" y="1" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
              <rect x="7.5" y="1" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
              <rect x="1" y="7.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
              <rect x="7.5" y="7.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
            </svg>
            {blockCount} blocks
          </span>
        )}
        {installCountDisplay > 0 && (
          <span style={{ marginLeft: "auto", whiteSpace: "nowrap", flexShrink: 0 }}>
            {installCountDisplay} installs
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => onInstall(playbook.slug)}
          disabled={installing}
          style={{
            flex: 1,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 5,
            height: 32,
            borderRadius: 7,
            fontSize: 12,
            fontWeight: 600,
            cursor: installing ? "not-allowed" : "pointer",
            opacity: installing ? 0.5 : 1,
            transition: "all .12s",
            border: isInstalled ? "1px solid var(--ok-bd)" : "1px solid var(--accent)",
            background: isInstalled ? "transparent" : "var(--accent)",
            color: isInstalled ? "var(--ok)" : "#fff",
          }}
        >
          {isInstalled ? (
            <>
              <svg width={13} height={13} viewBox="0 0 13 13" fill="none">
                <path d="M2.5 6.5l3 3 5-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Installed — open
            </>
          ) : (
            "Install"
          )}
        </button>
        <button
          onClick={() => onViewYaml(playbook.slug)}
          title="Preview YAML"
          style={{
            width: 32,
            height: 32,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 7,
            border: "1px solid var(--border)",
            background: "transparent",
            color: "var(--text-2)",
            cursor: "pointer",
            flexShrink: 0,
            transition: "all .12s",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text)" }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)" }}
        >
          <svg width={15} height={15} viewBox="0 0 15 15" fill="none">
            <path d="M3 4.5h9M3 7.5h6M3 10.5h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            <path d="M11.5 10l1.5 1.5-1.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}
