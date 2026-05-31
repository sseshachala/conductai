"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import GuardNav from "@/components/guard/GuardNav"

interface TeamPrefs {
  alert_channel: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
}

export default function GuardSettingsPage() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()

  const [prefs, setPrefs] = useState<TeamPrefs>({
    alert_channel: null,
    notify_on_block: true,
    notify_on_budget: true,
  })
  const [channelInput, setChannelInput] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [channelSaved, setChannelSaved] = useState(false)
  const [savingChannel, setSavingChannel] = useState(false)

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const buildHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken()
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    return headers
  }, [getToken])

  const workspaceQuery = activeWorkspace ? `?workspace_id=${activeWorkspace.id}` : ""

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/guard/teams/me${workspaceQuery}`, { headers })
      if (!res.ok) throw new Error(`Failed to load team (${res.status})`)
      const data = await res.json()
      setPrefs({
        alert_channel: data.alert_channel ?? null,
        notify_on_block: data.notify_on_block ?? true,
        notify_on_budget: data.notify_on_budget ?? true,
      })
      setChannelInput(data.alert_channel ?? "")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [base, buildHeaders, workspaceQuery])

  useEffect(() => {
    load()
  }, [load])

  async function patch(body: Partial<TeamPrefs>) {
    const headers = await buildHeaders()
    const qs = activeWorkspace ? `?workspace_id=${activeWorkspace.id}` : ""
    const res = await fetch(`${base}/guard/teams/me${qs}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
    return res.json()
  }

  async function handleSaveChannel() {
    setSavingChannel(true)
    try {
      const data = await patch({ alert_channel: channelInput || null })
      setPrefs(p => ({ ...p, alert_channel: data.alert_channel }))
      setChannelSaved(true)
      setTimeout(() => setChannelSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSavingChannel(false)
    }
  }

  async function handleToggle(field: "notify_on_block" | "notify_on_budget", value: boolean) {
    try {
      const data = await patch({ [field]: value })
      setPrefs(p => ({ ...p, [field]: data[field] }))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    }
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-stone-900">Guard</h1>
          <p className="text-sm text-stone-500 mt-0.5">Policy enforcement and spend controls for your team.</p>
        </div>

        <GuardNav />

        {loading ? (
          <div className="text-sm text-stone-400 py-8 text-center">Loading settings...</div>
        ) : error ? (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3">{error}</div>
        ) : (
          <div className="space-y-5">
            {/* Notifications section */}
            <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-100">
              <div className="px-5 py-4">
                <h2 className="text-sm font-semibold text-stone-900">Notifications</h2>
                <p className="text-xs text-stone-500 mt-0.5">
                  Guard alerts go to this Slack channel when a policy fires or a budget threshold is reached.
                </p>
              </div>

              {/* Slack channel input */}
              <div className="px-5 py-4 space-y-2">
                <label className="text-xs font-medium text-stone-700">Slack channel</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={channelInput}
                    onChange={e => setChannelInput(e.target.value)}
                    placeholder="#guard-alerts"
                    className="w-56 text-sm border border-stone-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    onKeyDown={e => { if (e.key === "Enter") handleSaveChannel() }}
                  />
                  <button
                    onClick={handleSaveChannel}
                    disabled={savingChannel}
                    className="text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
                  >
                    {savingChannel ? "Saving..." : "Save"}
                  </button>
                  {channelSaved && (
                    <span className="text-xs text-emerald-600 font-medium">Saved</span>
                  )}
                </div>
              </div>

              {/* Notify on block/warn toggle */}
              <div className="px-5 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-stone-800">Notify on block / warn</p>
                  <p className="text-xs text-stone-500 mt-0.5">Send a Slack message whenever a policy blocks or warns a developer.</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={prefs.notify_on_block}
                    onChange={e => handleToggle("notify_on_block", e.target.checked)}
                  />
                  <div className="w-10 h-5 bg-stone-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-indigo-400 rounded-full peer peer-checked:after:translate-x-5 peer-checked:bg-indigo-600 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all" />
                </label>
              </div>

              {/* Notify on budget toggle */}
              <div className="px-5 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-stone-800">Notify on budget threshold</p>
                  <p className="text-xs text-stone-500 mt-0.5">Send a Slack message when monthly spend reaches the alert threshold.</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={prefs.notify_on_budget}
                    onChange={e => handleToggle("notify_on_budget", e.target.checked)}
                  />
                  <div className="w-10 h-5 bg-stone-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-indigo-400 rounded-full peer peer-checked:after:translate-x-5 peer-checked:bg-indigo-600 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all" />
                </label>
              </div>
            </div>

            {/* Info box */}
            <div className="bg-indigo-50 border border-indigo-200 rounded-xl px-5 py-4 space-y-1.5">
              <p className="text-xs font-medium text-indigo-800">Setup checklist</p>
              <p className="text-xs text-indigo-700">
                Invite the Conduct AI Slack bot to your alert channel:{" "}
                <code className="bg-indigo-100 px-1 py-0.5 rounded font-mono">/invite @ConductAI</code>
              </p>
              <p className="text-xs text-indigo-700">
                No Slack credentials yet?{" "}
                <a href="/settings/environments" className="underline hover:text-indigo-900">
                  Add them in Settings &rarr; Environments
                </a>
                .
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
