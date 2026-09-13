"use client"

import AppShell from "@/components/AppShell"
import ProxySettings from "@/components/settings/ProxySettings"
import { useWorkspace } from "@/lib/WorkspaceContext"

export default function ProxyGatewaysPage() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""

  return (
    <AppShell>
      <div style={{ maxWidth: 960, padding: "20px 24px" }}>
        <h2 style={{ fontSize: 18, fontWeight: 650, margin: "8px 0 4px" }}>
          Proxy &amp; Gateways
        </h2>
        <p style={{ fontSize: 13, color: "var(--text-3)", margin: "0 0 20px" }}>
          Route agent LLM traffic through Conduct so Guard can enforce prompt and response rules. Push upstream keys to the selected vault environment.
        </p>
        <ProxySettings workspaceId={workspaceId} />
      </div>
    </AppShell>
  )
}
