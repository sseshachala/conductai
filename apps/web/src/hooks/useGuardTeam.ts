"use client"

import { useState, useEffect } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { guard, projects } from "@/lib/api"

interface GuardTeamResult {
  teamId: string | null
  loading: boolean
  error: string | null
}

// guard.config.get is cached per workspace by lib/api/sharedCache (shared with
// the app shell and every Guard page); failures are evicted so a retry works.
async function resolveTeamId(
  authFetch: Parameters<typeof guard.config.get>[0],
  wsId: string,
): Promise<string> {
  let data: any
  try {
    data = await guard.config.get(authFetch, wsId)
  } catch (err: any) {
    // Auto-install Guard if not yet configured (404); install invalidates the cache.
    if (err?.message?.includes("404") || String(err).includes("404")) {
      await projects.guard.install(authFetch, wsId)
      data = await guard.config.get(authFetch, wsId)
    } else {
      throw err
    }
  }
  return data.workspace_id as string
}

export function useGuardTeam(): GuardTeamResult {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace, loading: wsLoading } = useWorkspace()
  const [teamId, setTeamId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function resolve() {
      if (wsLoading) return
      if (!activeWorkspace) {
        setLoading(false)
        setError("No workspace")
        return
      }
      try {
        const id = await resolveTeamId(authFetch, activeWorkspace.id)
        if (!cancelled) { setTeamId(id); setLoading(false) }
      } catch {
        if (!cancelled) { setLoading(false); setError("Failed to load Guard team") }
      }
    }
    setLoading(true)
    setTeamId(null)
    setError(null)
    resolve()
    return () => { cancelled = true }
  }, [wsLoading, activeWorkspace?.id])

  return { teamId, loading, error }
}
