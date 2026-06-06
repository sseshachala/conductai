"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"

interface SavingsTeamTotal {
  rtk_saved_tokens: number
  rtk_saved_usd: number
  booster_saved_tokens: number
  booster_saved_usd: number
}

interface SavingsByMember {
  member_email: string
  rtk_saved_tokens: number
  rtk_saved_usd: number
  booster_saved_tokens: number
  booster_saved_usd: number
  recorded_at: string
}

export interface GuardSavingsSummary {
  team_total: SavingsTeamTotal
  by_member: SavingsByMember[]
  tools_installed: string[]
}

interface GuardSavingsResult {
  savings: GuardSavingsSummary | null
  loading: boolean
}

export function useGuardSavings(workspaceId: string | null): GuardSavingsResult {
  const { getToken } = useAuth()
  const [savings, setSavings] = useState<GuardSavingsSummary | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const token = await getToken()
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await fetch(
        `${base}/guard/savings/summary?workspace_id=${workspaceId}`,
        { headers },
      )
      if (res.ok) {
        const data: GuardSavingsSummary = await res.json()
        setSavings(data)
      }
      // 404 / not-yet-deployed: leave savings as null — card shows "—" state
    } catch {
      // non-fatal — keep null state
    } finally {
      setLoading(false)
    }
  }, [getToken, workspaceId])

  useEffect(() => {
    setSavings(null)
    load()
  }, [load])

  return { savings, loading }
}
