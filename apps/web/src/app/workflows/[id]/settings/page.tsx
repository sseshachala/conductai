"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

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

export default function AgentSettingsPage() {
  const { id: workflowId } = useParams<{ id: string }>()
  const router = useRouter()
  const { getToken } = useAuth()
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null)
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [loading, setLoading] = useState(true)
  const [turnsInput, setTurnsInput] = useState("")
  const [turnsSaving, setTurnsSaving] = useState(false)
  const [turnsSaved, setTurnsSaved] = useState(false)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function headers(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const wsId = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
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
  }, [workflowId])

  async function saveEnvironment(envId: string) {
    const h = await headers()
    h["Content-Type"] = "application/json"
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/set-environment`, {
      method: "POST", headers: h, body: JSON.stringify({ environment_id: envId })
    })
    setWorkflow(prev => prev ? { ...prev, environment_id: envId } : prev)
  }

  async function saveTurnBudget() {
    const val = turnsInput.trim() === "" ? null : parseInt(turnsInput.trim(), 10)
    if (val !== null && (isNaN(val) || val < 1)) return
    setTurnsSaving(true)
    try {
      const h = await headers()
      h["Content-Type"] = "application/json"
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/turn-settings`, {
        method: "PATCH", headers: h, body: JSON.stringify({ default_max_turns: val })
      })
      setWorkflow(prev => prev ? { ...prev, default_max_turns: val } : prev)
      setTurnsSaved(true)
      setTimeout(() => setTurnsSaved(false), 2000)
    } finally {
      setTurnsSaving(false)
    }
  }

  async function deleteAgent() {
    if (!workflow || deleteConfirmValue !== workflow.name) return
    setDeleteError(null)
    setDeleting(true)
    try {
      const h = await headers()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, {
        method: "DELETE",
        headers: h,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setDeleteError(body.detail ?? "Could not delete agent. Please try again.")
        return
      }
      router.push("/workflows")
      router.refresh()
    } catch {
      setDeleteError("Could not delete agent — check your connection.")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AppShell noPadding>
      <div className="flex-1 overflow-auto">
        <div className="mx-auto max-w-2xl px-6 py-10">
          <h2 className="text-xl font-semibold text-stone-900 mb-6">Agent Settings</h2>

          {loading ? (
            <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-16 rounded-xl bg-stone-100 animate-pulse" />)}</div>
          ) : (
            <div className="space-y-6">

              {/* Name */}
              <div className="rounded-xl border border-stone-200 bg-white px-5 py-4">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-1">Agent name</p>
                <p className="text-stone-900 font-medium">{workflow?.name}</p>
                <p className="text-xs text-stone-400 mt-1">Rename from the agents list or canvas header.</p>
              </div>

              {/* Mode */}
              <div className="rounded-xl border border-stone-200 bg-white px-5 py-4">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-1">Execution mode</p>
                <p className="text-stone-900 font-medium capitalize">{workflow?.default_mode ?? "dag"}</p>
                <p className="text-xs text-stone-400 mt-1">dag = sequential blocks · agentic = AI decides order</p>
              </div>

              {/* Environment */}
              <div className="rounded-xl border border-stone-200 bg-white px-5 py-4">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Environment</p>
                {environments.length === 0 ? (
                  <p className="text-sm text-stone-400">No environments configured. Add one in workspace Settings.</p>
                ) : (
                  <div className="space-y-2">
                    {environments.map(env => (
                      <label key={env.id} className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="radio"
                          name="environment"
                          value={env.id}
                          checked={workflow?.environment_id === env.id}
                          onChange={() => saveEnvironment(env.id)}
                          className="accent-stone-900"
                        />
                        <span className="text-sm text-stone-800">{env.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Turn budget */}
              <div className="rounded-xl border border-stone-200 bg-white px-5 py-4">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-1">Default turn budget</p>
                <p className="text-xs text-stone-400 mb-3">
                  Minimum AI turns for every run of this agent — webhook, scheduled, and manual.
                  Leave empty to use the per-run estimate (recommended for most agents).
                  Autopilot agents typically need 35–50.
                </p>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min="1"
                    max="200"
                    placeholder="e.g. 35"
                    value={turnsInput}
                    onChange={e => setTurnsInput(e.target.value)}
                    className="w-28 border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-400"
                  />
                  <button
                    onClick={saveTurnBudget}
                    disabled={turnsSaving}
                    className="px-4 py-2 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 transition-colors disabled:opacity-50"
                  >
                    {turnsSaved ? "Saved ✓" : turnsSaving ? "Saving…" : "Save"}
                  </button>
                  {turnsInput.trim() !== "" && (
                    <button
                      onClick={() => { setTurnsInput(""); }}
                      className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
                    >
                      Clear (use estimate)
                    </button>
                  )}
                </div>
              </div>

              {/* Danger zone */}
              <div className="rounded-xl border border-red-100 bg-red-50 px-5 py-4">
                <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-3">Danger zone</p>
                <p className="text-sm text-red-700 mb-3">Deleting this agent removes all its runs and history permanently.</p>
                {deleteConfirmOpen ? (
                  <div className="space-y-2">
                    <p className="text-xs text-red-700">
                      Type <strong>{workflow?.name ?? "this agent"}</strong> to permanently delete it.
                    </p>
                    <div className="flex gap-2">
                      <input
                        value={deleteConfirmValue}
                        onChange={e => setDeleteConfirmValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter") deleteAgent()
                          if (e.key === "Escape") {
                            setDeleteConfirmOpen(false)
                            setDeleteConfirmValue("")
                            setDeleteError(null)
                          }
                        }}
                        placeholder={workflow?.name ?? "Agent name"}
                        className="flex-1 border border-red-200 rounded-lg px-3 py-2 text-sm text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-red-300"
                      />
                      <button
                        onClick={deleteAgent}
                        disabled={deleting || deleteConfirmValue !== (workflow?.name ?? "")}
                        className="text-xs font-medium text-white bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg transition-colors disabled:opacity-40"
                      >
                        {deleting ? "Deleting…" : "Delete"}
                      </button>
                      <button
                        onClick={() => {
                          setDeleteConfirmOpen(false)
                          setDeleteConfirmValue("")
                          setDeleteError(null)
                        }}
                        className="text-xs font-medium text-stone-600 border border-stone-200 hover:bg-stone-50 px-4 py-2 rounded-lg transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                    {deleteError && <p className="text-xs text-red-600">{deleteError}</p>}
                  </div>
                ) : (
                  <button
                    onClick={() => { setDeleteConfirmOpen(true); setDeleteConfirmValue(""); setDeleteError(null) }}
                    className="text-xs font-medium text-white bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg transition-colors"
                  >
                    Delete agent
                  </button>
                )}
              </div>

            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
