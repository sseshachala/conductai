"use client"

import { useEffect, useState } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { workflows, guard } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"

interface WorkflowDetail {
  id: string
  name: string
  default_max_turns: number | null
  agent_identity_required: boolean
}


interface Props {
  workflowId: string
  getToken: (() => Promise<string | null>) | null | undefined
  onDelete: () => void
}

export default function WorkflowSettingsPanel({ workflowId, getToken, onDelete }: Props) {
  const { activeWorkspace } = useWorkspace()
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [turnsInput, setTurnsInput] = useState("")
  const [guardEnabled, setGuardEnabled] = useState(true)
  const [agentIdentityRequired, setAgentIdentityRequired] = useState(true)
  const [agentIdentitySaving, setAgentIdentitySaving] = useState(false)
  const [persona, setPersona] = useState<string>("")
  const [guardSaving, setGuardSaving] = useState(false)
  const [workspaceRuntimePersona, setWorkspaceRuntimePersona] = useState<string>("conservative")
  const [turnsSaving, setTurnsSaving] = useState(false)
  const [turnsSaved, setTurnsSaved] = useState(false)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function makeAuthFetch(): AuthFetch {
    const wsId = activeWorkspace?.id ?? null
    return async (url, opts) => {
      const headers: Record<string, string> = {
        ...(opts?.headers as Record<string, string> | undefined),
      }
      if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
      if (wsId) headers["X-Workspace-ID"] = wsId
      return fetch(url, { ...opts, headers })
    }
  }

  useEffect(() => {
    async function load() {
      try {
        const authFetch = makeAuthFetch()
        const wf = await workflows.get(authFetch, workflowId)
        setWorkflow(wf)
        setTurnsInput(wf.default_max_turns ? String(wf.default_max_turns) : "")
        setGuardEnabled(wf.guard_enabled !== false)
        setAgentIdentityRequired(wf.agent_identity_required !== false)
        setPersona(wf.runtime_persona || "")
        // Resolve what "Inherit from workspace" currently means.
        try {
          const pData = await guard.config.persona(authFetch)
          if (pData?.workspace_runtime_persona) setWorkspaceRuntimePersona(pData.workspace_runtime_persona)
        } catch { /* non-fatal — fall back to 'conservative' */ }
      } finally {
        setLoading(false)
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

async function saveGuard(enabled = guardEnabled) {
    setGuardSaving(true)
    try {
      const authFetch = makeAuthFetch()
      const res = await workflows.update(authFetch, workflowId, { guard_enabled: enabled, runtime_persona: persona || null })
      if (!res.ok) throw new Error("Failed to save Guard settings")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save Guard settings")
    } finally {
      setGuardSaving(false)
    }
  }

  async function saveAgentIdentity(required = agentIdentityRequired) {
    setAgentIdentitySaving(true)
    try {
      const authFetch = makeAuthFetch()
      const res = await workflows.update(authFetch, workflowId, { agent_identity_required: required })
      if (!res.ok) throw new Error("Failed to save Agent Identity setting")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save Agent Identity setting")
    } finally {
      setAgentIdentitySaving(false)
    }
  }

  async function saveTurnBudget() {
    const val = turnsInput.trim() === "" ? null : parseInt(turnsInput.trim(), 10)
    if (val !== null && (isNaN(val) || val < 1)) return
    setTurnsSaving(true)
    try {
      const authFetch = makeAuthFetch()
      const res = await workflows.setTurnSettings(authFetch, workflowId, { default_max_turns: val })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? `Failed to save turn budget (${res.status})`)
        return
      }
      setWorkflow(prev => prev ? { ...prev, default_max_turns: val } : prev)
      setTurnsSaved(true)
      setTimeout(() => setTurnsSaved(false), 2000)
    } finally {
      setTurnsSaving(false)
    }
  }

  async function deleteAgent() {
    if (!workflow || deleteConfirmValue !== workflow.name) return
    setError(null)
    setDeleting(true)
    try {
      const authFetch = makeAuthFetch()
      const res = await workflows.remove(authFetch, workflowId)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? "Could not delete agent. Please try again.")
        return
      }
      onDelete()
    } catch {
      setError("Could not delete agent — check your connection.")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex-1 overflow-auto">
      <div style={{ maxWidth: 672, margin: "0 auto", padding: "40px 24px" }}>
        <h2 style={{ fontSize: 20, fontWeight: 600, color: "var(--text)", marginBottom: 24 }}>Workflow Settings</h2>

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[1, 2, 3].map(i => (
              <div
                key={i}
                style={{
                  height: 64,
                  borderRadius: 12,
                  background: "var(--surface-3)",
                  animation: "pulse 1.5s ease-in-out infinite",
                }}
              />
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

            {/* Name */}
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="eyebrow" style={{ marginBottom: 4 }}>Workflow name</p>
              <p style={{ color: "var(--text)", fontWeight: 500 }}>{workflow?.name}</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                Rename from the workflows list or canvas header.
              </p>
            </div>


            {/* Guard — workflow-level on/off + persona override */}
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="eyebrow" style={{ marginBottom: 4 }}>ConductGuard</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                Govern every brain block in this workflow. When on, Guard checks each tool call
                against the selected persona policy set and PII-redacts context sent to the LLM.
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                <button
                  type="button"
                  onClick={() => { const next = !guardEnabled; setGuardEnabled(next); saveGuard(next) }}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${guardEnabled ? "bg-violet-600" : "bg-stone-300"}`}
                  role="switch"
                  aria-checked={guardEnabled}
                >
                  <span className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${guardEnabled ? "translate-x-4" : "translate-x-0"}`} />
                </button>
                <span style={{ fontSize: 13, color: "var(--text-2)" }}>{guardEnabled ? "Enforcing" : "Bypassed (use with caution)"}</span>
              </div>
              {guardEnabled && (
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Surface</label>
                  <a href="/theguard/policies?persona=agent" style={{ display: "inline-flex", alignItems: "center", background: "var(--accent-bg, #ede9fe)", color: "var(--accent, #6d28d9)", borderRadius: 6, padding: "3px 10px", fontSize: 12, fontWeight: 600, textDecoration: "none" }}>
                    Agent ↗
                  </a>
                </div>
              )}
              {guardSaving && <span style={{ fontSize: 12, color: "var(--text-3)" }}>Saving…</span>}
            </div>

            {/* Agent Identity */}
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="eyebrow" style={{ marginBottom: 4 }}>Agent Identity Required</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                Each run mints a short-lived token scoped to that run.
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <button
                  type="button"
                  disabled
                  className="relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent bg-violet-600 opacity-60 cursor-not-allowed"
                  role="switch"
                  aria-checked={true}
                >
                  <span className="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow translate-x-4" />
                </button>
                <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Short-lived token per run</span>
              </div>
            </div>

            {/* Turn budget */}
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="eyebrow" style={{ marginBottom: 4 }}>Default turn budget</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                Minimum AI turns for every run of this agent — webhook, scheduled, and manual.
                Leave empty to use the per-run estimate (recommended for most agents).
                Autopilot agents typically need 35&ndash;50.
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <input
                  type="number"
                  min="1"
                  max="200"
                  placeholder="e.g. 35"
                  value={turnsInput}
                  onChange={e => setTurnsInput(e.target.value)}
                  style={{
                    width: 112,
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: "8px 12px",
                    fontSize: 13,
                    background: "var(--surface)",
                    color: "var(--text)",
                    outline: "none",
                  }}
                />
                <button
                  onClick={saveTurnBudget}
                  disabled={turnsSaving}
                  className="btn btn-primary btn-sm"
                  style={{ opacity: turnsSaving ? 0.5 : 1 }}
                >
                  {turnsSaved ? "Saved \u2713" : turnsSaving ? "Saving\u2026" : "Save"}
                </button>
                {turnsInput.trim() !== "" && (
                  <button
                    onClick={() => setTurnsInput("")}
                    className="btn btn-ghost btn-sm"
                  >
                    Clear (use estimate)
                  </button>
                )}
              </div>
            </div>

            {/* Danger zone */}
            <div
              style={{
                borderRadius: 12,
                border: "1px solid var(--err-bd)",
                background: "var(--err-bg)",
                padding: "16px 20px",
              }}
            >
              <p className="eyebrow" style={{ color: "var(--err)", marginBottom: 12 }}>
                Danger zone
              </p>
              <p style={{ fontSize: 13, color: "var(--err)", marginBottom: 12 }}>
                Deleting this workflow removes all its runs and history permanently.
              </p>
              {deleteConfirmOpen ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <p style={{ fontSize: 12, color: "var(--err)" }}>
                    Type <strong>{workflow?.name ?? "this agent"}</strong> to permanently delete it.
                  </p>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      value={deleteConfirmValue}
                      onChange={e => setDeleteConfirmValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") deleteAgent()
                        if (e.key === "Escape") {
                          setDeleteConfirmOpen(false)
                          setDeleteConfirmValue("")
                          setError(null)
                        }
                      }}
                      placeholder={workflow?.name ?? "Agent name"}
                      style={{
                        flex: 1,
                        border: "1px solid var(--err-bd)",
                        borderRadius: 8,
                        padding: "8px 12px",
                        fontSize: 13,
                        background: "var(--surface)",
                        color: "var(--text)",
                        outline: "none",
                      }}
                    />
                    <button
                      onClick={deleteAgent}
                      disabled={deleting || deleteConfirmValue !== (workflow?.name ?? "")}
                      style={{
                        fontSize: 12,
                        fontWeight: 500,
                        color: "#fff",
                        background: "var(--err)",
                        border: "none",
                        borderRadius: 8,
                        padding: "8px 16px",
                        cursor: deleting || deleteConfirmValue !== (workflow?.name ?? "") ? "not-allowed" : "pointer",
                        opacity: deleting || deleteConfirmValue !== (workflow?.name ?? "") ? 0.4 : 1,
                        transition: "opacity 0.15s",
                      }}
                    >
                      {deleting ? "Deleting\u2026" : "Delete"}
                    </button>
                    <button
                      onClick={() => {
                        setDeleteConfirmOpen(false)
                        setDeleteConfirmValue("")
                        setError(null)
                      }}
                      className="btn btn-ghost btn-sm"
                    >
                      Cancel
                    </button>
                  </div>
                  {error && (
                    <p style={{ fontSize: 12, color: "var(--err)" }}>{error}</p>
                  )}
                </div>
              ) : (
                <button
                  onClick={() => { setDeleteConfirmOpen(true); setDeleteConfirmValue(""); setError(null) }}
                  className="btn btn-ghost"
                  style={{ color: "var(--err)" }}
                >
                  Delete workflow
                </button>
              )}
            </div>

          </div>
        )}
      </div>
    </div>
  )
}
