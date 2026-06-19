"use client"

export type { GuardRole, GuardPermissions } from "@/lib/GuardRoleContext"
export { ADMIN_PERMISSIONS, VIEWER_PERMISSIONS, permissionsFromList } from "@/lib/GuardRoleContext"
import { useGuardRoleContext } from "@/lib/GuardRoleContext"
import type { GuardRole, GuardPermissions } from "@/lib/GuardRoleContext"

// _teamId and workspaceId are unused — context manages workspace via useWorkspace()
export function useGuardRole(
  _teamId?: string | null,
  _workspaceId?: string | null,
): { role: GuardRole | null; permissions: GuardPermissions; loading: boolean } {
  return useGuardRoleContext()
}
