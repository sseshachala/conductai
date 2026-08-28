"use client"

import { useState, useEffect, useRef } from "react"
import { useAuth } from "@clerk/nextjs"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import AppShell from "@/components/AppShell"
import { TabBar } from "@/components/TabBar"
import { useWorkspace } from "@/lib/WorkspaceContext"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"
import MembersManager from "@/components/settings/MembersManager"
import PreferencesPanel from "@/components/settings/PreferencesPanel"
import ProxySettings from "@/components/settings/ProxySettings"
import LLMPrimitivesPanel from "@/components/settings/LLMPrimitivesPanel"

type Tab = "credentials" | "llm_primitives" | "members" | "preferences" | "proxy"

const TAB_LABELS: Record<Tab, string> = {
  credentials: "Vault",
  llm_primitives: "LLM Model Primitives",
  preferences: "Appearance",
  members: "Members & roles",
  proxy: "Proxy",
}

export default function SettingsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <SettingsPageWithAuth />
  return <SettingsPageInner isAdmin={true} workspaceId="" getToken={null} />
}

function SettingsPageWithAuth() {
  const { userId, getToken } = useAuth()
  const { authFetch } = useAuthFetch()
  const [isAdmin, setIsAdmin] = useState(false)
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""

  useEffect(() => {
    if (!workspaceId || !userId) return
    async function check() {
      try {
        const res = await authFetch(`${API}/projects/${workspaceId}/my-role`)
        if (!res.ok) { setIsAdmin(false); return }
        const data: { role: string } = await res.json()
        setIsAdmin(data.role === "admin")
      } catch { setIsAdmin(false) }
    }
    check()
  }, [workspaceId, userId])

  return <SettingsPageInner isAdmin={isAdmin} workspaceId={workspaceId} getToken={getToken} />
}

// ── Organisation name editor ──────────────────────────────────────────────────

function OrgNameEditor({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { authFetch } = useAuthFetch()
  const [orgId, setOrgId] = useState<string | null>(null)
  const [orgName, setOrgName] = useState("")
  const [inputValue, setInputValue] = useState("")
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle")
  const [errorMsg, setErrorMsg] = useState("")
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await authFetch(`${API}/organizations`)
        if (!res.ok || cancelled) return
        const data = await res.json()
        const org = Array.isArray(data) && data.length > 0 ? data[0] : null
        if (!org || cancelled) return
        setOrgId(org.id)
        setOrgName(org.name)
        setInputValue(org.name)
      } catch {
        // Non-fatal: leave empty
      } finally {
        if (!cancelled) setLoading(false)
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
      const res = await authFetch(`${API}/organizations/${orgId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
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
            disabled={loading}
            style={{ height: 36, border: "1px solid var(--border)", borderRadius: 8, padding: "0 12px", fontSize: 13, background: "var(--surface)", color: "var(--text)", outline: "none", width: "100%", opacity: loading ? 0.5 : 1 }}
            placeholder={loading ? "Loading…" : "Your organisation name"}
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
  const tabs = (["credentials", "llm_primitives", "preferences", "proxy", ...(isAdmin ? ["members"] : [])] as Tab[])
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

        <div style={{ marginBottom: 24 }}>
          <TabBar tabs={tabs} labels={TAB_LABELS} activeTab={activeTab} onSelect={setActiveTab} />
        </div>

        <div role="tabpanel" id="tabpanel-credentials" aria-labelledby="tab-credentials" hidden={activeTab !== "credentials"}>
          <EnvironmentsManager isAdmin={isAdmin} />
        </div>
        <div role="tabpanel" id="tabpanel-llm_primitives" aria-labelledby="tab-llm_primitives" hidden={activeTab !== "llm_primitives"}>
          <LLMPrimitivesPanel workspaceId={workspaceId} isAdmin={isAdmin} />
        </div>
        <div role="tabpanel" id="tabpanel-preferences" aria-labelledby="tab-preferences" hidden={activeTab !== "preferences"}>
          <PreferencesPanel />
        </div>
        {isAdmin && (
          <div role="tabpanel" id="tabpanel-members" aria-labelledby="tab-members" hidden={activeTab !== "members"}>
            <MembersManager />
          </div>
        )}
        <div role="tabpanel" id="tabpanel-proxy" aria-labelledby="tab-proxy" hidden={activeTab !== "proxy"}>
          <ProxySettings workspaceId={workspaceId} getToken={getToken} />
        </div>
      </div>
    </AppShell>
  )
}
