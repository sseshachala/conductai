"use client"

import { authEnabled } from "@/lib/auth/runtime"


import { useAuth } from "@/lib/auth/client"
import AppShell from "@/components/AppShell"
import { TabBar } from "@/components/TabBar"
import { TAB_LABELS, TABS } from "./_components/shared"
import { useAgentIdentity } from "./_components/useAgentIdentity"
import { TokenTabs } from "./_components/TokenTabs"
import { SessionAndIntegrationTabs } from "./_components/SessionAndIntegrationTabs"
import { IdentitiesTab } from "./_components/IdentitiesTab"

export default function AgentIdentityPage() {
  const clerkEnabled = authEnabled()
  if (clerkEnabled) return <WithAuth />
  return <Inner getToken={null} />
}

function WithAuth() {
  const { getToken } = useAuth()
  return <Inner getToken={getToken} />
}

function Inner({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const s = useAgentIdentity()
  const { activeTab, selectTab } = s

  return (
    <AppShell>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: 0 }}>Agent Identity</h1>
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>
            Your CLI token and per-run tokens issued to workflow agents. Guard validates authority at the execution boundary — short-lived run tokens mean permissions expire with the action, not the session. There are no stale approvals.
          </p>
        </div>

        {/* Vertical tab rail (left) + content column (right) — mirrors SettingsShell / GuardShell pattern. */}
        <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-[180px_minmax(0,1fr)]">
          <TabBar tabs={TABS} labels={TAB_LABELS} activeTab={activeTab} onSelect={selectTab} orientation="vertical" />
          <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 20 }}>

        <TokenTabs s={s} />

        <SessionAndIntegrationTabs s={s} />

        <IdentitiesTab s={s} />

          </div>{/* /content column */}
        </div>{/* /grid */}
      </div>
    </AppShell>
  )
}
