"use client"

import { useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

// Local-dev bypass: when Clerk publishable key is unset, ClerkProvider is
// not mounted (see apps/web/src/app/layout.tsx). Calling useAuth() in that
// state throws. Route around it with a hook-shaped stub so pages continue
// to render — the API grants DEV_WORKSPACE_ID/admin without a token.
const CLERK_ENABLED = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

function useAuthSafe() {
  if (CLERK_ENABLED) return useAuth()
  return { getToken: async () => null } as ReturnType<typeof useAuth>
}

/**
 * Returns a fetch wrapper that automatically attaches the Clerk Bearer token
 * and X-Workspace-ID header to every request. Token is read from auth context
 * only — never from URL params or user input.
 */
export function useAuthFetch() {
  const { getToken } = useAuthSafe()
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
