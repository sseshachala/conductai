// Shared Spend components used by both /theguard/spend (Configure) and
// /theguard/spend/glance (Spend at a glance).
//
// Kept small and dumb — each component takes props, renders UI, calls
// callbacks. State + fetching live in useSpendState so both pages
// consume the same source of truth without duplicating logic.
"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AI_TOOL_OPTIONS,
  TRANSPORT_OPTIONS,
  CURRENCY_SYMBOLS,
  MONTHS,
  fromUsd,
  toUsd,
  type Currency,
  type ModelBreakdown,
  type ProviderBreakdown,
  type TeamBudgetSettings,
  type ToolCap,
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

// ─── Per-tool caps panel (F3 — cross-tool bleed fix) ────────────────────
//
// A workspace-wide monthly cap scoped to a single AI tool. When set, budget
// checks for that tool sum only that tool's cost — so a Codex Desktop
// overspend does not block a Claude Code caller. Enforcement is still gated
// by the workspace-default hard_cap_enabled flag on the main Spend controls
// panel; if that's off, per-tool caps are advisory (visible but not
// blocking).
export function PerToolCapsPanel({
  caps,
  currency,
  hardCapEnabled,
  onSave,
  onRemove,
  readOnly,
}: {
  caps: ToolCap[]
  currency: Currency
  hardCapEnabled: boolean
  onSave: (ai_tool: string, monthly_limit_usd: number) => Promise<void>
  onRemove: (id: string) => Promise<void>
  readOnly?: boolean
}) {
  const sym = CURRENCY_SYMBOLS[currency] ?? "$"
  const [addingTool, setAddingTool] = useState<string>("")
  const [addingAmount, setAddingAmount] = useState<string>("")
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const takenTools = useMemo(() => new Set(caps.map(c => c.ai_tool)), [caps])
  const availableTools = useMemo(
    () => AI_TOOL_OPTIONS.filter(t => !takenTools.has(t)),
    [takenTools],
  )
  // Transports first — they cap the aggregate transport pool regardless of
  // client tool. Client tools cap a specific declared caller. Both write to
  // the same ai_tool column; the optgroup labels are for the admin's benefit.
  const availableTransports = useMemo(
    () => TRANSPORT_OPTIONS.filter(t => !takenTools.has(t)),
    [takenTools],
  )

  const parseAmt = (v: string): number => Math.max(0, Math.round(toUsd(parseFloat(v) || 0, currency) * 100) / 100)
  const displayAmt = (usd: number): string => (Math.round(fromUsd(usd, currency) * 100) / 100).toString()

  const handleAdd = async () => {
    if (!addingTool || !addingAmount) return
    setSaving(true)
    setErr(null)
    try {
      await onSave(addingTool, parseAmt(addingAmount))
      setAddingTool("")
      setAddingAmount("")
    } catch (e: any) {
      setErr(e?.message ?? "Failed to add per-tool cap")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card" style={{ borderColor: "var(--warn-bd)", marginBottom: 22, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 22px", borderBottom: "1px solid var(--border)" }}>
        <span style={{ width: 32, height: 32, borderRadius: 9, background: "var(--warn-bg)", color: "var(--warn)", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 6h16M4 12h16M4 18h10" />
          </svg>
        </span>
        <div>
          <div style={{ fontWeight: 650, fontSize: 15 }}>Per-tool caps</div>
          <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>
            {hardCapEnabled
              ? "Overspend on one tool won't block the others."
              : "Advisory only until Hard cap at 100% is turned on above."}
          </div>
        </div>
      </div>

      {!readOnly && (availableTools.length > 0 || availableTransports.length > 0) && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "160px 1fr auto",
            gap: 16,
            alignItems: "center",
            padding: "14px 22px",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-1)",
          }}
        >
          <select
            value={addingTool}
            onChange={e => setAddingTool(e.target.value)}
            aria-label="AI tool"
            style={{ padding: "6px 10px", borderRadius: 7, border: "1px solid var(--border-2)", fontSize: 13 }}
          >
            <option value="">Select a tool…</option>
            {availableTransports.length > 0 && (
              <optgroup label="Transports">
                {availableTransports.map(t => (
                  <option key={`transport-${t}`} value={t}>{t}</option>
                ))}
              </optgroup>
            )}
            {availableTools.length > 0 && (
              <optgroup label="Client tools">
                {availableTools.map(t => (
                  <option key={`tool-${t}`} value={t}>{t}</option>
                ))}
              </optgroup>
            )}
          </select>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{sym}</span>
            <input
              type="number" min="0.01" step="0.01"
              value={addingAmount}
              onChange={e => setAddingAmount(e.target.value)}
              placeholder="Monthly limit"
              style={{ width: 140, fontSize: 13, border: "1px solid var(--border-2)", borderRadius: 7, padding: "5px 10px" }}
            />
          </div>
          <button
            onClick={handleAdd}
            disabled={!addingTool || !addingAmount || saving}
            className="btn btn-primary btn-sm"
            style={{ opacity: (!addingTool || !addingAmount || saving) ? 0.6 : 1 }}
          >
            {saving ? "Adding…" : "Add"}
          </button>
        </div>
      )}

      {caps.length === 0 ? (
        <div style={{ padding: "18px 22px", color: "var(--text-muted)", fontSize: 13 }}>
          No per-tool caps set. Add one above to scope enforcement to a single tool.
        </div>
      ) : (
        <div>
          {caps.map(c => (
            <div
              key={c.id}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 1fr auto",
                gap: 16,
                alignItems: "center",
                padding: "12px 22px",
                borderTop: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 600 }}>{c.ai_tool}</div>
              <div style={{ fontSize: 13, color: "var(--text-2)" }}>
                {sym}{Math.round(fromUsd(c.current_month_cost_usd, currency)).toLocaleString()}
                {" / "}
                {sym}{Math.round(fromUsd(c.monthly_limit_usd, currency)).toLocaleString()} this month
              </div>
              {!readOnly && (
                <button
                  onClick={() => onRemove(c.id).catch(e => setErr(e?.message ?? "Remove failed"))}
                  className="btn btn-ghost btn-sm"
                  aria-label={`Remove ${c.ai_tool} cap`}
                  title="Remove cap"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {err && (
        <div style={{ padding: "10px 22px", color: "var(--err)", fontSize: 12.5, borderTop: "1px solid var(--border)" }}>
          {err}
        </div>
      )}
    </div>
  )
}

export { ModelSpendPanel } from "./ModelSpendPanel"
export { BudgetBar, BudgetInput, MonthPicker } from "./BudgetControls"
