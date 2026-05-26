"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"
import MembersManager from "@/components/settings/MembersManager"
import AuditLog from "@/components/settings/AuditLog"
import PreferencesPanel from "@/components/settings/PreferencesPanel"
import ApiKeysManager from "@/components/settings/ApiKeysManager"
import { useWorkspace } from "@/lib/WorkspaceContext"

type Tab = "environments" | "members" | "audit" | "preferences" | "api-keys"

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

function SettingsPageInner({ isAdmin, workspaceId, getToken }: { isAdmin: boolean; workspaceId: string; getToken: (() => Promise<string | null>) | null }) {
  const tabs = (["environments", "preferences", ...(isAdmin ? ["members", "audit", "api-keys"] : [])] as Tab[])
  const [activeTab, setActiveTab] = useState<Tab>("environments")
  const [showTip, setShowTip] = useState(true)

  return (
    <AppShell>
      {showTip && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm w-full rounded-xl bg-amber-50 border border-amber-200 shadow-lg px-4 py-3 flex items-start gap-3">
          <span className="text-amber-500 text-base leading-none mt-0.5 shrink-0">⚠</span>
          <p className="text-sm text-amber-800 leading-relaxed flex-1">
            <span className="font-semibold">Add credentials before running agents.</span>{" "}
            Create an environment (e.g. "Production"), add your GitHub and Slack tokens inside it, then assign the environment to your agent on the canvas.
          </p>
          <button
            onClick={() => setShowTip(false)}
            className="shrink-0 text-amber-400 hover:text-amber-700 transition-colors ml-1 text-base leading-none"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-stone-900">Settings</h1>
          <span className="text-xs text-stone-400">Tokens encrypted at rest</span>
        </div>

        <div className="flex bg-stone-100 rounded-lg p-1 mb-6 w-fit">
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${
                activeTab === tab
                  ? "bg-white text-stone-900 shadow-sm"
                  : "text-stone-500 hover:text-stone-800"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {activeTab === "environments" && <EnvironmentsManager isAdmin={isAdmin} />}
        {activeTab === "preferences" && <PreferencesPanel />}
        {activeTab === "members" && isAdmin && <MembersManager />}
        {activeTab === "audit" && isAdmin && <AuditLog workspaceId={workspaceId} getToken={getToken} />}
        {activeTab === "api-keys" && isAdmin && <ApiKeysManager />}
      </div>
    </AppShell>
  )
}
