"use client"

import { useEffect, useState } from "react"

interface WorkflowDetail {
  id: string
  name: string
  default_mode: string
  environment_id: string | null
  default_max_turns: number | null
}

interface Environment {
  id: string
  name: string
}

interface Props {
  workflowId: string
  getToken: (() => Promise<string | null>) | null | undefined
  onDelete: () => void
}

export default function WorkflowSettingsPanel({ workflowId, getToken, onDelete }: Props) {
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null)
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [loading, setLoading] = useState(true)
  const [turnsInput, setTurnsInput] = useState("")
  const [turnsSaving, setTurnsSaving] = useState(false)
  const [turnsSaved, setTurnsSaved] = useState(false)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function headers(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const wsId = typeof document !== "undefined"
      ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
    if (wsId) h["X-Workspace-ID"] = wsId
    return h
  }

  useEffect(() => {
    async function load() {
      try {
        const h = await headers()
        const [wfRes, envRes] = await Promise.all([
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers: h }),
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers: h }),
        ])
        if (wfRes.ok) {
          const wf = await wfRes.json()
          setWorkflow(wf)
          setTurnsInput(wf.default_max_turns ? String(wf.default_max_turns) : "")
        }
        if (envRes.ok) setEnvironments(await envRes.json())
      } finally {
        setLoading(false)
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  async function saveEnvironment(envId: string) {
    const h = await headers()
    h["Content-Type"] = "application/json"
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/set-environment`, {
      method: "POST", headers: h, body: JSON.stringify({ environment_id: envId })
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      setError(body.detail ?? `Failed to save environment (${res.status})`)
      return
    }
    setWorkflow(prev => prev ? { ...prev, environment_id: envId } : prev)
  }

  async function saveTurnBudget() {
    const val = turnsInput.trim() === "" ? null : parseInt(turnsInput.trim(), 10)
    if (val !== null && (isNaN(val) || val < 1)) return
    setTurnsSaving(true)
    try {
      const h = await headers()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/turn-settings`, {
        method: "PATCH", headers: h, body: JSON.stringify({ default_max_turns: val })
      })
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
      const h = await headers()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, {
        method: "DELETE",
        headers: h,
      })
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

            {/* Mode */}
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="eyebrow" style={{ marginBottom: 4 }}>Execution mode</p>
              <p style={{ color: "var(--text)", fontWeight: 500, textTransform: "capitalize" }}>
                {workflow?.default_mode ?? "dag"}
              </p>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                dag = sequential blocks · agentic = AI decides order
              </p>
            </div>

            {/* Environment */}
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Environment</p>
              {environments.length === 0 ? (
                <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  No environments configured. Add one in workspace Settings.
                </p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {environments.map(env => (
                    <label
                      key={env.id}
                      style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }}
                    >
                      <input
                        type="radio"
                        name="environment"
                        value={env.id}
                        checked={workflow?.environment_id === env.id}
                        onChange={() => saveEnvironment(env.id)}
                        style={{ accentColor: "var(--text)" }}
                      />
                      <span style={{ fontSize: 13, color: "var(--text)" }}>{env.name}</span>
                    </label>
                  ))}
                </div>
              )}
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
