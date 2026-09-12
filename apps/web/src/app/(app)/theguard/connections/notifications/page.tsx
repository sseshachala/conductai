"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import NotificationsPanel from "@/features/guard/connections/notifications/Panel"

export default function GuardNotificationsPage() {
  return (
    <AppShell>
      <NotificationsContent />
    </AppShell>
  )
}

function NotificationsContent() {
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const router = useRouter()

  useEffect(() => {
    if (resolvedRole !== null && !permissions.canEditSettings) router.replace("/theguard")
  }, [resolvedRole, permissions.canEditSettings, router])

  return (
    <GuardShell>
      <NotificationsPanel
        workspaceId={activeWorkspace?.id ?? null}
        isAdmin={permissions.canEditSettings}
      />
    </GuardShell>
  )
}
