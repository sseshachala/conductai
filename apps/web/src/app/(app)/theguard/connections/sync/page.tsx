"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import SyncPanel from "@/features/guard/connections/sync/Panel"
import { GuardSectionTabs, CONNECTIONS_TABS } from "@/features/guard/GuardSectionTabs"

export default function GuardSyncPage() {
  return (
    <AppShell>
      <SyncContent />
    </AppShell>
  )
}

function SyncContent() {
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const router = useRouter()

  useEffect(() => {
    if (resolvedRole !== null && !permissions.canEditSettings) router.replace("/theguard")
  }, [resolvedRole, permissions.canEditSettings, router])

  return (
    <GuardShell>
      <GuardSectionTabs tabs={CONNECTIONS_TABS} />
      <SyncPanel
        workspaceId={activeWorkspace?.id ?? null}
        isAdmin={permissions.canEditSettings}
      />
    </GuardShell>
  )
}
