"use client"

import { useState, useEffect, useRef } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"
import MembersManager from "@/components/settings/MembersManager"
import PreferencesPanel from "@/components/settings/PreferencesPanel"
import ApiKeysManager from "@/components/settings/ApiKeysManager"
import { useWorkspace } from "@/lib/WorkspaceContext"

type Tab = "credentials" | "members" | "preferences" | "api-keys"

const TAB_LABELS: Record<Tab, string> = {
  credentials: "Environments",
  preferences: "Preferences",
  members: "Members",
  "api-keys": "API Keys",
}

export default function SettingsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <SettingsPageWithAuth />
  return <SettingsPageInner isAdmin={true} workspaceId="" getToken={null} />
}

function SettingsPageWithAuth() {
  const { getToken, userId } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [isAdmin, setIsAdmin] = useState(true)
  const workspaceId = activeWorkspace?.id ?? ""

  useEffect(() => {
    if (!activeWorkspace || !userId) return
    async function check() {
      try {
        const headers: Record<string, string> = {}
        if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
        const ws = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
        if (ws) headers["X-Workspace-Id"] = ws
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace!.id}/members`, { headers })
        if (!res.ok) { setIsAdmin(true); return }
        const members: { clerk_user_id: string; role: string }[] = await res.json()
        if (members.length === 0) { setIsAdmin(true); return }
        setIsAdmin(members.find(m => m.clerk_user_id === userId)?.role === "admin")
      } catch { setIsAdmin(true) }
    }
    check()
  }, [activeWorkspace?.id, userId])

  return <SettingsPageInner isAdmin={isAdmin} workspaceId={workspaceId} getToken={getToken} />
}

// ── Organisation name editor ──────────────────────────────────────────────────

function OrgNameEditor({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const [orgId, setOrgId] = useState<string | null>(null)
  const [orgName, setOrgName] = useState("")
  const [inputValue, setInputValue] = useState("")
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle")
  const [errorMsg, setErrorMsg] = useState("")
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const headers: Record<string, string> = {}
        if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
        const res = await fetch(`${base}/organizations`, { headers })
        if (!res.ok || cancelled) return
        const data = await res.json()
        const org = Array.isArray(data) && data.length > 0 ? data[0] : null
        if (!org || cancelled) return
        setOrgId(org.id)
        setOrgName(org.name)
        setInputValue(org.name)
      } catch {
        // Non-fatal: leave empty
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  async function handleSave() {
    if (!orgId || inputValue.trim() === "" || inputValue === orgName) return
    setStatus("saving")
    setErrorMsg("")
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
      const res = await fetch(`${base}/organizations/${orgId}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ name: inputValue.trim() }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setErrorMsg(body?.detail ?? "Could not save — please try again.")
        setStatus("error")
        return
      }
      const updated = await res.json()
      setOrgName(updated.name)
      setInputValue(updated.name)
      setStatus("saved")
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)
      savedTimerRef.current = setTimeout(() => setStatus("idle"), 2000)
    } catch {
      setErrorMsg("Could not save — check your connection.")
      setStatus("error")
    }
  }

  const isDirty = inputValue !== orgName

  return (
    <div className="mb-8 pb-8 border-b border-stone-200">
      <h2 className="text-sm font-semibold text-stone-700 mb-4">Organisation</h2>
      <div className="flex items-center gap-3">
        <div className="flex flex-col gap-1 flex-1 max-w-sm">
          <label htmlFor="org-name-input" className="text-xs font-medium text-stone-500">
            Organisation name
          </label>
          <input
            id="org-name-input"
            type="text"
            value={inputValue}
            onChange={e => { setInputValue(e.target.value); setStatus("idle"); setErrorMsg("") }}
            onKeyDown={e => { if (e.key === "Enter" && isDirty) handleSave() }}
            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 bg-white outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300 transition-colors"
            placeholder="Your organisation name"
          />
        </div>
        <button
          onClick={handleSave}
          disabled={!isDirty || status === "saving"}
          className="mt-5 px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {status === "saving" ? "Saving…" : "Save"}
        </button>
      </div>
      {status === "saved" && (
        <p className="mt-2 text-xs text-green-600 font-medium">Saved</p>
      )}
      {status === "error" && errorMsg && (
        <p className="mt-2 text-xs text-red-600">{errorMsg}</p>
      )}
    </div>
  )
}

// ── Main settings page ────────────────────────────────────────────────────────

function SettingsPageInner({ isAdmin, workspaceId, getToken }: { isAdmin: boolean; workspaceId: string; getToken: (() => Promise<string | null>) | null }) {
  const tabs = (["credentials", "preferences", ...(isAdmin ? ["members", "api-keys"] : [])] as Tab[])
  const [activeTab, setActiveTab] = useState<Tab>("credentials")
  const [showTip, setShowTip] = useState(false)

  // Only show tip if user hasn't dismissed it before
  useEffect(() => {
    if (typeof window !== "undefined") {
      setShowTip(localStorage.getItem("conduct_settings_tip_dismissed") !== "1")
    }
  }, [])

  function dismissTip() {
    if (typeof window !== "undefined") {
      localStorage.setItem("conduct_settings_tip_dismissed", "1")
    }
    setShowTip(false)
  }

  return (
    <AppShell>
      {showTip && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm w-full rounded-xl bg-amber-50 border border-amber-200 shadow-lg px-4 py-3 flex items-start gap-3">
          <span className="text-amber-500 text-base leading-none mt-0.5 shrink-0">⚠</span>
          <p className="text-sm text-amber-800 leading-relaxed flex-1">
            <span className="font-semibold">Add credentials before running agents.</span>{" "}
            Go to Credentials, add your GitHub token, Slack token, and any other API keys. Agents pick them up automatically — no extra config needed.
          </p>
          <button
            onClick={dismissTip}
            className="shrink-0 text-amber-400 hover:text-amber-700 transition-colors ml-1 text-base leading-none"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-stone-900">Global Settings</h1>
          <span className="text-xs text-stone-400">Tokens encrypted at rest</span>
        </div>

        {isAdmin && <OrgNameEditor getToken={getToken} />}

        <div className="flex bg-stone-100 rounded-lg p-1 mb-6 w-fit">
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "bg-white text-stone-900 shadow-sm"
                  : "text-stone-500 hover:text-stone-800"
              }`}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
          <Link
            href="/settings/modules"
            className="px-4 py-1.5 rounded-md text-sm font-medium transition-colors text-stone-500 hover:text-stone-800"
          >
            Modules
          </Link>
        </div>

        {activeTab === "credentials" && <EnvironmentsManager isAdmin={isAdmin} />}
        {activeTab === "preferences" && <PreferencesPanel />}
        {activeTab === "members" && isAdmin && <MembersManager />}
        {activeTab === "api-keys" && isAdmin && <ApiKeysManager />}
      </div>
    </AppShell>
  )
}
