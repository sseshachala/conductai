"use client"

import { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from "react"
import { useAuth, useSession } from "@clerk/nextjs"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { sessionFetch, type GetSessionToken } from "./sessionFetch"

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
  const { getToken, isLoaded, isSignedIn, sessionId } = useAuth()
  const { session } = useSession()
  const pathname = usePathname()
  const authPage = /^\/(sign-in|sign-up|accept-invite)(\/|$)/.test(pathname)
  if (isLoaded && !isSignedIn && !authPage) return (
    <section className="mx-auto max-w-md p-8 space-y-4">
      <h1 className="text-xl font-semibold">Sign in to Conduct</h1>
      <p>Sign in or create an account to access your workspace.</p>
      <div className="flex gap-4">
        <Link href="/sign-in" className="underline">Sign in</Link>
        <Link href="/sign-up" className="underline">Create account</Link>
      </div>
    </section>
  )
  return <WorkspaceProviderInner key={sessionId ?? 'signed-out'} getToken={getToken} ready={isLoaded && !!isSignedIn && session?.status === 'active'}>{children}</WorkspaceProviderInner>
}

function WorkspaceProviderInner({
  children,
  getToken,
  ready = true,
}: {
  children: ReactNode
  getToken: GetSessionToken | null
  ready?: boolean
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [activeWorkspace, setActiveWorkspaceState] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestVersion = useRef(0)

  const refresh = useCallback(async () => {
    if (!ready) return
    const version = ++requestVersion.current
    setLoading(true)
    setError(null)
    try {
      const api = process.env.NEXT_PUBLIC_API_URL
      if (api === undefined) {
        setError("Workspace API is not configured. Set NEXT_PUBLIC_API_URL and restart the web server.")
        return
      }
      const res = await sessionFetch(`${api}/projects`, {}, getToken)
      if (version !== requestVersion.current) return
      if (!res.ok) {
        setError(`Failed to load workspaces (${res.status})`)
        return
      }
      const data: Workspace[] = await res.json()
      if (version !== requestVersion.current) return
      if (!Array.isArray(data)) { setError("Unexpected response from workspace API"); return }
      setWorkspaces(data)

      // Restore previously active workspace from cookie, or default to first
      const storedId = getCookie("delegator_project_id")
      const match = storedId ? data.find(w => w.id === storedId) : null
      const resolved = match ?? data[0] ?? null
      setActiveWorkspaceState(resolved)
      if (resolved) {
        setCookie("delegator_project_id", resolved.id)
        setCookie("delegator_project_name", encodeURIComponent(resolved.name))
      } else {
        setCookie("delegator_project_id", "")
        setCookie("delegator_project_name", "")
      }
    } catch (e) {
      if (version === requestVersion.current) setError(e instanceof Error ? e.message : "Network error loading workspaces")
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }, [getToken, ready])

  useEffect(() => {
    void refresh()
    return () => { requestVersion.current++ }
  }, [refresh])

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
