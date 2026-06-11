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
  const [webhookError, setWebhookError]   = useState<string | null>(null)
  const [error, setError]                 = useState<string | null>(null)

  // NL-to-DAG mode
  const [mode, setMode]                   = useState<"playbook" | "describe">("playbook")
  const [nlPrompt, setNlPrompt]           = useState("")
  const [generating, setGenerating]       = useState(false)
  const [generatedCreds, setGeneratedCreds] = useState<string[]>([])

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


  async function handleGenerate() {
    if (!nlPrompt.trim()) return
    setGenerating(true)
    setError(null)
    try {
      const headers = await buildHeaders(true)
      const genRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/generate`, {
        method: "POST", headers,
        body: JSON.stringify({ prompt: nlPrompt.trim(), environment_id: selectedEnvId || null }),
      })
      if (!genRes.ok) {
        const err = await genRes.json().catch(() => ({}))
        setError(err.detail ?? `Generation failed (${genRes.status})`)
        return
      }
      const { name, graph, required_credentials } = await genRes.json()
      setGeneratedCreds(required_credentials ?? [])

      // Create the workflow with the generated graph
      const createRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST", headers,
        body: JSON.stringify({
          name: agentName.trim() || name,
          graph,
          ...(selectedProjectId && { project_id: selectedProjectId }),
          ...(selectedEnvId     && { environment_id: selectedEnvId }),
        }),
      })
      if (!createRes.ok) {
        const err = await createRes.json().catch(() => ({}))
        setError(err.detail ?? `Create failed (${createRes.status})`)
        return
      }
      const wf = await createRes.json()
      router.push(`/workflows/${wf.id}`)
    } catch {
      setError("Network error — please try again")
    } finally {
      setGenerating(false)
    }
  }

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

  const ni: React.CSSProperties = { width: "100%", height: 38, padding: "0 12px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 13.5, outline: "none" }

  const tpl = TEMPLATES.find(t => t.id === template)

  return (
    <AppShell>
      <div style={{ maxWidth: 560, margin: "0 auto", padding: "30px 34px 80px" }}>

        {/* back link */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18, fontSize: 13, color: "var(--text-3)", cursor: "pointer" }}
          onClick={() => router.push("/workflows")}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: "rotate(180deg)" }}>
            <path d="M9 18l6-6-6-6" />
          </svg>
          Agents
        </div>

        <h1 className="page-title" style={{ fontSize: 22 }}>New agent</h1>
        <p className="page-sub" style={{ marginBottom: 22 }}>Choose a playbook and configure it — the webhook is registered automatically on create.</p>

        {/* mode toggle */}
        <div style={{ display: "flex", background: "var(--surface-3)", borderRadius: 10, padding: 3, marginBottom: 24, width: "fit-content" }}>
          {([["playbook", "Start from playbook"]] as const).map(([v, l]) => (
            <button key={v} onClick={() => setMode(v)} style={{ border: "none", background: mode === v ? "var(--surface)" : "transparent", color: mode === v ? "var(--text)" : "var(--text-3)", fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 8, cursor: "pointer", boxShadow: mode === v ? "var(--shadow-sm)" : "none", display: "flex", alignItems: "center", gap: 7 }}>
              {l}
            </button>
          ))}
        </div>

        {mode === "playbook" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

            {/* Playbook picker */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Playbook</label>
              <div style={{ position: "relative" }} ref={templateRef}>
                <button type="button" onClick={() => setTemplateOpen(o => !o)}
                  style={{ ...ni, display: "flex", alignItems: "center", gap: 8, textAlign: "left", cursor: "pointer" }}>
                  <span style={{ fontWeight: 600 }}>{tpl?.label}</span>
                  <span style={{ color: "var(--text-muted)" }}>·</span>
                  <span style={{ fontSize: 12.5, color: "var(--text-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{tpl?.description}</span>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    style={{ color: "var(--text-muted)", flexShrink: 0, transform: templateOpen ? "rotate(180deg)" : "none", transition: "transform .15s" }}>
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </button>
                {templateOpen && (
                  <div style={{ position: "absolute", zIndex: 20, top: "calc(100% + 5px)", left: 0, right: 0, maxHeight: 340, overflowY: "auto", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 13, boxShadow: "var(--shadow-lg)" }}>
                    {TEMPLATES.map(t => (
                      <button key={t.id} type="button" onClick={() => { setTemplate(t.id); setTemplateOpen(false) }}
                        style={{ width: "100%", textAlign: "left", padding: "11px 14px", display: "flex", alignItems: "flex-start", gap: 10, border: "none", borderBottom: "1px solid var(--border)", background: t.id === template ? "var(--surface-2)" : "transparent", cursor: "pointer" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                            <span style={{ fontSize: 13.5, fontWeight: 600 }}>{t.label}</span>
                            <div style={{ display: "flex", gap: 4 }}>
                              {t.tags.map(tag => (
                                <span key={tag} style={{ fontSize: 9.5, fontWeight: 600, background: "var(--surface-3)", color: "var(--text-3)", borderRadius: 4, padding: "1px 5px" }}>{tag}</span>
                              ))}
                            </div>
                          </div>
                          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>{t.description}</div>
                        </div>
                        {t.id === template && (
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                            style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }}>
                            <path d="M20 6L9 17l-5-5" />
                          </svg>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {bootstrapping ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[1, 2, 3].map(i => <div key={i} style={{ height: 38, borderRadius: 9, background: "var(--surface-3)" }} />)}
              </div>
            ) : (
              <>
                {/* Agent name */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>
                    Agent name <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>— e.g. &ldquo;Autopilot — conductai prod&rdquo;</span>
                  </label>
                  <input value={agentName} onChange={e => setAgentName(e.target.value)}
                    placeholder={FRIENDLY_NAMES[template] ?? template} style={ni} />
                </div>

                {/* Project + Environment — 2-col */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Project</label>
                    <select value={selectedProjectId} onChange={e => setSelectedProjectId(e.target.value)} style={ni}>
                      {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Environment</label>
                    {environments.length === 0 ? (
                      <div style={{ fontSize: 12, color: "var(--warn)", background: "var(--warn-bg)", border: "1px solid var(--warn-bd)", borderRadius: 9, padding: "8px 12px" }}>
                        No environments. <a href="/settings" style={{ textDecoration: "underline", fontWeight: 600 }}>Create one first</a>.
                      </div>
                    ) : (
                      <select value={selectedEnvId} onChange={e => setSelectedEnvId(e.target.value)} style={ni}>
                        {environments.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                      </select>
                    )}
                  </div>
                </div>

                {/* Dynamic playbook inputs */}
                {Object.entries(playbookInputs).map(([key, input]) => (
                  <div key={key} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>
                      {input.label ?? key}
                      {input.hint && <span style={{ fontWeight: 400, color: "var(--text-muted)" }}> — {input.hint}</span>}
                    </label>
                    {input.type === "select" && input.options ? (
                      <>
                        <select value={inputValues[key] ?? String(input.default ?? "")}
                          onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))} style={ni}>
                          {input.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                        {key === "model" && (
                          <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: "2px 0 0", lineHeight: 1.45 }}>
                            {MODEL_HINTS[inputValues["model"] ?? String(input.default ?? "")] ?? ""}
                          </p>
                        )}
                      </>
                    ) : (
                      <input type="text" value={inputValues[key] ?? String(input.default ?? "")}
                        onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                        className={key === "trigger_label" || key === "label" ? "mono" : ""}
                        style={{ ...ni, ...(key === "trigger_label" || key === "label" ? { fontSize: 13 } : {}) }} />
                    )}
                  </div>
                ))}

                {/* GitHub repo */}
                {GITHUB_WEBHOOK_SLUGS.has(template) && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>
                      GitHub repo <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>— webhook registered automatically on create</span>
                    </label>
                    {reposLoading ? (
                      <div style={{ height: 38, borderRadius: 9, background: "var(--surface-3)" }} />
                    ) : repos.length === 0 ? (
                      <div style={{ fontSize: 12, color: "var(--warn)", background: "var(--warn-bg)", border: "1px solid var(--warn-bd)", borderRadius: 9, padding: "8px 12px" }}>
                        No repos found. Connect GitHub in <a href="/settings" style={{ textDecoration: "underline", fontWeight: 600 }}>Settings → Environments</a>.
                      </div>
                    ) : (
                      <select value={selectedRepo} onChange={e => setSelectedRepo(e.target.value)} style={ni}>
                        {repos.map(r => <option key={r.full_name} value={r.full_name}>{r.full_name}</option>)}
                      </select>
                    )}
                  </div>
                )}

                {/* Manual webhook note */}
                {MANUAL_WEBHOOK_SLUGS.has(template) && (
                  <div className="card" style={{ padding: "13px 15px", background: "var(--surface-2)" }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 3 }}>Manual webhook setup required</div>
                    <div style={{ fontSize: 12, color: "var(--text-3)", lineHeight: 1.5 }}>
                      After creating, copy the webhook URL from agent settings and paste it into your{" "}
                      {template === "incident_responder" ? "PagerDuty or OpsGenie" : "GitHub Actions"} configuration.
                    </div>
                  </div>
                )}

                {webhookError && (
                  <div className="card" style={{ padding: "13px 15px", borderColor: "var(--err-bd)", background: "var(--err-bg)" }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--err)", marginBottom: 3 }}>Webhook not registered</div>
                    <div style={{ fontSize: 12, color: "var(--err)", lineHeight: 1.5 }}>{webhookError}</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 6 }}>The agent was created — add the webhook once the token is updated.</div>
                  </div>
                )}

                {error && (
                  <div style={{ fontSize: 12.5, color: "var(--err)", background: "var(--err-bg)", border: "1px solid var(--err-bd)", borderRadius: 9, padding: "10px 12px" }}>{error}</div>
                )}

                <button className="btn btn-primary" style={{ height: 42, justifyContent: "center", marginTop: 4 }}
                  onClick={handleCreate}
                  disabled={loading || (GITHUB_WEBHOOK_SLUGS.has(template) && !selectedRepo)}>
                  {loading ? "Creating…" : "Create agent"}
                </button>
              </>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div className="card" style={{ padding: "13px 15px", display: "flex", gap: 11, background: "var(--accent-weak)", borderColor: "var(--accent-ring)" }}>
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                style={{ color: "var(--accent-text)", flexShrink: 0, marginTop: 1 }}>
                <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z" /><path d="M19 15l.75 2.25L22 18l-2.25.75L19 21l-.75-2.25L16 18l2.25-.75z" />
              </svg>
              <div style={{ fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.5 }}>
                Describe what the agent should do in plain English. Conduct drafts the block graph and flags the credentials it needs — you can refine it on the canvas.
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Describe your agent</label>
              <textarea value={nlPrompt} onChange={e => setNlPrompt(e.target.value)} rows={5}
                placeholder="When a PR is labeled needs-review, have an agent review the diff for security issues and post a summary to #eng-reviews. Require a human approval before it can be merged."
                style={{ ...ni, height: "auto", padding: "10px 12px", resize: "vertical", lineHeight: 1.5 }} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Project</label>
                <select value={selectedProjectId} onChange={e => setSelectedProjectId(e.target.value)} style={ni}>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Environment</label>
                <select value={selectedEnvId} onChange={e => setSelectedEnvId(e.target.value)} style={ni}>
                  {environments.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </div>
            </div>

            {error && (
              <div style={{ fontSize: 12.5, color: "var(--err)", background: "var(--err-bg)", border: "1px solid var(--err-bd)", borderRadius: 9, padding: "10px 12px" }}>{error}</div>
            )}

            <button className="btn btn-accent" style={{ height: 42, justifyContent: "center", marginTop: 4, opacity: nlPrompt.trim() ? 1 : 0.5, cursor: nlPrompt.trim() ? "pointer" : "not-allowed" }}
              onClick={handleGenerate} disabled={!nlPrompt.trim() || generating}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z" />
              </svg>
              {generating ? "Generating…" : "Generate agent"}
            </button>
          </div>
        )}
      </div>
    </AppShell>
  )
}
