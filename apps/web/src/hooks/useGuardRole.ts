"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type GuardRole = "admin" | "security" | "developer" | "viewer"

export interface GuardPermissions {
  canEditPolicies: boolean
  canEditSettings: boolean
  canEditBudgets: boolean
  canViewAllActivity: boolean    // true = see all devs; false = own only
  canViewAllSpend: boolean       // true = see all devs; false = own only (viewer = hide entirely, use canViewOwnSpend)
  canViewOwnSpend: boolean       // developer sees own spend; viewer sees nothing
  canExportActivity: boolean     // CSV export — admin + security only
}

// ---------------------------------------------------------------------------
// Permission matrix
// ---------------------------------------------------------------------------

export const ROLE_PERMISSIONS: Record<GuardRole, GuardPermissions> = {
  admin:     { canEditPolicies: true,  canEditSettings: true,  canEditBudgets: true,  canViewAllActivity: true,  canViewAllSpend: true,  canViewOwnSpend: true,  canExportActivity: true  },
  security:  { canEditPolicies: true,  canEditSettings: false, canEditBudgets: false, canViewAllActivity: true,  canViewAllSpend: true,  canViewOwnSpend: true,  canExportActivity: true  },
  developer: { canEditPolicies: false, canEditSettings: false, canEditBudgets: false, canViewAllActivity: false, canViewAllSpend: false, canViewOwnSpend: true,  canExportActivity: false },
  viewer:    { canEditPolicies: false, canEditSettings: false, canEditBudgets: false, canViewAllActivity: false, canViewAllSpend: false, canViewOwnSpend: false, canExportActivity: false },
}

const VIEWER_PERMISSIONS = ROLE_PERMISSIONS["viewer"]

// ---------------------------------------------------------------------------
// Guard API role → UI role mapping
// ---------------------------------------------------------------------------

function mapGuardRole(apiRole: string): GuardRole {
  if (apiRole === "owner" || apiRole === "admin") return "admin"
  if (apiRole === "security") return "security"
  if (apiRole === "developer") return "developer"
  return "viewer"
}

// ---------------------------------------------------------------------------
// Platform workspace role → UI role mapping
// ---------------------------------------------------------------------------

function mapPlatformRole(apiRole: string): GuardRole {
  if (apiRole === "admin") return "admin"
  if (apiRole === "editor" || apiRole === "developer") return "developer"
  return "viewer"
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useGuardRole(
  teamId: string | null,
  workspaceId: string | null,
): { role: GuardRole | null; permissions: GuardPermissions; loading: boolean } {
  const { getToken, userId } = useAuth()
  const [role, setRole] = useState<GuardRole | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""

    async function resolve() {
      if (teamId === null && workspaceId === null) {
        return
      }
      if (!userId) {
        if (!cancelled) { setRole("viewer"); setLoading(false) }
        return
      }

      // ── Step 1: Try Guard team members endpoint ──────────────────────────
      if (teamId) {
        try {
          const token = await getToken()
          const h: Record<string, string> = {}
          if (token) h["Authorization"] = `Bearer ${token}`
          const res = await fetch(`${base}/guard/teams/${teamId}/members`, { headers: h })
          if (res.ok) {
            const members: { user_id: string; role: string }[] = await res.json()
            const member = members.find(m => m.user_id === userId)
            if (member) {
              if (!cancelled) { setRole(mapGuardRole(member.role)); setLoading(false) }
              return
            }
          }
        } catch {
          // fall through to platform fallback
        }
      }

      // ── Step 2: Platform workspace members fallback ──────────────────────
      if (workspaceId) {
        try {
          const token = await getToken()
          const h: Record<string, string> = {
            "X-Workspace-ID": workspaceId,
          }
          if (token) h["Authorization"] = `Bearer ${token}`
          const res = await fetch(`${base}/projects/${workspaceId}/members`, { headers: h })
          if (res.ok) {
            const members: { clerk_user_id: string; role: string }[] = await res.json()
            const member = members.find(m => m.clerk_user_id === userId)
            if (member) {
              if (!cancelled) { setRole(mapPlatformRole(member.role)); setLoading(false) }
              return
            }
          }
        } catch {
          // fall through to safe default
        }
      }

      // ── Step 3: Safe default ─────────────────────────────────────────────
      if (!cancelled) { setRole("viewer"); setLoading(false) }
    }

    setLoading(true)
    setRole(null)
    resolve()
    return () => { cancelled = true }
  }, [teamId, workspaceId, userId])

  return {
    role,
    permissions: role !== null ? ROLE_PERMISSIONS[role] : VIEWER_PERMISSIONS,
    loading,
  }
}
