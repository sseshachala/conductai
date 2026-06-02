"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type GuardRole = "admin" | "security" | "editor" | "viewer"

export interface GuardPermissions {
  canEditPolicies: boolean      // toggle enable/disable, add, delete rules
  canEditSettings: boolean      // change Slack channel, notification toggles
  canEditBudgets: boolean       // set team or per-developer budget limits
  canViewAllActivity: boolean   // see all developers' events (not just own)
  canViewAllSpend: boolean      // see all developers' spend breakdown
}

// ---------------------------------------------------------------------------
// Permission matrix
// ---------------------------------------------------------------------------

export const ROLE_PERMISSIONS: Record<GuardRole, GuardPermissions> = {
  admin:    { canEditPolicies: true,  canEditSettings: true,  canEditBudgets: true,  canViewAllActivity: true,  canViewAllSpend: true  },
  security: { canEditPolicies: true,  canEditSettings: false, canEditBudgets: false, canViewAllActivity: true,  canViewAllSpend: true  },
  editor:   { canEditPolicies: false, canEditSettings: false, canEditBudgets: false, canViewAllActivity: true,  canViewAllSpend: true  },
  viewer:   { canEditPolicies: false, canEditSettings: false, canEditBudgets: false, canViewAllActivity: false, canViewAllSpend: false  },
}

const VIEWER_PERMISSIONS = ROLE_PERMISSIONS["viewer"]

// ---------------------------------------------------------------------------
// Guard API role → UI role mapping
// ---------------------------------------------------------------------------

function mapGuardRole(apiRole: string): GuardRole {
  if (apiRole === "owner" || apiRole === "admin") return "admin"
  if (apiRole === "security") return "security"
  // "developer" and anything else → viewer
  return "viewer"
}

// ---------------------------------------------------------------------------
// Platform workspace role → UI role mapping
// ---------------------------------------------------------------------------

function mapPlatformRole(apiRole: string): GuardRole {
  if (apiRole === "admin") return "admin"
  if (apiRole === "editor") return "editor"
  return "viewer"
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

interface UseGuardRoleResult {
  role: GuardRole | null   // null while loading
  permissions: GuardPermissions
  loading: boolean
}

export function useGuardRole(
  teamId: string | null,
  workspaceId: string | null,
): UseGuardRoleResult {
  const { getToken, userId } = useAuth()
  const [role, setRole] = useState<GuardRole | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""

    async function resolve() {
      // Wait until both teamId and workspaceId have been determined
      if (teamId === null && workspaceId === null) {
        // Still waiting on upstream resolution — keep loading
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
