"use client"

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react"
import { useAuth } from "@clerk/nextjs"

export interface Workspace {
  id: string
  name: string
  owner_id: string
  is_approved: boolean
  workflow_count: number
}

interface WorkspaceContextValue {
  workspaces: Workspace[]
  activeWorkspace: Workspace | null
  setActiveWorkspace: (ws: Workspace) => void
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  permissions: string[]
  permissionsRole: string | null
  permissionsLoading: boolean
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  workspaces: [],
  activeWorkspace: null,
  setActiveWorkspace: () => {},
  loading: true,
  error: null,
  refresh: async () => {},
  permissions: [],
  permissionsRole: null,
  permissionsLoading: false,
})

export function useWorkspace() {
  return useContext(WorkspaceContext)
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith(`${name}=`))?.split("=")[1] ?? null
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${value}; path=/; max-age=31536000; Secure; SameSite=Lax`
}

interface Props {
  children: ReactNode
  clerkEnabled?: boolean
}

export function WorkspaceProvider({ children, clerkEnabled }: Props) {
  if (clerkEnabled) return <WorkspaceProviderWithAuth>{children}</WorkspaceProviderWithAuth>
  return <WorkspaceProviderInner getToken={null}>{children}</WorkspaceProviderInner>
}

function WorkspaceProviderWithAuth({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  return <WorkspaceProviderInner getToken={getToken} clerkReady={isLoaded && !!isSignedIn}>{children}</WorkspaceProviderInner>
}

function WorkspaceProviderInner({
  children,
  getToken,
  clerkReady = true,
}: {
  children: ReactNode
  getToken: (() => Promise<string | null>) | null
  clerkReady?: boolean
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [activeWorkspace, setActiveWorkspaceState] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [permissions, setPermissions] = useState<string[]>([])
  const [permissionsRole, setPermissionsRole] = useState<string | null>(null)
  const [permissionsLoading, setPermissionsLoading] = useState(false)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, { headers })
      if (!res.ok) {
        setError(`Failed to load workspaces (${res.status})`)
        return
      }
      const data: Workspace[] = await res.json()
      if (!Array.isArray(data)) { setError("Unexpected response from workspace API"); return }
      setWorkspaces(data)

      // Restore previously active workspace from cookie, or default to first
      const storedId = getCookie("delegator_project_id")
      const match = storedId ? data.find(w => w.id === storedId) : null
      const resolved = match ?? data[0] ?? null
      if (resolved) {
        setActiveWorkspaceState(resolved)
        setCookie("delegator_project_id", resolved.id)
        setCookie("delegator_project_name", encodeURIComponent(resolved.name))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error loading workspaces")
    } finally {
      setLoading(false)
    }
  }, [getToken])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (!activeWorkspace || !clerkReady) return
    let cancelled = false
    setPermissionsLoading(true)
    async function fetchPerms() {
      try {
        const token = getToken ? await getToken() : null
        if (!token) { if (!cancelled) setPermissionsLoading(false); return }
        const headers = { "Authorization": `Bearer ${token}` }
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/me/permissions?workspace_id=${activeWorkspace!.id}`,
          { headers }
        )
        if (res.ok) {
          const data: { role: string; permissions: string[] } = await res.json()
          if (!cancelled) { setPermissions(data.permissions); setPermissionsRole(data.role) }
        }
      } catch {
        // non-fatal — Guard pages degrade to viewer permissions
      } finally {
        if (!cancelled) setPermissionsLoading(false)
      }
    }
    fetchPerms()
    return () => { cancelled = true }
  }, [activeWorkspace?.id, clerkReady, getToken])

  function setActiveWorkspace(ws: Workspace) {
    setActiveWorkspaceState(ws)
    setCookie("delegator_project_id", ws.id)
    setCookie("delegator_project_name", encodeURIComponent(ws.name))
  }

  return (
    <WorkspaceContext.Provider value={{ workspaces, activeWorkspace, setActiveWorkspace, loading, error, refresh, permissions, permissionsRole, permissionsLoading }}>
      {children}
    </WorkspaceContext.Provider>
  )
}
