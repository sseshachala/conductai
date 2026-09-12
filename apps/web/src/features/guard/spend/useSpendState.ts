// Shared state hook for the Spend Configure (/theguard/spend) and
// Spend at a glance (/theguard/spend/glance) pages.
//
// Both surfaces need currency + month + spend data + budgets + team
// settings + savings. Rather than duplicate the state / fetch logic
// on each page, own it here once. Each page consumes what it needs.
//
// Two pages both mount this hook independently — no shared context.
// Cost: each page fires its own fetch on mount. Benefit: no plumbing,
// no stale-cache bugs, no cross-page coupling.
"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useGuardSavings } from "@/hooks/useGuardSavings"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { guard } from "@/lib/api"
import {
  formatMonthLabel,
  type Currency,
  type SpendData,
  type TeamBudgetSettings,
} from "./shared"

export interface UseSpendState {
  // Team + role
  teamId: string | null
  teamLoading: boolean
  teamError: string | null
  isAdmin: boolean
  canViewSpend: boolean
  roleLoading: boolean

  // Currency + month
  currency: Currency
  setCurrency: (c: Currency) => void
  month: string
  setMonth: (m: string) => void
  monthLabel: string

  // Spend data
  data: SpendData | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null

  // Budgets
  teamSettings: TeamBudgetSettings
  budgets: Record<string, number | null>
  hardLimits: Record<string, number | null>

  // Savings
  savings: ReturnType<typeof useGuardSavings>["savings"]
  savingsLoading: boolean

  // Actions
  load: () => Promise<void>
  saveTeamSettings: (s: TeamBudgetSettings) => Promise<void>
  saveBudget: (email: string, limit: number, hard: number | null) => Promise<void>
}

export function useSpendState(): UseSpendState {
  const { authFetch } = useAuthFetch()
  const { teamId, loading: teamLoading, error: teamError } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: roleLoading } = useGuardRole(
    teamId,
    activeWorkspace?.id ?? null,
  )

  const now = new Date()
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  )
  const { savings, loading: savingsLoading } = useGuardSavings(teamId, month)
  const [data, setData] = useState<SpendData | null>(null)
  const [budgets, setBudgets] = useState<Record<string, number | null>>({})
  const [hardLimits, setHardLimits] = useState<Record<string, number | null>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currency, setCurrency] = useState<Currency>("USD")
  const [teamSettings, setTeamSettings] = useState<TeamBudgetSettings>({
    team_monthly_limit_usd: null,
    alert_threshold_pct: 80,
    hard_cap_enabled: false,
    default_per_developer_usd: null,
  })
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const isAdmin = permissions.canEditBudgets
  const canViewSpend = permissions.canViewAllSpend || permissions.canViewOwnSpend

  const load = useCallback(async () => {
    if (!teamId) return
    setLoading(true)
    setError(null)

    try {
      const [spendData, budgetList] = await Promise.all([
        guard.spend.get(authFetch, { workspace_id: teamId, month }),
        guard.spend.budgets.get(authFetch, { workspace_id: teamId }),
      ])
      const spendJson: SpendData = spendData
      setData(spendJson)

      if (Array.isArray(budgetList)) {
        const teamBudget = budgetList.find((b: any) => b.clerk_user_id === null)
        if (teamBudget) {
          setTeamSettings({
            team_monthly_limit_usd: teamBudget.monthly_limit_usd,
            alert_threshold_pct: teamBudget.alert_threshold_pct,
            hard_cap_enabled: teamBudget.hard_limit_usd != null,
            default_per_developer_usd: teamBudget.default_per_developer_usd,
          })
        }
        const map: Record<string, number | null> = {}
        const hardMap: Record<string, number | null> = {}
        for (const b of budgetList as any[]) {
          const key = b.email ?? b.clerk_user_id
          if (key) {
            map[key] = b.monthly_limit_usd
            hardMap[key] = b.hard_limit_usd
          }
        }
        setBudgets(map)
        setHardLimits(hardMap)
      }
      setLastUpdated(new Date())
    } catch (err: any) {
      const msg = err?.message ?? String(err)
      if (msg.includes("401")) setError("Session expired — please refresh")
      else if (msg.includes("403")) setError("You don't have permission to view spend data")
      else if (msg.includes("5")) setError("Server error — try again later")
      else setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [authFetch, teamId, month])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    if (teamError) setError(teamError)
  }, [teamError])

  const saveTeamSettings = useCallback(async (s: TeamBudgetSettings) => {
    if (!teamId) return
    const res = await guard.spend.budgets.set(authFetch, {
      workspace_id: teamId,
      clerk_user_id: null,
      monthly_limit_usd: s.team_monthly_limit_usd ?? 0,
      alert_threshold_pct: s.alert_threshold_pct,
      hard_limit_usd: s.hard_cap_enabled ? (s.team_monthly_limit_usd ?? 0) : null,
      default_per_developer_usd: s.default_per_developer_usd,
    })
    if (!res.ok) throw new Error("Failed to save spend controls")
    setTeamSettings(s)
  }, [authFetch, teamId])

  const saveBudget = useCallback(async (email: string, limit: number, hard: number | null) => {
    if (!teamId) return
    const res = await guard.spend.budgets.set(authFetch, {
      workspace_id: teamId,
      email,
      monthly_limit_usd: limit,
      hard_limit_usd: hard,
    })
    if (!res.ok) throw new Error("Failed to save budget")
    setBudgets(prev => ({ ...prev, [email]: limit }))
    setHardLimits(prev => ({ ...prev, [email]: hard }))
  }, [authFetch, teamId])

  return {
    teamId,
    teamLoading,
    teamError,
    isAdmin,
    canViewSpend,
    roleLoading,
    currency,
    setCurrency,
    month,
    setMonth,
    monthLabel: formatMonthLabel(month),
    data,
    loading,
    error,
    lastUpdated,
    teamSettings,
    budgets,
    hardLimits,
    savings,
    savingsLoading,
    load,
    saveTeamSettings,
    saveBudget,
  }
}
