// Shared Spend components used by both /theguard/spend (Configure) and
// /theguard/spend/glance (Spend at a glance).
//
// Kept small and dumb — each component takes props, renders UI, calls
// callbacks. State + fetching live in useSpendState so both pages
// consume the same source of truth without duplicating logic.
"use client"

import { useEffect, useState } from "react"
import {
  CURRENCY_SYMBOLS,
  MONTHS,
  fromUsd,
  toUsd,
  type Currency,
  type TeamBudgetSettings,
} from "./shared"

// ─── Spend controls panel (Configure tab body) ───────────────────────────

export function SpendControlsPanel({
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

// ─── Budget bar ─────────────────────────────────────────────────────────

export function BudgetBar({ used, limit, warnAt = 80 }: { used: number; limit: number | null; warnAt?: number }) {
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

// ─── Budget inline editor ───────────────────────────────────────────────

export function BudgetInput({
  email,
  current,
  currentHard,
  onSave,
}: {
  email: string
  current: number | null
  currentHard: number | null
  onSave: (email: string, limit: number, hard: number | null) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(current != null ? String(current) : "")
  const [hardValue, setHardValue] = useState(currentHard != null ? String(currentHard) : "")
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    const parsed = parseFloat(value)
    if (isNaN(parsed) || parsed < 0) return
    const hardParsed = hardValue.trim() === "" ? null : parseFloat(hardValue)
    if (hardParsed != null && (isNaN(hardParsed) || hardParsed < 0)) return
    setSaving(true)
    try {
      await onSave(email, parsed, hardParsed)
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
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <label style={{ fontSize: 10.5, color: "var(--text-muted)" }} title="Monthly soft limit — warns at threshold">
        soft $
        <input
          type="number" min="0" step="10"
          value={value}
          onChange={e => setValue(e.target.value)}
          style={{ width: 56, fontSize: 11, border: "1px solid var(--border-2)", borderRadius: 5, padding: "2px 6px", marginLeft: 3 }}
          autoFocus
          onKeyDown={e => {
            if (e.key === "Enter") handleSave()
            if (e.key === "Escape") setEditing(false)
          }}
        />
      </label>
      <label style={{ fontSize: 10.5, color: "var(--text-muted)" }} title="Hard cap — blocks tool calls once reached. Leave blank for no cap.">
        hard $
        <input
          type="number" min="0" step="10"
          value={hardValue}
          placeholder="—"
          onChange={e => setHardValue(e.target.value)}
          style={{ width: 56, fontSize: 11, border: "1px solid var(--border-2)", borderRadius: 5, padding: "2px 6px", marginLeft: 3 }}
          onKeyDown={e => {
            if (e.key === "Enter") handleSave()
            if (e.key === "Escape") setEditing(false)
          }}
        />
      </label>
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

// ─── Month picker ─────────────────────────────────────────────────────

export function MonthPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
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
