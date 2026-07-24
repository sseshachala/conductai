"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

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

export function useGuardSavings(workspaceId: string | null, month?: string): GuardSavingsResult {
  const { authFetch } = useAuthFetch()
  const [savings, setSavings] = useState<GuardSavingsSummary | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const data = await guard.savings.summary(authFetch, workspaceId, month)
      setSavings(data)
      // 404 / not-yet-deployed: leave savings as null — card shows "—" state
    } catch {
      // non-fatal — keep null state
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId, month])

  useEffect(() => {
    setSavings(null)
    load()
  }, [load])

  return { savings, loading }
}
