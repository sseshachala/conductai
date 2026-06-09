"use client"

import { useState, useEffect, useRef } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"
import MembersManager from "@/components/settings/MembersManager"
import PreferencesPanel from "@/components/settings/PreferencesPanel"
import ApiKeysManager from "@/components/settings/ApiKeysManager"
import { useWorkspace } from "@/lib/WorkspaceContext"

type Tab = "credentials" | "members" | "preferences" | "api-keys"

const TAB_LABELS: Record<Tab, string> = {
  credentials: "Environments",
  preferences: "Appearance",
  members: "Members & roles",
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
      window.dispatchEvent(new CustomEvent("conduct:org-name-changed", { detail: { name: updated.name } }))
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
    <div style={{ marginBottom: 32, paddingBottom: 32, borderBottom: "1px solid var(--border)" }}>
      <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-2)", marginBottom: 16, marginTop: 0 }}>Organisation</h2>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, maxWidth: 384 }}>
          <label
            htmlFor="org-name-input"
            style={{ fontSize: 13, fontWeight: 500, color: "var(--text-2)" }}
          >
            Organisation name
          </label>
          <input
            id="org-name-input"
            type="text"
            value={inputValue}
            onChange={e => { setInputValue(e.target.value); setStatus("idle"); setErrorMsg("") }}
            onKeyDown={e => { if (e.key === "Enter" && isDirty) handleSave() }}
            style={{ height: 36, border: "1px solid var(--border)", borderRadius: 8, padding: "0 12px", fontSize: 13, background: "var(--surface)", color: "var(--text)", outline: "none", width: "100%" }}
            placeholder="Your organisation name"
          />
          <span style={{ fontSize: 12, color: "var(--text-3)" }}>
            This name appears across your workspace and shared playbooks.
          </span>
        </div>
        <button
          onClick={handleSave}
          disabled={!isDirty || status === "saving"}
          className="btn btn-primary btn-sm"
          style={{ marginTop: 20 }}
        >
          {status === "saving" ? "Saving…" : "Save"}
        </button>
      </div>
      {status === "saved" && (
        <p style={{ marginTop: 8, fontSize: 12, fontWeight: 500, color: "var(--ok)" }}>Saved</p>
      )}
      {status === "error" && errorMsg && (
        <p style={{ marginTop: 8, fontSize: 12, color: "var(--err)" }}>{errorMsg}</p>
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
        <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 50, maxWidth: 380, width: "100%", borderRadius: 12, background: "var(--warn-bg)", border: "1px solid var(--warn-bd)", padding: "12px 16px", display: "flex", alignItems: "flex-start", gap: 12 }}>
          <span style={{ color: "var(--warn)", flexShrink: 0 }}>⚠</span>
          <p style={{ color: "var(--warn)", fontSize: 13, flex: 1, margin: 0, lineHeight: 1.5 }}>
            <span style={{ fontWeight: 600, color: "var(--warn)" }}>Add credentials before running agents.</span>{" "}
            Go to Credentials, add your GitHub token, Slack token, and any other API keys. Agents pick them up automatically — no extra config needed.
          </p>
          <button
            onClick={dismissTip}
            className="btn btn-ghost btn-sm btn-icon"
            style={{ color: "var(--warn)" }}
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 24px" }}>
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 25, fontWeight: 680, letterSpacing: "-.02em", color: "var(--text)", margin: 0 }}>
            Settings
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-3)", marginTop: 5, margin: "5px 0 0" }}>
            Connect tools, manage environments, members, appearance, and API access.
          </p>
        </div>

        {isAdmin && <OrgNameEditor getToken={getToken} />}

        <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 24 }}>
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                background: "none",
                border: "none",
                padding: "9px 14px",
                fontSize: 13.5,
                fontWeight: 600,
                cursor: "pointer",
                marginBottom: -1,
                color: activeTab === tab ? "var(--text)" : "var(--text-3)",
                borderBottom: activeTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
              }}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>

        {activeTab === "credentials" && <EnvironmentsManager isAdmin={isAdmin} />}
        {activeTab === "preferences" && <PreferencesPanel />}
        {activeTab === "members" && isAdmin && <MembersManager />}
        {activeTab === "api-keys" && isAdmin && <ApiKeysManager />}
      </div>
    </AppShell>
  )
}
