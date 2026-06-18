"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardSavings } from "@/hooks/useGuardSavings"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"

// ─── Types ────────────────────────────────────────────────────────────────────

interface DeveloperSpend {
  email: string
  sessions: number
  tokens_after: number
  cost_usd: number
  saved_usd: number
  detected_tools: string[]
  mcp_registered: string[]
  hook_registered: string[]
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

function fromUsd(amount: number, currency: Currency): number {
  return amount * CURRENCY_RATES[currency]
}

function toUsd(amount: number, currency: Currency): number {
  return amount / CURRENCY_RATES[currency]
}

interface BudgetOut {
  id: string
  workspace_id: string
  clerk_user_id: string | null
  email?: string | null
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


// ─── Tool coverage ─────────────────────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  "claude-code":    "Claude Code",
  "claude_code":    "Claude Code",
  "claude_chat":    "Claude.ai",
  "claude-chat":    "Claude.ai",
  "claude_desktop": "Claude Desktop",
  "claude-desktop": "Claude Desktop",
  "claude_work":    "Claude Work",
  "claude-work":    "Claude Work",
  "codex":          "Codex",
  "codex_cli":      "Codex CLI",
  "codex_chat":     "Codex Chat",
  "cursor":         "Cursor",
  "windsurf":       "Windsurf",
  "copilot":        "Copilot",
  "gemini":         "Gemini",
  "vscode":         "VS Code",
  "unknown":        "Claude.ai",
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

// ─── Spend controls panel ─────────────────────────────────────────────────────

function SpendControlsPanel({
  settings,
  onSave,
  currency,
  readOnly,
  totalCostUsd,
}: {
  settings: TeamBudgetSettings
  onSave: (s: TeamBudgetSettings) => Promise<void>
  currency: Currency
  readOnly?: boolean
  totalCostUsd: number
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

  function displayAmt(usd: number | null): string {
    if (usd == null) return ""
    return String(Math.round(fromUsd(usd, currency)))
  }

  function parseAmt(val: string): number | null {
    const n = parseFloat(val)
    return isNaN(n) || n < 0 ? null : toUsd(n, currency)
  }

  const teamPct =
    settings.team_monthly_limit_usd && settings.team_monthly_limit_usd > 0
      ? Math.min(((totalCostUsd ?? 0) / settings.team_monthly_limit_usd) * 100, 100)
      : null

  const gridItems: [React.ReactNode, React.ReactNode, React.ReactNode | null][] = [
    [
      "Team monthly budget",
      editing ? (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{sym}</span>
          <input
            type="number" min="0.01" step="0.01"
            value={displayAmt(local.team_monthly_limit_usd)}
            onChange={e => setLocal(p => ({ ...p, team_monthly_limit_usd: parseAmt(e.target.value) }))}
            placeholder="No limit"
            style={{ width: 100, fontSize: 13, border: "1px solid var(--border-2)", borderRadius: 7, padding: "5px 10px" }}
          />
        </div>
      ) : (
        <span style={{ fontSize: 18, fontWeight: 650 }}>
          {settings.team_monthly_limit_usd != null
            ? `${sym}${Math.round(fromUsd(settings.team_monthly_limit_usd, currency)).toLocaleString()} / month`
            : <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 14 }}>No limit set</span>
          }
        </span>
      ),
      teamPct != null && !editing
        ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
            <div style={{ flex: 1, height: 7, borderRadius: 6, background: "var(--surface-3)" }}>
              <div style={{ width: `${teamPct}%`, height: "100%", borderRadius: 6, background: "var(--accent)" }} />
            </div>
            <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{Math.round(teamPct)}%</span>
          </div>
        )
        : null,
    ],
    [
      "Default per-developer limit",
      editing ? (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{sym}</span>
          <input
            type="number" min="0.01" step="0.01"
            value={displayAmt(local.default_per_developer_usd)}
            onChange={e => setLocal(p => ({ ...p, default_per_developer_usd: parseAmt(e.target.value) }))}
            placeholder="No limit"
            style={{ width: 100, fontSize: 13, border: "1px solid var(--border-2)", borderRadius: 7, padding: "5px 10px" }}
          />
        </div>
      ) : (
        <span style={{ fontSize: 18, fontWeight: 650 }}>
          {settings.default_per_developer_usd != null
            ? `${sym}${Math.round(fromUsd(settings.default_per_developer_usd, currency)).toLocaleString()} / month`
            : <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 14 }}>No limit set</span>
          }
        </span>
      ),
      <div key="devlimit-sub" style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 10 }}>
        Applies to new members automatically
      </div>,
    ],
    [
      "Alert threshold",
      editing ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
          <input
            type="range" min="50" max="99" step="5"
            value={local.alert_threshold_pct}
            onChange={e => setLocal(p => ({ ...p, alert_threshold_pct: parseInt(e.target.value) }))}
            style={{ width: 100, accentColor: "var(--accent)" }}
            aria-label="Alert threshold percentage"
            aria-valuenow={local.alert_threshold_pct}
            aria-valuemin={0}
            aria-valuemax={100}
          />
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--warn)" }}>{local.alert_threshold_pct}%</span>
        </div>
      ) : (
        <span style={{ fontSize: 18, fontWeight: 650 }}>
          <span style={{ color: "var(--warn)" }}>{settings.alert_threshold_pct}%</span>
          <span style={{ fontSize: 13, fontWeight: 400, color: "var(--text-muted)" }}> — notify team lead + developer</span>
        </span>
      ),
      null,
    ],
    [
      "Hard cap at 100%",
      editing ? (
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginTop: 4 }}>
          <input
            type="checkbox"
            checked={local.hard_cap_enabled}
            onChange={e => setLocal(p => ({ ...p, hard_cap_enabled: e.target.checked }))}
            style={{ width: 16, height: 16, accentColor: "var(--accent)" }}
          />
          <span style={{ fontSize: 13, color: "var(--text-2)" }}>Block new AI sessions at cap</span>
        </label>
      ) : (
        <span style={{ fontSize: 18, fontWeight: 650 }}>
          {settings.hard_cap_enabled
            ? <span style={{ color: "var(--err)" }}>On — sessions blocked at 100%</span>
            : <span style={{ color: "var(--text-3)", fontWeight: 400, fontSize: 14 }}>Off</span>
          }
        </span>
      ),
      null,
    ],
  ]

  return (
    <div className="card" style={{ borderColor: "var(--warn-bd)", marginBottom: 22, overflow: "hidden" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 22px", borderBottom: "1px solid var(--border)" }}>
        <span style={{ width: 32, height: 32, borderRadius: 9, background: "var(--warn-bg)", color: "var(--warn)", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
        </span>
        <div>
          <div style={{ fontWeight: 650, fontSize: 15 }}>Spend controls</div>
          <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>Set limits now — not after the bill arrives.</div>
        </div>
        {!readOnly && (
          editing ? (
            <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button onClick={reset} className="btn btn-ghost btn-sm">Cancel</button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn btn-primary btn-sm"
                style={{ opacity: saving ? 0.6 : 1 }}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="btn btn-ghost btn-sm"
              style={{ marginLeft: "auto", color: "var(--accent-text)", borderColor: "var(--accent-ring)" }}
            >
              Configure
            </button>
          )
        )}
      </div>

      {/* 2×2 grid body */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
        {gridItems.map(([k, v, extra], i) => (
          <div
            key={i}
            style={{
              padding: "18px 22px",
              borderTop: "1px solid var(--border)",
              borderRight: i % 2 === 0 ? "1px solid var(--border)" : "none",
            }}
          >
            <div style={{ fontSize: 12.5, color: "var(--text-2)", marginBottom: 6 }}>{k}</div>
            {v}
            {extra}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Budget bar ───────────────────────────────────────────────────────────────

function BudgetBar({ used, limit, warnAt = 80 }: { used: number; limit: number | null; warnAt?: number }) {
  if (limit == null || limit === 0) {
    return <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No limit</span>
  }
  const pct = Math.min((used / limit) * 100, 100)
  const over = pct >= warnAt
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, flex: 1 }}>
      <div style={{ flex: 1, height: 7, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 6, background: over ? "var(--warn)" : "var(--accent)" }} />
      </div>
      <span className="mono" style={{ fontSize: 11.5, color: over ? "var(--warn)" : "var(--text-muted)", width: 30, textAlign: "right" }}>
        {Math.round(pct)}%
      </span>
    </div>
  )
}

// ─── Budget inline editor ─────────────────────────────────────────────────────

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
        style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}
        title="Set budget"
        aria-label={`Set budget for ${email}`}
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M11.5 2.5a1.414 1.414 0 0 1 2 2L5 13H3v-2L11.5 2.5z" strokeLinejoin="round" />
        </svg>
      </button>
    )
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>$</span>
      <input
        type="number" min="0" step="10"
        value={value}
        onChange={e => setValue(e.target.value)}
        style={{ width: 56, fontSize: 11, border: "1px solid var(--border-2)", borderRadius: 5, padding: "2px 6px" }}
        autoFocus
        onKeyDown={e => {
          if (e.key === "Enter") handleSave()
          if (e.key === "Escape") setEditing(false)
        }}
      />
      <button
        onClick={handleSave}
        disabled={saving}
        style={{ fontSize: 11, background: "var(--accent)", color: "#fff", border: "none", borderRadius: 5, padding: "2px 7px", cursor: "pointer" }}
      >
        {saving ? "…" : "Save"}
      </button>
      <button
        onClick={() => setEditing(false)}
        style={{ fontSize: 11, background: "none", border: "none", cursor: "pointer", color: "var(--text-3)" }}
      >
        ✕
      </button>
    </div>
  )
}

// ─── Month picker ─────────────────────────────────────────────────────────────

function MonthPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [year, month] = value.split("-").map(Number)
  const label = `${MONTHS[month - 1]} ${year}`
  const now = new Date()
  const isNextYearDisabled = year >= now.getFullYear()

  function select(m: number) {
    const nowY = new Date().getFullYear()
    const nowM = new Date().getMonth() + 1
    if (year > nowY || (year === nowY && m > nowM)) return
    onChange(`${year}-${String(m).padStart(2, "0")}`)
    setOpen(false)
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          fontSize: 12,
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "5px 12px",
          color: "var(--text-3)",
          background: "var(--surface)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {label}
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 4l4 4 4-4" />
        </svg>
      </button>
      {open && (
        <div style={{
          position: "absolute",
          right: 0,
          marginTop: 4,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          boxShadow: "var(--shadow-lg)",
          padding: 12,
          zIndex: 10,
          minWidth: 160,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <button
              onClick={() => onChange(`${year - 1}-${String(month).padStart(2, "0")}`)}
              style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "0 4px" }}
            >
              &lsaquo; {year - 1}
            </button>
            <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text-2)" }}>{year}</span>
            <button
              onClick={() => !isNextYearDisabled && onChange(`${year + 1}-${String(month).padStart(2, "0")}`)}
              disabled={isNextYearDisabled}
              style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: isNextYearDisabled ? "not-allowed" : "pointer", fontSize: 12, padding: "0 4px", opacity: isNextYearDisabled ? 0.4 : 1 }}
            >
              {year + 1} &rsaquo;
            </button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4 }}>
            {MONTHS.map((m, i) => {
              const nowY = new Date().getFullYear()
              const nowM = new Date().getMonth() + 1
              const isFuture = year > nowY || (year === nowY && i + 1 > nowM)
              return (
                <button
                  key={m}
                  onClick={() => select(i + 1)}
                  disabled={isFuture}
                  style={{
                    fontSize: 12,
                    borderRadius: 5,
                    padding: "4px 6px",
                    border: "none",
                    cursor: isFuture ? "not-allowed" : "pointer",
                    background: i + 1 === month ? "var(--accent)" : "none",
                    color: i + 1 === month ? "#fff" : "var(--text-3)",
                    opacity: isFuture ? 0.4 : 1,
                  }}
                >
                  {m}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SpendPage() {
  return <AppShell><SpendContent /></AppShell>
}

function SpendContent() {
  const { getToken } = useAuth()
  const { teamId, loading: teamLoading, error: teamError } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: roleLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const { savings, loading: savingsLoading } = useGuardSavings(teamId)
  const now = new Date()
  const [month, setMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
  )
  const [data, setData] = useState<SpendData | null>(null)
  const [budgets, setBudgets] = useState<Record<string, number | null>>({})
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
      if (!spendRes.ok) {
        if (spendRes.status === 401) throw new Error("Session expired — please refresh")
        if (spendRes.status === 403) throw new Error("You don't have permission to view spend data")
        if (spendRes.status >= 500) throw new Error("Server error — try again later")
        throw new Error(`Failed to load (${spendRes.status})`)
      }
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
          const key = b.email ?? b.clerk_user_id
          if (key) map[key] = b.monthly_limit_usd
        }
        setBudgets(map)
      }
      setLastUpdated(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [getToken, teamId, month])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

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
    setBudgets(prev => ({ ...prev, [email]: limit }))
  }

  const monthLabel = (() => {
    const [y, m] = month.split("-").map(Number)
    return `${MONTHS[m - 1]} ${y}`
  })()

  if (!roleLoading && !canViewSpend) {
    return (
      <GuardShell lastFetched={lastUpdated}>
        <div className="card" style={{ padding: "64px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          You don&apos;t have access to spend data. Contact your admin.
        </div>
      </GuardShell>
    )
  }

  return (
    <GuardShell lastFetched={lastUpdated}>
      {/* Page controls row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, marginBottom: 20 }}>
        <select
          value={currency}
          onChange={e => setCurrency(e.target.value as Currency)}
          style={{
            fontSize: 12,
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "5px 10px",
            color: "var(--text-3)",
            background: "var(--surface)",
            outline: "none",
            cursor: "pointer",
          }}
        >
          <option value="USD">$ USD</option>
          <option value="EUR">€ EUR</option>
          <option value="INR">₹ INR</option>
        </select>
        <MonthPicker value={month} onChange={setMonth} />
      </div>

      {error && (
        <div style={{
          borderRadius: 8,
          background: "var(--err-bg)",
          border: "1px solid var(--err-bd)",
          padding: "10px 16px",
          fontSize: 13,
          color: "var(--err)",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <span style={{ flex: 1 }}>{error}</span>
          <button
            onClick={load}
            style={{ fontSize: 12, fontWeight: 600, background: "var(--err)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 12px", cursor: "pointer", flexShrink: 0 }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Spend controls card */}
      {data === null && loading ? (
        <div className="card" style={{ height: 200, opacity: 0.5, marginBottom: 22 }} />
      ) : (
        <SpendControlsPanel
          settings={teamSettings}
          onSave={saveTeamSettings}
          currency={currency}
          readOnly={!isAdmin}
          totalCostUsd={data?.total_cost_usd ?? 0}
        />
      )}

      {/* 4 stat cards */}
      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card" style={{ height: 80, opacity: 0.5 }} />
          ))}
        </div>
      ) : data ? (
        <>
          <div className="eyebrow" style={{ marginBottom: 11 }}>Spend for {monthLabel}</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
            {[
              [`${CURRENCY_SYMBOLS[currency]}${fromUsd(data.total_cost_usd, currency).toFixed(2)}`, "Est. cost this month", "plain"],
              [formatTokens(data.total_tokens_after), "Tokens used", "ok"],
              [`${CURRENCY_SYMBOLS[currency]}${fromUsd(data.total_cost_usd + data.total_saved_usd, currency).toFixed(0)}`, "Est. cost without Guard", "plain"],
              [`${CURRENCY_SYMBOLS[currency]}${fromUsd(data.total_saved_usd, currency).toFixed(0)}`, "Est. savings", "accent"],
            ].map(([v, k, tone], i) => (
              <div key={i} className="card" style={{ padding: "16px 20px" }}>
                <div style={{
                  fontSize: 24,
                  fontWeight: 700,
                  letterSpacing: "-.02em",
                  color: tone === "ok" ? "var(--ok)" : tone === "accent" ? "var(--accent-text)" : "var(--text)",
                }}>
                  {v}
                </div>
                <div className="eyebrow" style={{ marginTop: 7, fontSize: 9.5 }}>{k}</div>
              </div>
            ))}
          </div>

          {/* Team token savings — RTK + Agent Booster */}
          {!savingsLoading && savings &&
            (savings.team_total.rtk_saved_tokens > 0 || savings.team_total.booster_saved_tokens > 0) && (() => {
            const totalTok = savings.team_total.rtk_saved_tokens + savings.team_total.booster_saved_tokens
            const totalUsd = savings.team_total.rtk_saved_usd + savings.team_total.booster_saved_usd
            return (
              <div className="card" style={{ overflow: "hidden", marginBottom: 24, borderColor: "var(--ok-bd)" }}>
                {/* Header */}
                <div style={{ padding: "16px 22px", borderBottom: "1px solid var(--ok-bd)", background: "var(--ok-bg)", display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ width: 32, height: 32, borderRadius: 9, background: "rgba(22,163,74,0.15)", color: "var(--ok)", display: "grid", placeItems: "center", flexShrink: 0, fontSize: 16 }}>
                    ↓
                  </span>
                  <div>
                    <div style={{ fontWeight: 650, fontSize: 15, color: "var(--text)" }}>Team token savings — all time</div>
                    <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                      Reported by {savings.by_member.length} developer{savings.by_member.length !== 1 ? "s" : ""} via{" "}
                      <span className="mono" style={{ fontSize: 11 }}>conduct guard sync</span>
                    </div>
                  </div>
                  <div style={{ marginLeft: "auto", textAlign: "right" }}>
                    <div style={{ fontSize: 26, fontWeight: 700, color: "var(--ok)", letterSpacing: "-.02em", lineHeight: 1 }}>
                      {CURRENCY_SYMBOLS[currency]}{fromUsd(totalUsd, currency).toFixed(2)}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 3 }}>{formatTokens(totalTok)} tokens saved</div>
                  </div>
                </div>

                {/* 4 KPI cells */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", borderBottom: "1px solid var(--border)" }}>
                  {[
                    { v: formatTokens(savings.team_total.rtk_saved_tokens), k: "RTK tokens saved" },
                    { v: `${CURRENCY_SYMBOLS[currency]}${fromUsd(savings.team_total.rtk_saved_usd, currency).toFixed(2)}`, k: "RTK cost saved" },
                    { v: formatTokens(savings.team_total.booster_saved_tokens), k: "Booster tokens saved" },
                    { v: `${CURRENCY_SYMBOLS[currency]}${fromUsd(savings.team_total.booster_saved_usd, currency).toFixed(2)}`, k: "Booster cost saved" },
                  ].map(({ v, k }, i) => (
                    <div key={i} style={{ padding: "14px 20px", borderRight: i < 3 ? "1px solid var(--border)" : undefined }}>
                      <div style={{ fontSize: 20, fontWeight: 700, color: "var(--ok)" }}>{v}</div>
                      <div className="eyebrow" style={{ marginTop: 5, fontSize: 10, color: "var(--text-3)" }}>{k}</div>
                    </div>
                  ))}
                </div>

                {/* Per-developer breakdown */}
                {savings.by_member.length > 0 && (
                  <>
                    <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 1fr 1fr 1fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                      {["Developer", "RTK tokens", "Booster tokens", "Combined tokens", "Total saved"].map((h, i) => (
                        <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
                      ))}
                    </div>
                    {savings.by_member.map(m => {
                      const mTok = m.rtk_saved_tokens + m.booster_saved_tokens
                      const mUsd = m.rtk_saved_usd + m.booster_saved_usd
                      return (
                        <div key={m.member_email} style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 1fr 1fr 1fr", gap: 14, padding: "11px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                          <div className="mono" style={{ fontSize: 12.5, fontWeight: 550, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.member_email}</div>
                          <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{formatTokens(m.rtk_saved_tokens)}</div>
                          <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{formatTokens(m.booster_saved_tokens)}</div>
                          <div className="mono" style={{ fontSize: 12.5, color: "var(--text-2)", fontWeight: 600 }}>{formatTokens(mTok)}</div>
                          <div className="mono" style={{ fontSize: 12.5, color: "var(--ok)", fontWeight: 600 }}>{CURRENCY_SYMBOLS[currency]}{fromUsd(mUsd, currency).toFixed(2)}</div>
                        </div>
                      )
                    })}
                  </>
                )}
              </div>
            )
          })()}
        </>
      ) : null}

      {/* By developer table */}
      <div className="card" style={{ overflow: "hidden", marginBottom: 24 }}>
        <div style={{ padding: "15px 20px 13px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14.5 }}>
          By developer
        </div>
        {/* Header row */}
        <div style={{ display: "grid", gridTemplateColumns: "1.8fr 0.8fr 0.9fr 0.9fr 0.9fr 1.4fr 1.3fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          {["Developer", "Sessions", "Tokens", "Est. cost", "Saved", "Coverage", "Budget"].map((h, i) => (
            <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: 20 }}>
            {[...Array(3)].map((_, i) => (
              <div key={i} style={{ height: 40, background: "var(--surface-2)", borderRadius: 6, marginBottom: 8, opacity: 0.6 }} />
            ))}
          </div>
        ) : !data || data.by_developer.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No developer spend data for this period.
          </div>
        ) : (
          data.by_developer.map(dev => {
            const budgetLimit = budgets[dev.email] ?? null
            return (
              <div key={dev.email} style={{ display: "grid", gridTemplateColumns: "1.8fr 0.8fr 0.9fr 0.9fr 0.9fr 1.4fr 1.3fr", gap: 14, padding: "12px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 550, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dev.email}</span>
                  <a
                    href={`/guard/activity?dev=${encodeURIComponent(dev.email)}`}
                    style={{ fontSize: 11, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}
                    aria-label={`View activity for ${dev.email}`}
                  >
                    →
                  </a>
                </div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{dev.sessions}</div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{formatTokens(dev.tokens_after)}</div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--text-2)" }}>
                  {CURRENCY_SYMBOLS[currency]}{fromUsd(dev.cost_usd, currency).toFixed(2)}
                </div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--ok)" }}>
                  {CURRENCY_SYMBOLS[currency]}{fromUsd(dev.saved_usd, currency).toFixed(2)}
                </div>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  {(dev.detected_tools ?? []).map(tool => {
                    const covered = (dev.mcp_registered ?? []).includes(tool) || (dev.hook_registered ?? []).includes(tool)
                    return (
                      <span
                        key={tool}
                        aria-label={`${TOOL_LABELS[tool] ?? tool}: ${covered ? "covered" : "not covered"}`}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 3,
                          fontSize: 10.5, fontWeight: 600, padding: "2px 7px",
                          borderRadius: 20,
                          background: covered ? "var(--ok-bg)" : "var(--warn-bg)",
                          color: covered ? "var(--ok)" : "var(--warn)",
                          border: `1px solid ${covered ? "var(--ok-bd)" : "var(--warn-bd)"}`,
                        }}
                      >
                        <span aria-hidden="true">{covered ? "✓" : "!"}</span> {TOOL_LABELS[tool] ?? tool}
                      </span>
                    )
                  })}
                  {(dev.detected_tools ?? []).length === 0 && (
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <BudgetBar used={dev.cost_usd} limit={budgetLimit} warnAt={teamSettings.alert_threshold_pct ?? 80} />
                  {isAdmin && (
                    <BudgetInput email={dev.email} current={budgetLimit} onSave={saveBudget} />
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* By AI tool table */}
      {data && data.by_ai_tool.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{ padding: "15px 20px 13px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14.5 }}>
            By AI tool
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1.6fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
            {["Tool", "Tokens used", "Est. cost", "% of total"].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
            ))}
          </div>
          {data.by_ai_tool.map(t => {
            const pct = data.total_tokens_after > 0
              ? Math.round((t.tokens_after / data.total_tokens_after) * 100)
              : 0
            return (
              <div
                key={t.ai_tool}
                style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1.6fr", gap: 14, padding: "13px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}
              >
                <div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{t.ai_tool}</div>
                <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>{formatTokens(t.tokens_after)}</div>
                <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>
                  {CURRENCY_SYMBOLS[currency]}{fromUsd(t.cost_usd, currency).toFixed(2)}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                  <div style={{ flex: 1, height: 8, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", borderRadius: 6 }} />
                  </div>
                  <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", width: 34, textAlign: "right" }}>{pct}%</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </GuardShell>
  )
}
