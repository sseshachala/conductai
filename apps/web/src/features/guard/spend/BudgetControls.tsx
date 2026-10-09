"use client"

import { useState } from "react"
import { MONTHS } from "./shared"

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
