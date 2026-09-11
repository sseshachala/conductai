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
  // CLERK_ENABLED is a module-level compile-time constant, so the branch
  // is stable across renders — Rules of Hooks is not actually violated.
  // eslint-disable-next-line react-hooks/rules-of-hooks
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
      const buildHeaders = (bearer: string | null) => {
        const h: Record<string, string> = {
          ...(options.headers as Record<string, string> | undefined),
        }
        if (bearer) h["Authorization"] = `Bearer ${bearer}`
        if (activeWorkspace?.id) h["X-Workspace-ID"] = activeWorkspace.id
        return h
      }

      const token = await getToken()
      const res = await fetch(url, { ...options, headers: buildHeaders(token) })

      // 401-then-retry: Clerk's SDK refreshes session tokens in a background
      // web worker. First page load can fire an authFetch before the worker
      // has minted a fresh JWT — first call returns 401, retry with a
      // just-refreshed token succeeds. One retry only; genuine auth
      // failures still surface to the caller after that.
      if (res.status === 401) {
        const retried = await getToken({ skipCache: true } as never)
        if (retried && retried !== token) {
          return fetch(url, { ...options, headers: buildHeaders(retried) })
        }
      }
      return res
    },
    [getToken, activeWorkspace],
  )

  return { authFetch, workspaceId: activeWorkspace?.id ?? null }
}
