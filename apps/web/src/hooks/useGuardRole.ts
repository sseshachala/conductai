"use client"

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
  _workspaceId: string | null,
): { role: GuardRole | null; permissions: GuardPermissions; loading: boolean } {
  const { permissions, permissionsRole, permissionsLoading } = useWorkspace()
  const role = (permissionsRole as GuardRole) ?? null
  return {
    role,
    permissions: permissions.length > 0 ? permissionsFromList(permissions) : VIEWER_PERMISSIONS,
    loading: permissionsLoading,
  }
}
