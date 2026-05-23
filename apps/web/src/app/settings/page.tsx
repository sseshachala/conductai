"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import CredentialsManager from "@/components/settings/CredentialsManager"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"
import MembersManager from "@/components/settings/MembersManager"
import { useWorkspace } from "@/lib/WorkspaceContext"

type Tab = "integrations" | "environments" | "members"

export default function SettingsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <SettingsPageWithAuth />
  return <SettingsPageInner isAdmin={true} />
}

function SettingsPageWithAuth() {
  const { getToken, userId } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    if (!activeWorkspace || !userId) return
    async function check() {
      try {
        const headers: Record<string, string> = {}
        if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
        const ws = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
        if (ws) headers["X-Workspace-Id"] = ws
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members`, { headers })
        if (!res.ok) return
        const members: { clerk_user_id: string; role: string }[] = await res.json()
        setIsAdmin(members.find(m => m.clerk_user_id === userId)?.role === "admin")
      } catch { /* stay false */ }
    }
    check()
  }, [activeWorkspace?.id, userId])

  return <SettingsPageInner isAdmin={isAdmin} />
}

function SettingsPageInner({ isAdmin }: { isAdmin: boolean }) {
  const tabs = (["integrations", "environments", ...(isAdmin ? ["members"] : [])] as Tab[])
  const [activeTab, setActiveTab] = useState<Tab>("integrations")

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-stone-900">Settings</h1>
          <span className="text-xs text-stone-400">Tokens encrypted at rest</span>
        </div>

        <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 flex items-start gap-3">
          <span className="text-amber-500 text-base leading-none mt-0.5">⚠</span>
          <p className="text-sm text-amber-800 leading-relaxed">
            <span className="font-semibold">Add credentials before running agents.</span>{" "}
            Create an environment under <strong>Environments</strong>, add your GitHub and Slack tokens under <strong>Integrations</strong>, then assign the environment to your agent on the canvas.
          </p>
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

        {activeTab === "integrations" && <CredentialsManager isAdmin={isAdmin} />}
        {activeTab === "environments" && <EnvironmentsManager isAdmin={isAdmin} />}
        {activeTab === "members" && isAdmin && <MembersManager />}
      </div>
    </AppShell>
  )
}
