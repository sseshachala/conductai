"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Project   { id: string; name: string }
interface Environment { id: string; name: string }
interface Repo      { full_name: string }
interface PlaybookInput {
  label: string
  default: string
  type: "string" | "select"
  options?: string[]
  hint?: string
}

const MODEL_HINTS: Record<string, string> = {
  "claude-haiku-4-5-20251001": "Fastest & cheapest — great for simple fixes and triage tasks",
  "claude-sonnet-4-6":         "Balanced speed and capability — recommended for most autopilot tasks",
  "claude-opus-4-7":           "Most capable — best for complex multi-file refactors, slower and costlier",
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

const GITHUB_WEBHOOK_SLUGS = new Set([
  "pr_reviewer", "copilot_reviewer", "issue_triage",
  "ci_notify", "release_notes", "security_scanner",
  "autopilot_quick", "autopilot_full", "autopilot_approved",
  "security_patch_updater",
])

const MANUAL_WEBHOOK_SLUGS = new Set(["incident_responder", "dependency_updater"])

const TEMPLATES = [
  { id: "autopilot_quick",    label: "Autopilot Quick",         description: "Issue labeled → implement fix → open PR immediately.", tags: ["GitHub", "Slack"] },
  { id: "autopilot_full",     label: "Autopilot Full",          description: "Issue labeled → implement fix → run tests → open PR.", tags: ["GitHub", "Slack"] },
  { id: "autopilot_approved", label: "Autopilot + Approval",    description: "Fix → tests → human approves in Slack → open PR.", tags: ["GitHub", "Slack"] },
  { id: "pr_reviewer",        label: "PR Reviewer",             description: "PR opened → AI reviews diff → posts comment.", tags: ["GitHub", "Slack"] },
  { id: "issue_triage",       label: "Issue Triage",            description: "New issue → AI classifies and adds labels.", tags: ["GitHub", "Slack"] },
  { id: "release_notes",      label: "Release Notes",           description: "Tag pushed → AI writes CHANGELOG → posts to Slack.", tags: ["GitHub", "Slack"] },
  { id: "ci_notify",          label: "CI Failure Alert",        description: "CI fails → AI diagnoses → posts root cause to Slack.", tags: ["GitHub", "Slack"] },
  { id: "incident_responder", label: "Incident Responder",      description: "Alert fires → AI correlates commits → posts to #incidents.", tags: ["Slack"] },
  { id: "dependency_updater", label: "Dependency Updater",      description: "Weekly cron → bump patch/minor deps → open PR.", tags: ["GitHub", "Slack"] },
  { id: "security_scanner",   label: "Security Scanner",        description: "PR opened → OWASP scan → structured security report.", tags: ["GitHub"] },
  { id: "copilot_reviewer",   label: "Copilot Reviewer",        description: "Copilot/Cursor PR → AI reviews → human approves before merge.", tags: ["GitHub", "Slack"] },
]

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
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
  const router = useRouter()
  const searchParams = useSearchParams()
  const urlProjectId = searchParams.get("project_id") ?? ""

  const [template, setTemplate]           = useState("autopilot_quick")
  const [templateOpen, setTemplateOpen]   = useState(false)
  const templateRef                        = useRef<HTMLDivElement>(null)
  const [agentName, setAgentName]         = useState(FRIENDLY_NAMES["autopilot_quick"])
  const [projects, setProjects]           = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState(urlProjectId)
  const [environments, setEnvironments]   = useState<Environment[]>([])
  const [selectedEnvId, setSelectedEnvId] = useState("")
  const [playbookInputs, setPlaybookInputs] = useState<Record<string, PlaybookInput>>({})
  const [inputValues, setInputValues]     = useState<Record<string, string>>({})
  const [repos, setRepos]                 = useState<Repo[]>([])
  const [selectedRepo, setSelectedRepo]   = useState("")
  const [reposLoading, setReposLoading]   = useState(false)
  const [loading, setLoading]             = useState(false)
  const [bootstrapping, setBootstrapping] = useState(true)
  const [conflictWarning, setConflictWarning] = useState<string | null>(null)
  const [webhookError, setWebhookError]   = useState<string | null>(null)
  const [error, setError]                 = useState<string | null>(null)

  const buildHeaders = useCallback(async (contentType = false): Promise<Record<string, string>> => {
    const h: Record<string, string> = {}
    if (contentType) h["Content-Type"] = "application/json"
    if (getToken) {
      const t = await getToken()
      if (t) h["Authorization"] = `Bearer ${t}`
    }
    const ws = getWorkspaceId()
    if (ws) h["X-Workspace-Id"] = ws
    return h
  }, [getToken])

  // Close template dropdown on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (templateRef.current && !templateRef.current.contains(e.target as Node)) setTemplateOpen(false)
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  // Bootstrap: load projects + environments once
  useEffect(() => {
    async function boot() {
      setBootstrapping(true)
      const headers = await buildHeaders()
      const workspaceId = getWorkspaceId()
      await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${workspaceId}/projects`, { headers }).then(async res => {
          if (res.ok) {
            const data: Project[] = await res.json()
            setProjects(data)
            if (!urlProjectId) setSelectedProjectId(data[0]?.id ?? "")
          }
        }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers }).then(async res => {
          if (res.ok) {
            const data: Environment[] = await res.json()
            setEnvironments(data)
            setSelectedEnvId(data[0]?.id ?? "")
          }
        }),
      ])
      setBootstrapping(false)
    }
    boot()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // When template changes: load playbook inputs + repos if needed
  useEffect(() => {
    async function loadTemplate(slug: string) {
      const headers = await buildHeaders()
      setAgentName(FRIENDLY_NAMES[slug] ?? slug)
      setConflictWarning(null)
      setWebhookError(null)

      const pbPromise = fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks/${slug}`).then(async res => {
        if (res.ok) {
          const data = await res.json()
          const inputs: Record<string, PlaybookInput> = data.inputs ?? {}
          setPlaybookInputs(inputs)
          setInputValues(Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, String(v.default ?? "")])))
        }
      })

      if (GITHUB_WEBHOOK_SLUGS.has(slug)) {
        setReposLoading(true)
        await Promise.all([
          pbPromise,
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/github/repos`, { headers }).then(async res => {
            if (res.ok) {
              const data: Repo[] = await res.json()
              setRepos(data)
              setSelectedRepo(data[0]?.full_name ?? "")
            }
          }).finally(() => setReposLoading(false)),
        ])
      } else {
        setRepos([])
        setSelectedRepo("")
        await pbPromise
      }
    }
    loadTemplate(template)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template])

  // Conflict check when repo or trigger_label changes
  useEffect(() => {
    if (!selectedRepo) { setConflictWarning(null); return }
    const triggerLabel = inputValues["trigger_label"] ?? ""
    buildHeaders().then(async headers => {
      const params = new URLSearchParams({ template, repo: selectedRepo })
      if (triggerLabel) params.set("trigger_label", triggerLabel)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/conflict-check?${params}`, { headers })
      if (res.ok) {
        const data = await res.json()
        setConflictWarning(data.conflicts.length > 0
          ? data.conflict_type === "label"
            ? `An agent is already watching "${triggerLabel}" on ${selectedRepo}. Choose a different trigger label.`
            : `This playbook is already installed on ${selectedRepo}. Installing again runs two independent agents.`
          : null)
      }
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepo, template, inputValues["trigger_label"]])

  async function handleCreate() {
    setLoading(true)
    setError(null)
    setWebhookError(null)
    try {
      const headers = await buildHeaders(true)
      const needsRepo = GITHUB_WEBHOOK_SLUGS.has(template)
      const body: Record<string, unknown> = {
        name: agentName.trim() || (FRIENDLY_NAMES[template] ?? template),
        template,
        inputs: inputValues,
      }
      if (selectedProjectId) body.project_id = selectedProjectId
      if (selectedEnvId)     body.environment_id = selectedEnvId
      if (needsRepo && selectedRepo) body.repo = selectedRepo

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST", headers, body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        if (err.webhook_error) { setWebhookError(err.webhook_error); return }
        setError(err.detail ?? `Error ${res.status}`)
        return
      }
      const wf = await res.json()
      router.push(`/workflows/${wf.id}`)
    } catch {
      setError("Network error — please try again")
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-md px-6 py-10">
        <h1 className="text-base font-semibold text-stone-900 mb-1">New agent</h1>
        <p className="text-xs text-stone-400 mb-8">Choose a playbook and configure it — webhook registered automatically on create.</p>

        <div className="flex flex-col gap-5">

          {/* Template picker — rich dropdown */}
          <div className="flex flex-col gap-1.5" ref={templateRef}>
            <label className="text-xs font-medium text-stone-500">Playbook</label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setTemplateOpen(o => !o)}
                className="w-full flex items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400 hover:border-stone-300 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-medium truncate">{TEMPLATES.find(t => t.id === template)?.label}</span>
                  <span className="text-stone-300">·</span>
                  <span className="text-xs text-stone-400 truncate">{TEMPLATES.find(t => t.id === template)?.description}</span>
                </div>
                <svg className={`w-4 h-4 text-stone-400 shrink-0 ml-2 transition-transform ${templateOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {templateOpen && (
                <div className="absolute z-20 mt-1 w-full rounded-xl border border-stone-200 bg-white shadow-lg overflow-hidden">
                  {TEMPLATES.map(t => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => { setTemplate(t.id); setTemplateOpen(false) }}
                      className={`w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-stone-50 transition-colors border-b border-stone-100 last:border-0 ${template === t.id ? "bg-stone-50" : ""}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium ${template === t.id ? "text-stone-900" : "text-stone-700"}`}>{t.label}</span>
                          <div className="flex gap-1">
                            {t.tags.map(tag => (
                              <span key={tag} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded">{tag}</span>
                            ))}
                          </div>
                        </div>
                        <p className="text-xs text-stone-400 mt-0.5">{t.description}</p>
                      </div>
                      {template === t.id && (
                        <svg className="w-4 h-4 text-stone-900 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {bootstrapping ? (
            <div className="space-y-3">
              {[1,2,3].map(i => <div key={i} className="h-9 rounded-lg bg-stone-100 animate-pulse" />)}
            </div>
          ) : (
            <>
              {/* Agent name */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">Agent name</label>
                <input
                  value={agentName}
                  onChange={e => setAgentName(e.target.value)}
                  placeholder={FRIENDLY_NAMES[template] ?? template}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                />
                <p className="text-[10px] text-stone-400">Give this instance a name — e.g. "Autopilot — conductai prod"</p>
              </div>

              {/* Project */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">Project</label>
                <select
                  value={selectedProjectId}
                  onChange={e => setSelectedProjectId(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                >
                  {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>

              {/* Environment */}
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
                    className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                  >
                    {environments.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </select>
                )}
              </div>

              {/* Dynamic playbook inputs (trigger label, model, clone depth…) */}
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
                        className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                      >
                        {input.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                      {key === "model" && (
                        <p className="text-xs text-stone-400">{MODEL_HINTS[inputValues["model"] ?? String(input.default ?? "")] ?? ""}</p>
                      )}
                    </>
                  ) : (
                    <input
                      type="text"
                      value={inputValues[key] ?? String(input.default ?? "")}
                      onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                      className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                    />
                  )}
                </div>
              ))}

              {/* GitHub repo */}
              {GITHUB_WEBHOOK_SLUGS.has(template) && (
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-stone-500">
                    GitHub repo
                    <span className="ml-1 text-stone-400 font-normal">— webhook registered automatically on create</span>
                  </label>
                  {reposLoading ? (
                    <div className="h-9 rounded-lg bg-stone-100 animate-pulse" />
                  ) : repos.length === 0 ? (
                    <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                      No repos found. Connect GitHub in <a href="/settings/environments" className="underline font-medium">Settings → Environments</a>.
                    </div>
                  ) : (
                    <select
                      value={selectedRepo}
                      onChange={e => setSelectedRepo(e.target.value)}
                      className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                    >
                      {repos.map(r => <option key={r.full_name} value={r.full_name}>{r.full_name}</option>)}
                    </select>
                  )}
                </div>
              )}

              {/* Manual webhook note */}
              {MANUAL_WEBHOOK_SLUGS.has(template) && (
                <div className="bg-stone-50 border border-stone-200 rounded-lg px-3 py-3">
                  <p className="text-xs font-medium text-stone-700 mb-1">Manual webhook setup required</p>
                  <p className="text-xs text-stone-500 leading-relaxed">
                    After creating, copy the webhook URL from agent settings and paste it into your{" "}
                    {template === "incident_responder" ? "PagerDuty or OpsGenie" : "GitHub Actions"} configuration.
                  </p>
                </div>
              )}

              {conflictWarning && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-3 flex gap-2">
                  <span className="text-amber-500">⚠</span>
                  <p className="text-xs text-amber-700 leading-relaxed">{conflictWarning}</p>
                </div>
              )}

              {webhookError && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-3">
                  <p className="text-xs font-semibold text-red-700 mb-1">Webhook not registered</p>
                  <p className="text-xs text-red-600 leading-relaxed">{webhookError}</p>
                  <p className="text-xs text-stone-400 mt-2">The agent was installed — the webhook can be added once the token is updated.</p>
                </div>
              )}

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  <p className="text-xs text-red-600">{error}</p>
                </div>
              )}

              <button
                onClick={handleCreate}
                disabled={loading || (GITHUB_WEBHOOK_SLUGS.has(template) && !selectedRepo)}
                className="w-full rounded-xl bg-stone-900 px-4 py-3 text-sm font-medium text-white hover:bg-stone-700 transition-colors disabled:opacity-40"
              >
                {loading ? "Creating…" : "Create agent"}
              </button>
            </>
          )}
        </div>
      </div>
    </AppShell>
  )
}
