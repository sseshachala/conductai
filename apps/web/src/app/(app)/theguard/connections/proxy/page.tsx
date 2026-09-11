"use client"

import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import ProxySettings from "@/components/settings/ProxySettings"
import { useWorkspace } from "@/lib/WorkspaceContext"

export default function GuardProxyConnectionsPage() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""

  return (
    <AppShell>
      <GuardShell>
        <div style={{ maxWidth: 960 }}>
          <h2 style={{ fontSize: 18, fontWeight: 650, margin: "8px 0 4px" }}>
            Proxy &amp; gateways
          </h2>
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: "0 0 20px" }}>
            Route agent LLM traffic through Conduct so Guard can enforce prompt and response rules. Push upstream keys to the selected vault environment.
          </p>
          <ProxySettings workspaceId={workspaceId} />
        </div>
      </GuardShell>
    </AppShell>
  )
}
