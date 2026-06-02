"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import AppShell from "@/components/AppShell"

interface TeamPrefs {
  alert_channel: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
}

export default function GuardSettingsPage() {
  return <AppShell><SettingsContent /></AppShell>
}

function SettingsContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)

  const [prefs, setPrefs] = useState<TeamPrefs>({
    alert_channel: null,
    notify_on_block: true,
    notify_on_budget: true,
  })
  const [channelInput, setChannelInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [installed, setInstalled] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [channelSaved, setChannelSaved] = useState(false)
  const [savingChannel, setSavingChannel] = useState(false)

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const wsId = activeWorkspace?.id ?? null

  const isAdmin = permissions.canEditSettings

  async function authHeaders(): Promise<Record<string, string>> {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }

  const load = useCallback(async () => {
    if (!wsId) return
    setLoading(true)
    setError(null)
    setInstalled(true)
    try {
      const headers = await authHeaders()
      const res = await fetch(`${base}/guard/teams/me?workspace_id=${wsId}`, { headers })
      if (res.status === 404) { setInstalled(false); setLoading(false); return }
      if (!res.ok) throw new Error(`Failed to load team (${res.status})`)
      const data = await res.json()
      setPrefs({
        alert_channel: data.alert_channel ?? null,
        notify_on_block: data.notify_on_block ?? true,
        notify_on_budget: data.notify_on_budget ?? true,
      })
      // Strip leading # if stored with prefix (legacy)
      setChannelInput((data.alert_channel ?? "").replace(/^#+/, ""))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings")
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, wsId])

  useEffect(() => {
    load()
  }, [load])

  async function patch(body: Partial<TeamPrefs>) {
    if (!wsId) return
    const headers = await authHeaders()
    const res = await fetch(`${base}/guard/teams/me?workspace_id=${wsId}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
    return res.json()
  }

  async function handleSaveChannel() {
    setSavingChannel(true)
    const stripped = channelInput.replace(/^#+/, "")
    try {
      await patch({ alert_channel: stripped || null })
      setChannelInput(stripped)
      setPrefs(p => ({ ...p, alert_channel: stripped || null }))
      setChannelSaved(true)
      setTimeout(() => setChannelSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSavingChannel(false)
    }
  }

  async function handleToggle(field: "notify_on_block" | "notify_on_budget", value: boolean) {
    setPrefs(p => ({ ...p, [field]: value }))
    try {
      await patch({ [field]: value })
    } catch (e) {
      setPrefs(p => ({ ...p, [field]: !value }))
      setError(e instanceof Error ? e.message : "Save failed")
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-xl font-semibold text-stone-900">Settings</h1>
          <p className="text-sm text-stone-500 mt-0.5">Policy enforcement and spend controls for your team.</p>
        </div>

        {loading ? (
          <div className="text-sm text-stone-400 py-8 text-center">Loading settings...</div>
        ) : error ? (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3">{error}</div>
        ) : (
          <div className="space-y-5">
            {/* View-only notice for non-admin roles */}
            {!isAdmin && resolvedRole !== null && (
              <p className="text-xs text-stone-500 bg-stone-50 border border-stone-200 rounded-lg px-4 py-2.5">
                View only — contact your admin to make changes.
              </p>
            )}

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
                  <div className="flex items-center w-56 border border-stone-300 rounded-lg overflow-hidden focus-within:ring-1 focus-within:ring-indigo-500">
                    <span className="px-2 py-1.5 text-sm text-stone-400 bg-stone-50 border-r border-stone-200 select-none">#</span>
                    <input
                      type="text"
                      value={channelInput}
                      onChange={e => isAdmin && setChannelInput(e.target.value.replace(/^#+/, ""))}
                      placeholder="guard-alerts"
                      disabled={!isAdmin}
                      className="flex-1 text-sm px-2 py-1.5 focus:outline-none bg-white disabled:text-stone-400 disabled:cursor-not-allowed"
                      onKeyDown={e => { if (e.key === "Enter" && isAdmin) handleSaveChannel() }}
                    />
                  </div>
                  {isAdmin && (
                    <button
                      onClick={handleSaveChannel}
                      disabled={savingChannel}
                      className="text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
                    >
                      {savingChannel ? "Saving..." : "Save"}
                    </button>
                  )}
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
                <label className={`relative inline-flex items-center ${isAdmin ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}>
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={prefs.notify_on_block}
                    disabled={!isAdmin}
                    onChange={e => isAdmin && handleToggle("notify_on_block", e.target.checked)}
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
                <label className={`relative inline-flex items-center ${isAdmin ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}>
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={prefs.notify_on_budget}
                    disabled={!isAdmin}
                    onChange={e => isAdmin && handleToggle("notify_on_budget", e.target.checked)}
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
  )
}
