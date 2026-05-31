"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface SpendSummary {
  total_cost_usd: number
  tokens_used: number
  tokens_saved: number
  reduction_pct: number
  cost_without_optimisation: number
  money_saved: number
}

interface DeveloperSpend {
  email: string
  sessions: number
  tokens_used: number
  cost_usd: number
  saved_usd: number
  budget_used_usd: number
  budget_limit_usd: number | null
}

interface AiToolBreakdown {
  tool: string
  tokens_used: number
  cost_usd: number
  pct_of_total: number
}

interface SpendData {
  summary: SpendSummary
  by_developer: DeveloperSpend[]
  by_ai_tool: AiToolBreakdown[]
}

interface Budget {
  email: string
  monthly_limit_usd: number
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

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

function MonthPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  // value is "YYYY-MM"
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
  const { getToken } = useAuth()
  const now = new Date()
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
  )
  const [data, setData] = useState<SpendData | null>(null)
  const [budgets, setBudgets] = useState<Record<string, number | null>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedDev, setExpandedDev] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const token = await getToken()
    const teamId = getCookie("delegator_project_id") ?? ""
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`

    try {
      const [spendRes, budgetRes] = await Promise.all([
        fetch(`${base}/guard/spend?team_id=${teamId}&month=${month}`, { headers }),
        fetch(`${base}/guard/spend/budgets?team_id=${teamId}`, { headers }),
      ])
      if (!spendRes.ok) throw new Error("Failed to load spend data")
      const spendJson: SpendData = await spendRes.json()
      setData(spendJson)

      if (budgetRes.ok) {
        const budgetList: Budget[] = await budgetRes.json()
        const map: Record<string, number | null> = {}
        for (const b of budgetList) map[b.email] = b.monthly_limit_usd
        setBudgets(map)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [getToken, month])

  useEffect(() => { load() }, [load])

  async function saveBudget(email: string, limit: number) {
    const token = await getToken()
    const teamId = getCookie("delegator_project_id") ?? ""
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
    const res = await fetch(`${base}/guard/spend/budgets`, {
      method: "POST",
      headers,
      body: JSON.stringify({ team_id: teamId, email, monthly_limit_usd: limit }),
    })
    if (!res.ok) throw new Error("Failed to save budget")
    setBudgets((prev) => ({ ...prev, [email]: limit }))
  }

  const s = data?.summary

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Guard &middot; Spend</h1>
            <p className="text-sm text-stone-500 mt-1">Token usage and cost tracking for your team.</p>
          </div>
          <MonthPicker value={month} onChange={setMonth} />
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {/* Summary cards */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-stone-100 rounded-xl h-24" />
            ))}
          </div>
        ) : s ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Total cost this month"
              value={`$${s.total_cost_usd.toFixed(2)}`}
              accent="text-stone-900"
            />
            <StatCard
              label="Tokens saved"
              value={formatTokens(s.tokens_saved)}
              sub={`${Math.round(s.reduction_pct)}% reduction`}
              accent="text-green-700"
            />
            <StatCard
              label="Cost without optimisation"
              value={`$${s.cost_without_optimisation.toFixed(0)}`}
              accent="text-stone-500"
            />
            <StatCard
              label="Money saved"
              value={`$${s.money_saved.toFixed(0)}`}
              accent="text-indigo-700"
            />
          </div>
        ) : null}

        {/* By developer */}
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
                    const budgetLimit = budgets[dev.email] ?? dev.budget_limit_usd
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
                            {formatTokens(dev.tokens_used)}
                          </td>
                          <td className="px-4 py-3 text-right text-stone-700 font-mono text-xs font-medium">
                            ${dev.cost_usd.toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-right text-green-700 font-mono text-xs">
                            ${dev.saved_usd.toFixed(2)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-stone-500 font-mono whitespace-nowrap">
                                ${dev.budget_used_usd.toFixed(0)}/{budgetLimit != null ? `$${budgetLimit}` : "—"}
                              </span>
                              <BudgetBar used={dev.budget_used_usd} limit={budgetLimit} />
                            </div>
                          </td>
                          <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                            <BudgetInput
                              email={dev.email}
                              current={budgetLimit ?? null}
                              onSave={saveBudget}
                            />
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr key={`${dev.email}-expanded`} className="bg-stone-50 border-b border-stone-100">
                            <td colSpan={7} className="px-6 py-4">
                              <p className="text-xs text-stone-500">
                                Session breakdown for <span className="font-medium text-stone-700">{dev.email}</span> is available in the Audit Trail.
                              </p>
                              <a
                                href={`/guard/audit?developer=${encodeURIComponent(dev.email)}`}
                                className="mt-1 inline-block text-xs text-indigo-600 hover:underline"
                              >
                                View audit trail for this developer &rarr;
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

        {/* By AI tool */}
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
                  {data.by_ai_tool.map((t) => (
                    <tr key={t.tool} className="border-b border-stone-100 last:border-0">
                      <td className="px-4 py-3 font-medium text-stone-800">{t.tool}</td>
                      <td className="px-4 py-3 text-right text-stone-600 font-mono text-xs">
                        {formatTokens(t.tokens_used)}
                      </td>
                      <td className="px-4 py-3 text-right text-stone-700 font-mono text-xs font-medium">
                        ${t.cost_usd.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-indigo-500 rounded-full"
                              style={{ width: `${Math.min(t.pct_of_total, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-stone-500 w-8 text-right">
                            {Math.round(t.pct_of_total)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}
