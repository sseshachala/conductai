"use client"

import { useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { sessionFetch } from "@/lib/sessionFetch"

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
      const headers = new Headers(options.headers)
      if (activeWorkspace?.id) headers.set("X-Workspace-ID", activeWorkspace.id)
      const response = await sessionFetch(
        url,
        { ...options, headers },
        CLERK_ENABLED ? getToken : null,
      )
      // sessionFetch already retries once on 401 with a refreshed token.
      // If we still get 401, the user's session is genuinely unauthed
      // (expired token, revoked workspace access, etc.) — route them to
      // /sign-in with a return-here parameter so they land back on the
      // page they wanted after login. Guarded against a redirect loop
      // for /sign-in and /sign-up (#1888).
      if (response.status === 401 && typeof window !== "undefined") {
        _redirectToSignIn()
      }
      return response
    },
    [getToken, activeWorkspace],
  )

  return { authFetch, workspaceId: activeWorkspace?.id ?? null }
}

// Guard against a redirect loop when the user is already ON /sign-in
// (Clerk's own API calls can 401 during the sign-in flow itself). Also
// scope to app routes — a public marketing page fetching a preview API
// that happens to 401 shouldn't yank the visitor away.
function _redirectToSignIn(): void {
  const path = window.location.pathname
  if (path === "/sign-in" || path === "/sign-up" || path.startsWith("/sign-in/") || path.startsWith("/sign-up/")) {
    return
  }
  const back = encodeURIComponent(path + window.location.search)
  window.location.href = `/sign-in?redirect_url=${back}`
}
