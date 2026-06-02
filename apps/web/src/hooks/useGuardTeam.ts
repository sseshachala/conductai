"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface GuardTeamResult {
  teamId: string | null
  loading: boolean
  error: string | null
}

export function useGuardTeam(): GuardTeamResult {
  const { getToken } = useAuth()
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
        const token = await getToken()
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        const base = process.env.NEXT_PUBLIC_API_URL ?? ""
        const res = await fetch(`${base}/guard/teams/me?workspace_id=${activeWorkspace.id}`, { headers })
        if (!res.ok) {
          if (!cancelled) { setLoading(false); setError(`Guard not installed (${res.status})`) }
          return
        }
        const data = await res.json()
        if (!cancelled) { setTeamId(data.id); setLoading(false) }
      } catch (e) {
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
