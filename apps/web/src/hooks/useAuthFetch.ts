"use client"

import { useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

/**
 * Returns a fetch wrapper that automatically attaches the Clerk Bearer token
 * and X-Workspace-ID header to every request. Token is read from auth context
 * only — never from URL params or user input.
 */
export function useAuthFetch() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()

  const authFetch = useCallback(
    async (url: string, options: RequestInit = {}): Promise<Response> => {
      const token = await getToken()
      const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> | undefined),
      }
      if (token) headers["Authorization"] = `Bearer ${token}`
      if (activeWorkspace?.id) headers["X-Workspace-ID"] = activeWorkspace.id
      return fetch(url, { ...options, headers })
    },
    [getToken, activeWorkspace],
  )

  return { authFetch, workspaceId: activeWorkspace?.id ?? null }
}
