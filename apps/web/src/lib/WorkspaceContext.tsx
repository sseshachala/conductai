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
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  workspaces: [],
  activeWorkspace: null,
  setActiveWorkspace: () => {},
  loading: true,
  error: null,
  refresh: async () => {},
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
  const { getToken } = useAuth()
  return <WorkspaceProviderInner getToken={getToken}>{children}</WorkspaceProviderInner>
}

function WorkspaceProviderInner({
  children,
  getToken,
}: {
  children: ReactNode
  getToken: (() => Promise<string | null>) | null
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [activeWorkspace, setActiveWorkspaceState] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  function setActiveWorkspace(ws: Workspace) {
    setActiveWorkspaceState(ws)
    setCookie("delegator_project_id", ws.id)
    setCookie("delegator_project_name", encodeURIComponent(ws.name))
  }

  return (
    <WorkspaceContext.Provider value={{ workspaces, activeWorkspace, setActiveWorkspace, loading, error, refresh }}>
      {children}
    </WorkspaceContext.Provider>
  )
}
