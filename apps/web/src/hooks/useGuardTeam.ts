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
        const wsId = activeWorkspace.id
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
        if (!cancelled) { setTeamId(data.workspace_id); setLoading(false) }
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
