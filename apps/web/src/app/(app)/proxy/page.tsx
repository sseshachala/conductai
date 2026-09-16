"use client"

import AppShell from "@/components/AppShell"
import GatewayProfileSettings from "@/components/settings/GatewayProfileSettings"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"

export default function ProxyGatewaysPage() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""
  const { role } = useGuardRole()

  return (
    <AppShell>
      <div style={{ maxWidth: 960, padding: "20px 24px" }}>
        <h2 style={{ fontSize: 18, fontWeight: 650, margin: "8px 0 4px" }}>
          Gateways
        </h2>
        <p style={{ fontSize: 13, color: "var(--text-3)", margin: "0 0 20px" }}>
          Route agent LLM traffic through Conduct so Guard can enforce prompt and response rules. Push upstream keys to the selected vault environment.
        </p>
        <GatewayProfileSettings workspaceId={workspaceId} isAdmin={role === "admin"} />
      </div>
    </AppShell>
  )
}
