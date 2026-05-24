"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface WorkflowDetail {
  id: string
  name: string
  default_mode: string
  environment_id: string | null
}

interface Environment {
  id: string
  name: string
}

export default function AgentSettingsPage() {
  const { id: workflowId } = useParams<{ id: string }>()
  const { getToken } = useAuth()
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null)
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [loading, setLoading] = useState(true)

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
        if (wfRes.ok) setWorkflow(await wfRes.json())
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

              {/* Danger zone */}
              <div className="rounded-xl border border-red-100 bg-red-50 px-5 py-4">
                <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-3">Danger zone</p>
                <p className="text-sm text-red-700 mb-3">Deleting this agent removes all its runs and history permanently.</p>
                <button className="text-xs font-medium text-white bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg transition-colors">
                  Delete agent
                </button>
              </div>

            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
