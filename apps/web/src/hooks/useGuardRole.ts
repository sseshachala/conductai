"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

export type GuardRole = "admin" | "security" | "developer" | "viewer"

export interface GuardPermissions {
  canEditPolicies:    boolean
  canEditSettings:    boolean
  canEditBudgets:     boolean
  canViewAllActivity: boolean
  canViewAllSpend:    boolean
  canViewOwnSpend:    boolean
  canExportActivity:  boolean
}

const VIEWER_PERMISSIONS: GuardPermissions = {
  canEditPolicies:    false,
  canEditSettings:    false,
  canEditBudgets:     false,
  canViewAllActivity: false,
  canViewAllSpend:    false,
  canViewOwnSpend:    false,
  canExportActivity:  false,
}

function permissionsFromList(perms: string[]): GuardPermissions {
  const has = (p: string) => perms.includes(p)
  return {
    canEditPolicies:    has("guard.policies.edit"),
    canEditSettings:    has("guard.settings.edit"),
    canEditBudgets:     has("guard.spend.budgets.edit"),
    canViewAllActivity: has("guard.activity.view_all"),
    canViewAllSpend:    has("guard.spend.view_all"),
    canViewOwnSpend:    has("guard.spend.view_own"),
    canExportActivity:  has("guard.activity.export"),
  }
}

export const ROLE_PERMISSIONS = {
  admin:     permissionsFromList(["guard.policies.edit","guard.settings.edit","guard.spend.budgets.edit","guard.activity.view_all","guard.spend.view_all","guard.spend.view_own","guard.activity.export"]),
  security:  permissionsFromList(["guard.policies.edit","guard.activity.view_all","guard.spend.view_all","guard.spend.view_own","guard.activity.export"]),
  developer: permissionsFromList(["guard.activity.view_own","guard.spend.view_own"]),
  viewer:    permissionsFromList([]),
}

export function useGuardRole(
  _teamId: string | null,
  workspaceId: string | null,
): { role: GuardRole | null; permissions: GuardPermissions; loading: boolean } {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const effectiveWorkspaceId = workspaceId ?? activeWorkspace?.id ?? null

  const [role, setRole] = useState<GuardRole | null>(null)
  const [permissions, setPermissions] = useState<GuardPermissions>(VIEWER_PERMISSIONS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!effectiveWorkspaceId || !isLoaded || !isSignedIn) return
    let cancelled = false
    setLoading(true)

    async function fetch_() {
      try {
        const token = await getToken()
        if (!token) { if (!cancelled) setLoading(false); return }
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/me/permissions?workspace_id=${effectiveWorkspaceId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        if (res.ok) {
          const data: { role: string; permissions: string[] } = await res.json()
          if (!cancelled) {
            setRole(data.role as GuardRole)
            setPermissions(data.permissions.length > 0 ? permissionsFromList(data.permissions) : VIEWER_PERMISSIONS)
          }
        }
      } catch {
        // degrade to viewer
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetch_()
    return () => { cancelled = true }
  }, [effectiveWorkspaceId, isLoaded, isSignedIn, getToken])

  return { role, permissions, loading }
}
