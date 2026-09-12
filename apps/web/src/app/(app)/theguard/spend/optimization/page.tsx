"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import CostPerformancePanel from "@/features/guard/spend/optimization/Panel"

export default function GuardCostPerformancePage() {
  return (
    <AppShell>
      <CostPerformanceContent />
    </AppShell>
  )
}

function CostPerformanceContent() {
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const router = useRouter()

  useEffect(() => {
    if (resolvedRole !== null && !permissions.canEditSettings) router.replace("/theguard")
  }, [resolvedRole, permissions.canEditSettings, router])

  return (
    <GuardShell>
      <CostPerformancePanel
        workspaceId={activeWorkspace?.id ?? null}
        isAdmin={permissions.canEditSettings}
      />
    </GuardShell>
  )
}
