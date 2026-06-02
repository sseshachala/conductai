"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"

interface DeveloperSpend {
  email: string
  sessions: number
  tokens_after: number
  cost_usd: number
  saved_usd: number
}

interface AiToolBreakdown {
  ai_tool: string
  tokens_after: number
  cost_usd: number
}

interface SpendData {
  team_id: string
  period: string
  total_tokens_before: number
  total_tokens_after: number
  total_saved_pct: number
  total_cost_usd: number
  total_saved_usd: number
  by_developer: DeveloperSpend[]
  by_ai_tool: AiToolBreakdown[]
}

type Currency = "USD" | "EUR" | "INR"

const CURRENCY_SYMBOLS: Record<Currency, string> = { USD: "$", EUR: "€", INR: "₹" }
const CURRENCY_RATES: Record<Currency, number> = { USD: 1, EUR: 0.92, INR: 83.5 }

function toUsd(amount: number, currency: Currency): number {
  return amount / CURRENCY_RATES[currency]
}

function fromUsd(amount: number, currency: Currency): number {
  return amount * CURRENCY_RATES[currency]
}

interface BudgetOut {
  id: string
  workspace_id: string
  clerk_user_id: string | null
  monthly_limit_usd: number
  alert_threshold_pct: number
  hard_limit_usd: number | null
  default_per_developer_usd: number | null
  current_month_cost_usd: number
}

interface TeamBudgetSettings {
  team_monthly_limit_usd: number | null
  alert_threshold_pct: number
  hard_cap_enabled: boolean
  default_per_developer_usd: number | null
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string | number
  sub?: string
  accent?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-5 py-4 flex flex-col gap-1">
      <div className={`text-2xl font-bold ${accent ?? "text-stone-900"}`}>{value}</div>
      <div className="text-xs font-medium text-stone-500 uppercase tracking-wide">{label}</div>
      {sub && <div className="text-xs text-stone-400">{sub}</div>}
    </div>
  )
}

function BudgetBar({ used, limit }: { used: number; limit: number | null }) {
  if (limit == null || limit === 0) {
    return <span className="text-xs text-stone-400">No limit</span>
  }
  const pct = Math.min((used / limit) * 100, 100)
  const fillColour =
    pct >= 95 ? "bg-red-500" : pct >= 80 ? "bg-amber-400" : "bg-indigo-500"
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 bg-stone-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${fillColour}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-stone-500 whitespace-nowrap">{Math.round(pct)}%</span>
    </div>
  )
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function BudgetInput({
  email,
  current,
  onSave,
}: {
  email: string
  current: number | null
  onSave: (email: string, limit: number) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(current != null ? String(current) : "")
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    const parsed = parseFloat(value)
    if (isNaN(parsed) || parsed < 0) return
    setSaving(true)
    try {
      await onSave(email, parsed)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="text-stone-400 hover:text-indigo-600 transition-colors"
        title="Set budget"
        aria-label={`Set budget for ${email}`}
      >
        <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M11.5 2.5a1.414 1.414 0 0 1 2 2L5 13H3v-2L11.5 2.5z" strokeLinejoin="round" />
        </svg>
      </button>
    )
  }

  return (
    <div className="flex items-center gap-1">
      <span className="text-xs text-stone-400">$</span>
      <input
        type="number"
        min="0"
        step="10"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-16 text-xs border border-stone-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === "Enter") handleSave()
          if (e.key === "Escape") setEditing(false)
        }}
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="text-xs text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded px-1.5 py-0.5 transition-colors"
      >
        {saving ? "…" : "Save"}
      </button>
      <button
        onClick={() => setEditing(false)}
        className="text-xs text-stone-500 hover:text-stone-700"
      >
        Cancel
      </button>
    </div>
  )
}

