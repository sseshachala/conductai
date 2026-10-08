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

// Module-level cache: one config fetch per workspace per page session, shared
// by every Guard page/hook. Failed lookups are evicted so a retry can succeed.
const teamIdCache = new Map<string, Promise<string>>()

function resolveTeamId(
  authFetch: Parameters<typeof guard.config.get>[0],
  wsId: string,
): Promise<string> {
  const cached = teamIdCache.get(wsId)
  if (cached) return cached
  const promise = (async () => {
    let data: any
    try {
      data = await guard.config.get(authFetch, wsId)
    } catch (err: any) {
      // Auto-install Guard if not yet configured (404)
      if (err?.message?.includes("404") || String(err).includes("404")) {
        await projects.guard.install(authFetch, wsId)
        data = await guard.config.get(authFetch, wsId)
      } else {
        throw err
      }
    }
    return data.workspace_id as string
  })()
  teamIdCache.set(wsId, promise)
  promise.catch(() => teamIdCache.delete(wsId))
  return promise
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
