"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

export interface RoutingRow {
  provider: string
  model_id: string
  reason: string
}

// keyed by category (or "" for fallback) → preference → row
export type RoutingTable = Record<string, Record<string, RoutingRow>>

let _cache: RoutingTable | null = null

export function useRoutingTable(): { table: RoutingTable | null; loading: boolean } {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const { activeWorkspace } = useWorkspace()

  const [table, setTable] = useState<RoutingTable | null>(_cache)
  const [loading, setLoading] = useState(_cache === null)

  useEffect(() => {
    if (_cache) return
    if (!isLoaded || !isSignedIn || !activeWorkspace?.id) return
    let cancelled = false

    async function fetch_() {
      try {
        const token = await getToken()
        if (!token) { if (!cancelled) setLoading(false); return }
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/meta/routing-table`,
          { headers: { Authorization: `Bearer ${token}`, "X-Workspace-Id": activeWorkspace!.id } }
        )
        if (res.ok) {
          const data: RoutingTable = await res.json()
          _cache = data
          if (!cancelled) setTable(data)
        }
      } catch {
        // fall back to hardcoded client-side policy
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetch_()
    return () => { cancelled = true }
  }, [isLoaded, isSignedIn, activeWorkspace?.id, getToken])

  return { table, loading }
}