function SpendControlsPanel({
  settings,
  onSave,
  currency,
  readOnly,
}: {
  settings: TeamBudgetSettings
  onSave: (s: TeamBudgetSettings) => Promise<void>
  currency: Currency
  readOnly?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [local, setLocal] = useState(settings)
  const [saving, setSaving] = useState(false)
  const sym = CURRENCY_SYMBOLS[currency]

  useEffect(() => { setLocal(settings) }, [settings])

  function reset() { setLocal(settings); setEditing(false) }

  async function handleSave() {
    setSaving(true)
    try { await onSave(local); setEditing(false) } finally { setSaving(false) }
  }

  const teamPct =
    settings.team_monthly_limit_usd && settings.team_monthly_limit_usd > 0
      ? Math.min((0 / settings.team_monthly_limit_usd) * 100, 100)
      : null

  function displayAmt(usd: number | null): string {
    if (usd == null) return ""
    return String(Math.round(fromUsd(usd, currency)))
  }

  function parseAmt(val: string): number | null {
    const n = parseFloat(val)
    return isNaN(n) || n < 0 ? null : toUsd(n, currency)
  }

  return (
    <div className="bg-white rounded-xl border border-amber-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <span className="text-base" aria-hidden>⚡</span>
          <div>
            <h2 className="text-sm font-semibold text-stone-900">Spend Controls</h2>
            <p className="text-xs text-stone-500">Set limits now — not after the bill arrives.</p>
          </div>
        </div>
        {!readOnly && (
          !editing ? (
            <button
              onClick={() => setEditing(true)}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded-lg px-3 py-1.5 transition-colors"
            >
              Configure
            </button>
          ) : (
            <div className="flex gap-2">
              <button onClick={reset} className="text-xs text-stone-500 hover:text-stone-700 border border-stone-200 rounded-lg px-3 py-1.5 transition-colors">
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          )
        )}
      </div>

      <div className="px-5 py-4 grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-stone-700">Team monthly budget</label>
          {editing ? (
            <div className="flex items-center gap-1.5">
              <span className="text-sm text-stone-400">{sym}</span>
              <input
                type="number" min="0" step="100"
                value={displayAmt(local.team_monthly_limit_usd)}
                onChange={e => setLocal(p => ({ ...p, team_monthly_limit_usd: parseAmt(e.target.value) }))}
                placeholder="No limit"
                className="w-32 text-sm border border-stone-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          ) : (
            <p className="text-sm font-semibold text-stone-900">
              {settings.team_monthly_limit_usd != null
                ? `${sym}${Math.round(fromUsd(settings.team_monthly_limit_usd, currency)).toLocaleString()} / month`
                : <span className="text-stone-400 font-normal">No limit set</span>}
            </p>
          )}
          {teamPct != null && !editing && (
            <BudgetBar used={0} limit={settings.team_monthly_limit_usd} />
          )}
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-stone-700">Default per-developer limit</label>
          {editing ? (
            <div className="flex items-center gap-1.5">
              <span className="text-sm text-stone-400">{sym}</span>
              <input
                type="number" min="0" step="50"
                value={displayAmt(local.default_per_developer_usd)}
                onChange={e => setLocal(p => ({ ...p, default_per_developer_usd: parseAmt(e.target.value) }))}
                placeholder="No limit"
                className="w-32 text-sm border border-stone-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          ) : (
            <p className="text-sm font-semibold text-stone-900">
              {settings.default_per_developer_usd != null
                ? `${sym}${Math.round(fromUsd(settings.default_per_developer_usd, currency)).toLocaleString()} / month`
                : <span className="text-stone-400 font-normal">No limit set</span>}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-stone-700">Alert threshold</label>
          {editing ? (
            <div className="flex items-center gap-2">
              <input
                type="range" min="50" max="99" step="5"
                value={local.alert_threshold_pct}
                onChange={e => setLocal(p => ({ ...p, alert_threshold_pct: parseInt(e.target.value) }))}
                className="w-32 accent-indigo-600"
              />
              <span className="text-sm font-medium text-stone-700 w-10">{local.alert_threshold_pct}%</span>
            </div>
          ) : (
            <p className="text-sm font-semibold text-stone-900">
              Alert at <span className="text-amber-600">{settings.alert_threshold_pct}%</span>
              <span className="text-xs font-normal text-stone-400 ml-1">— notify team lead + developer</span>
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-stone-700">Hard cap at 100%</label>
          {editing ? (
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={local.hard_cap_enabled}
                onChange={e => setLocal(p => ({ ...p, hard_cap_enabled: e.target.checked }))}
                className="w-4 h-4 accent-indigo-600"
              />
              <span className="text-sm text-stone-700">Block new AI sessions when budget is exhausted</span>
            </label>
          ) : (
            <p className="text-sm font-semibold text-stone-900">
              {settings.hard_cap_enabled
                ? <span className="text-red-600">Hard cap on — sessions blocked at 100%</span>
                : <span className="text-stone-400 font-normal">Off — spend can exceed limit</span>}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

function MonthPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [year, month] = value.split("-").map(Number)
  const label = `${MONTHS[month - 1]} ${year}`

  function select(m: number) {
    onChange(`${year}-${String(m).padStart(2, "0")}`)
    setOpen(false)
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs border border-stone-200 rounded-lg px-3 py-1.5 text-stone-600 hover:bg-stone-50 transition-colors flex items-center gap-1.5"
      >
        {label}
        <svg className="w-3 h-3 text-stone-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 4l4 4 4-4" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 bg-white border border-stone-200 rounded-xl shadow-lg p-3 z-10 min-w-[160px]">
          <div className="flex items-center justify-between mb-2">
            <button
              onClick={() => onChange(`${year - 1}-${String(month).padStart(2, "0")}`)}
              className="text-stone-400 hover:text-stone-600 text-xs px-1"
            >
              &lsaquo; {year - 1}
            </button>
            <span className="text-xs font-medium text-stone-700">{year}</span>
            <button
              onClick={() => onChange(`${year + 1}-${String(month).padStart(2, "0")}`)}
              className="text-stone-400 hover:text-stone-600 text-xs px-1"
            >
              {year + 1} &rsaquo;
            </button>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {MONTHS.map((m, i) => (
              <button
                key={m}
                onClick={() => select(i + 1)}
                className={`text-xs rounded px-1.5 py-1 transition-colors ${
                  i + 1 === month
                    ? "bg-indigo-600 text-white"
                    : "text-stone-600 hover:bg-stone-100"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function SpendPage() {
  return <AppShell><SpendContent /></AppShell>
}

function SpendContent() {
  const { getToken } = useAuth()
  const { teamId, loading: teamLoading, error: teamError } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const now = new Date()
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
  )
  const [data, setData] = useState<SpendData | null>(null)
  const [budgets, setBudgets] = useState<Record<string, number | null>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedDev, setExpandedDev] = useState<string | null>(null)
  const [currency, setCurrency] = useState<Currency>("USD")
  const [teamSettings, setTeamSettings] = useState<TeamBudgetSettings>({
    team_monthly_limit_usd: null,
    alert_threshold_pct: 80,
    hard_cap_enabled: false,
    default_per_developer_usd: null,
  })

  const isAdmin = permissions.canEditBudgets
  const canViewSpend = permissions.canViewAllSpend || permissions.canViewOwnSpend

  const load = useCallback(async () => {
    if (!teamId) return
    setLoading(true)
    setError(null)
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }

    try {
      const [spendRes, budgetRes] = await Promise.all([
        fetch(`${base}/guard/spend?workspace_id=${teamId}&month=${month}`, { headers }),
        fetch(`${base}/guard/spend/budgets?workspace_id=${teamId}`, { headers }),
      ])
      if (!spendRes.ok) throw new Error("Failed to load spend data")
      const spendJson: SpendData = await spendRes.json()
      setData(spendJson)

      if (budgetRes.ok) {
        const budgetList: BudgetOut[] = await budgetRes.json()
        const teamBudget = budgetList.find(b => b.clerk_user_id === null)
        if (teamBudget) {
          setTeamSettings({
            team_monthly_limit_usd: teamBudget.monthly_limit_usd,
            alert_threshold_pct: teamBudget.alert_threshold_pct,
            hard_cap_enabled: teamBudget.hard_limit_usd != null,
            default_per_developer_usd: teamBudget.default_per_developer_usd,
          })
        }
        const map: Record<string, number | null> = {}
        for (const b of budgetList) {
          if (b.clerk_user_id != null && b.clerk_user_id) {
            map[b.clerk_user_id] = b.monthly_limit_usd
          }
        }
        setBudgets(map)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [getToken, teamId, month])

  useEffect(() => { load() }, [load])

  // Propagate hook-level error (Guard not installed) to page error state
  useEffect(() => {
    if (teamError) setError(teamError)
  }, [teamError])

  async function saveTeamSettings(s: TeamBudgetSettings) {
    if (!teamId) return
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
    const res = await fetch(`${base}/guard/spend/budgets`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        workspace_id: teamId,
        clerk_user_id: null,
        monthly_limit_usd: s.team_monthly_limit_usd ?? 0,
        alert_threshold_pct: s.alert_threshold_pct,
        hard_limit_usd: s.hard_cap_enabled ? (s.team_monthly_limit_usd ?? 0) : null,
        default_per_developer_usd: s.default_per_developer_usd,
      }),
    })
    if (!res.ok) throw new Error("Failed to save spend controls")
    setTeamSettings(s)
  }

  async function saveBudget(email: string, limit: number) {
    if (!teamId) return
    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
    const res = await fetch(`${base}/guard/spend/budgets`, {
      method: "POST",
      headers,
      body: JSON.stringify({ workspace_id: teamId, email, monthly_limit_usd: limit }),
    })
    if (!res.ok) throw new Error("Failed to save budget")
    setBudgets((prev) => ({ ...prev, [email]: limit }))
  }

  const monthLabel = (() => {
    const [y, m] = month.split("-").map(Number)
    return `${MONTHS[m - 1]} ${y}`
  })()

  if (!canViewSpend) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="rounded-xl border border-stone-200 bg-white px-6 py-16 text-center text-sm text-stone-400">
          You don&apos;t have access to spend data. Contact your admin.
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900 mb-1">Spend</h1>
            <p className="text-sm text-stone-500">Token usage and cost tracking for your team.</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={currency}
              onChange={e => setCurrency(e.target.value as Currency)}
              className="text-xs border border-stone-200 rounded-lg px-2.5 py-1.5 text-stone-600 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="USD">$ USD</option>
              <option value="EUR">€ EUR</option>
              <option value="INR">₹ INR</option>
            </select>
            <MonthPicker value={month} onChange={setMonth} />
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        <SpendControlsPanel settings={teamSettings} onSave={saveTeamSettings} currency={currency} readOnly={!isAdmin} />

        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-stone-100 rounded-xl h-24" />
            ))}
          </div>
        ) : data ? (
          <>
            <p className="text-xs font-medium text-stone-500 uppercase tracking-wide -mb-4">
              Spend for {monthLabel}
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="Total cost this month"
                value={`${CURRENCY_SYMBOLS[currency]}${fromUsd(data.total_cost_usd, currency).toFixed(2)}`}
                accent="text-stone-900"
              />
              <StatCard
                label="Tokens saved"
                value={formatTokens(data.total_tokens_before - data.total_tokens_after)}
                sub={`${Math.round(data.total_saved_pct)}% reduction`}
                accent="text-green-700"
              />
              <StatCard
                label="Cost without optimisation"
                value={`${CURRENCY_SYMBOLS[currency]}${fromUsd(data.total_cost_usd + data.total_saved_usd, currency).toFixed(0)}`}
                accent="text-stone-500"
              />
              <StatCard
                label="Money saved"
                value={`${CURRENCY_SYMBOLS[currency]}${fromUsd(data.total_saved_usd, currency).toFixed(0)}`}
                accent="text-indigo-700"
              />
            </div>
          </>
        ) : null}

        <div>
          <h2 className="text-sm font-semibold text-stone-700 mb-3">By Developer</h2>
          {loading ? (
            <div className="space-y-2 animate-pulse">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="bg-stone-100 rounded-xl h-14" />
              ))}
            </div>
          ) : !data || data.by_developer.length === 0 ? (
            <div className="rounded-xl border border-stone-200 bg-white px-6 py-10 text-center text-sm text-stone-400">
              No developer spend data for this period.
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide">
                    <th className="px-4 py-3 text-left font-medium">Developer</th>
                    <th className="px-4 py-3 text-right font-medium">Sessions</th>
                    <th className="px-4 py-3 text-right font-medium">Tokens used</th>
                    <th className="px-4 py-3 text-right font-medium">Cost</th>
                    <th className="px-4 py-3 text-right font-medium">Saved</th>
                    <th className="px-4 py-3 text-left font-medium">Budget</th>
                    <th className="px-4 py-3 text-left font-medium w-6" />
                  </tr>
                </thead>
                <tbody>
                  {data.by_developer.map((dev) => {
                    const budgetLimit = budgets[dev.email] ?? null
                    const isExpanded = expandedDev === dev.email
                    return (
                      <>
                        <tr
                          key={dev.email}
                          className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors cursor-pointer"
                          onClick={() => setExpandedDev(isExpanded ? null : dev.email)}
                        >
                          <td className="px-4 py-3 font-medium text-stone-800">{dev.email}</td>
                          <td className="px-4 py-3 text-right text-stone-600">{dev.sessions}</td>
                          <td className="px-4 py-3 text-right text-stone-600 font-mono text-xs">
                            {formatTokens(dev.tokens_after)}
                          </td>
                          <td className="px-4 py-3 text-right text-stone-700 font-mono text-xs font-medium">
                            {CURRENCY_SYMBOLS[currency]}{fromUsd(dev.cost_usd, currency).toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-right text-green-700 font-mono text-xs">
                            {CURRENCY_SYMBOLS[currency]}{fromUsd(dev.saved_usd, currency).toFixed(2)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-stone-500 font-mono whitespace-nowrap">
                                ${dev.cost_usd.toFixed(0)}/{budgetLimit != null ? `$${budgetLimit}` : "—"}
                              </span>
                              <BudgetBar used={dev.cost_usd} limit={budgetLimit} />
                            </div>
                          </td>
                          {isAdmin && (
                            <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                              <BudgetInput
                                email={dev.email}
                                current={budgetLimit}
                                onSave={saveBudget}
                              />
                            </td>
                          )}
                          {!isAdmin && <td className="px-4 py-3" />}
                        </tr>
                        {isExpanded && (
                          <tr key={`${dev.email}-expanded`} className="bg-stone-50 border-b border-stone-100">
                            <td colSpan={7} className="px-6 py-4">
                              <p className="text-xs text-stone-500">
                                Session breakdown for <span className="font-medium text-stone-700">{dev.email}</span> is available in the Activity log.
                              </p>
                              <a
                                href={`/guard/activity?developer=${encodeURIComponent(dev.email)}`}
                                className="mt-1 inline-block text-xs text-indigo-600 hover:underline"
                              >
                                View activity log for this developer &rarr;
                              </a>
                            </td>
                          </tr>
                        )}
                      </>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {data && data.by_ai_tool.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-stone-700 mb-3">By AI Tool</h2>
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-100 text-xs text-stone-400 uppercase tracking-wide">
                    <th className="px-4 py-3 text-left font-medium">Tool</th>
                    <th className="px-4 py-3 text-right font-medium">Tokens used</th>
                    <th className="px-4 py-3 text-right font-medium">Cost</th>
                    <th className="px-4 py-3 text-right font-medium">% of total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_ai_tool.map((t) => {
                    const pct = data.total_tokens_after > 0
                      ? (t.tokens_after / data.total_tokens_after) * 100
                      : 0
                    return (
                      <tr key={t.ai_tool} className="border-b border-stone-100 last:border-0">
                        <td className="px-4 py-3 font-medium text-stone-800">{t.ai_tool}</td>
                        <td className="px-4 py-3 text-right text-stone-600 font-mono text-xs">
                          {formatTokens(t.tokens_after)}
                        </td>
                        <td className="px-4 py-3 text-right text-stone-700 font-mono text-xs font-medium">
                          {CURRENCY_SYMBOLS[currency]}{fromUsd(t.cost_usd, currency).toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-indigo-500 rounded-full"
                                style={{ width: `${Math.min(pct, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-stone-500 w-8 text-right">
                              {Math.round(pct)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
  )
}
