"use client"

import { createContext, useContext, useState, useEffect, type ReactNode } from "react"
import { useAuth, useUser } from "@clerk/nextjs"
import { useWorkspace } from "./WorkspaceContext"

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

export const VIEWER_PERMISSIONS: GuardPermissions = {
  canEditPolicies:    false,
  canEditSettings:    false,
  canEditBudgets:     false,
  canViewAllActivity: false,
  canViewAllSpend:    false,
  canViewOwnSpend:    false,
  canExportActivity:  false,
}

export const ADMIN_PERMISSIONS: GuardPermissions = {
  canEditPolicies:    true,
  canEditSettings:    true,
  canEditBudgets:     true,
  canViewAllActivity: true,
  canViewAllSpend:    true,
  canViewOwnSpend:    true,
  canExportActivity:  true,
}

export function permissionsFromList(perms: string[]): GuardPermissions {
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

interface GuardRoleState {
  role: GuardRole | null
  permissions: GuardPermissions
  loading: boolean
}

const GuardRoleContext = createContext<GuardRoleState>({
  role: "admin",
  permissions: ADMIN_PERMISSIONS,
  loading: false,
})

// Only mount this inside ClerkProvider (i.e. AppShellInnerWithAuth)
export function GuardRoleClerkProvider({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const { user } = useUser()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const email = user?.primaryEmailAddress?.emailAddress ?? null

  const [role, setRole] = useState<GuardRole | null>(null)
  const [permissions, setPermissions] = useState<GuardPermissions>(VIEWER_PERMISSIONS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!workspaceId || !isLoaded || !isSignedIn) { setLoading(false); return }
    let cancelled = false
    setLoading(true)

    async function fetch_() {
      try {
        const token = await getToken()
        if (!token) { if (!cancelled) setLoading(false); return }
        const params = new URLSearchParams({ workspace_id: workspaceId! })
        if (email) params.set("email", email)
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/me/permissions?${params}`,
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
  }, [workspaceId, isLoaded, isSignedIn, getToken, email])

  return (
    <GuardRoleContext.Provider value={{ role, permissions, loading }}>
      {children}
    </GuardRoleContext.Provider>
  )
}

export function GuardRoleAdminProvider({ children }: { children: ReactNode }) {
  return (
    <GuardRoleContext.Provider value={{ role: "admin", permissions: ADMIN_PERMISSIONS, loading: false }}>
      {children}
    </GuardRoleContext.Provider>
  )
}

export function useGuardRoleContext(): GuardRoleState {
  return useContext(GuardRoleContext)
}
