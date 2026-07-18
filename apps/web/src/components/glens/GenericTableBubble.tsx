"use client"

import { useState, useMemo } from "react"
import { DecisionBadge } from "@/components/guard/DecisionBadge"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Column {
  key: string
  label: string
  type: "text" | "number" | "currency" | "date" | "badge" | "percent" | "boolean"
}

// ─── Column inference ─────────────────────────────────────────────────────────

function toLabel(key: string): string {
  // snake_case / camelCase → "Title Case"
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, c => c.toUpperCase())
}

function inferColumns(rows: Record<string, unknown>[]): Column[] {
  if (!rows.length) return []
  const first = rows[0]
  return Object.keys(first).map(key => {
    const val = first[key]
    // boolean
    if (typeof val === "boolean") return { key, label: toLabel(key), type: "boolean" as const }
    // number
    if (typeof val === "number") {
      if (/cost|usd|price|amount|spend/i.test(key)) return { key, label: toLabel(key), type: "currency" as const }
      if (/pct|percent|ratio|score/i.test(key)) return { key, label: toLabel(key), type: "percent" as const }
      return { key, label: toLabel(key), type: "number" as const }
    }
    // string
    if (typeof val === "string") {
      if (/^\d{4}-\d{2}-\d{2}T/.test(val)) return { key, label: toLabel(key), type: "date" as const }
      const BADGE_VALUES = new Set(["blocked", "warned", "audited", "allowed", "approval", "active", "partial", "missing"])
      if (BADGE_VALUES.has(val.toLowerCase())) return { key, label: toLabel(key), type: "badge" as const }
    }
    return { key, label: toLabel(key), type: "text" as const }
  })
}

// ─── Cell formatters ──────────────────────────────────────────────────────────

function fmtNumber(n: number): string {
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M"
  if (Math.abs(n) >= 1_000)     return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K"
  return Number.isInteger(n) ? String(n) : String(n)
}

function fmtDate(raw: string): string {
  const d = new Date(raw)
  if (isNaN(d.getTime())) return raw
  const datePart = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })
  const timePart = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false })
  return `${datePart} ${timePart}`
}

const STATUS_CLASS: Record<string, string> = {
  active:  "sbadge ok",
  partial: "sbadge warn",
  missing: "sbadge err",
}

const DECISION_VALUES = new Set(["allowed", "blocked", "warned", "audited", "approval"])

function CellContent({ col, value }: { col: Column; value: unknown }) {
  const raw = value ?? ""

  switch (col.type) {
    case "number": {
      const n = Number(raw)
      return <>{isNaN(n) ? String(raw) : fmtNumber(n)}</>
    }
    case "currency": {
      const n = Number(raw)
      return <>{isNaN(n) ? String(raw) : `$${n.toFixed(2)}`}</>
    }
    case "date":
      return <>{fmtDate(String(raw))}</>
    case "badge": {
      const s = String(raw).toLowerCase()
      if (DECISION_VALUES.has(s)) return <DecisionBadge decision={s} />
      const cls = STATUS_CLASS[s]
      if (cls) return <span className={cls}>{String(raw)}</span>
      return <span className="sbadge warn">{String(raw)}</span>
    }
    case "percent": {
      const n = Number(raw)
      return <>{isNaN(n) ? String(raw) : `${n.toFixed(1)}%`}</>
    }
    case "boolean": {
      const b = raw === true || raw === "true" || raw === 1
      return (
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
          <circle cx="6" cy="6" r="6" fill={b ? "var(--ok, #22c55e)" : "var(--text-muted, #94a3b8)"} />
        </svg>
      )
    }
    default:
      return <>{String(raw)}</>
  }
}

// ─── Sortable table ───────────────────────────────────────────────────────────

function sortRows(
  rows: Record<string, unknown>[],
  col: Column | undefined,
  dir: "asc" | "desc",
): Record<string, unknown>[] {
  if (!col) return rows
  return [...rows].sort((a, b) => {
    const av = a[col.key]
    const bv = b[col.key]
    let cmp = 0
    if (typeof av === "number" && typeof bv === "number") {
      cmp = av - bv
    } else {
      cmp = String(av ?? "").localeCompare(String(bv ?? ""))
    }
    return dir === "asc" ? cmp : -cmp
  })
}

export function renderTable(columns: Column[], rows: Record<string, unknown>[]) {
  // This is a plain render helper used by BlocksBubble — no sort state.
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                style={{
                  textAlign: "left",
                  padding: "8px 12px",
                  color: "var(--text-muted)",
                  fontWeight: 600,
                  borderBottom: "1px solid var(--border)",
                  whiteSpace: "nowrap",
                }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ borderBottom: "1px solid var(--border)" }}>
              {columns.map(col => (
                <td key={col.key} style={{ padding: "8px 12px", color: "var(--text-2)", verticalAlign: "top" }}>
                  <CellContent col={col} value={row[col.key]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

const SKILL_LABELS: Record<string, string> = {
  report:       "Report",
  analytics:    "Analytics",
  extract:      "Extract",
  memory:       "Memory",
  session:      "Session",
  rules:        "Rules",
  guard_config: "Guard Config",
  spend_config: "Spend Config",
}

export function GenericTableBubble({
  answer,
  columns,
  rows,
  warning,
  skill,
  drilldown,
}: {
  answer: string
  columns?: Column[]   // optional — inferred from rows when absent
  rows: Record<string, unknown>[]
  warning?: string
  skill?: string
  drilldown?: { path: string; filters?: Record<string, string> }
}) {
  const effectiveCols = (columns && columns.length > 0) ? columns : inferColumns(rows)

  const defaultCol = effectiveCols[0]
  const [sortKey, setSortKey] = useState<string>(defaultCol?.key ?? "")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc")

  const activeCol = useMemo(
    () => effectiveCols.find(c => c.key === sortKey),
    [effectiveCols, sortKey],
  )

  const sorted = useMemo(
    () => sortRows(rows, activeCol, sortDir),
    [rows, activeCol, sortDir],
  )

  function handleHeaderClick(col: Column) {
    if (sortKey === col.key) {
      setSortDir(d => d === "asc" ? "desc" : "asc")
    } else {
      setSortKey(col.key)
      setSortDir("asc")
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{
        width: "100%",
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "16px 20px",
      }}>
        {skill && (
          <div style={{
            fontSize: 10,
            fontWeight: 700,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: ".06em",
            marginBottom: 6,
          }}>
            {SKILL_LABELS[skill] ?? skill}
          </div>
        )}

        {answer && (
          <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 14, lineHeight: 1.5 }}>
            {answer}
          </div>
        )}

        {warning && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
            {warning}
          </div>
        )}

        {rows.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "8px 0" }}>No data.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  {effectiveCols.map(col => {
                    const isActive = sortKey === col.key
                    return (
                      <th
                        key={col.key}
                        onClick={() => handleHeaderClick(col)}
                        style={{
                          textAlign: "left",
                          padding: "8px 12px",
                          color: "var(--text-muted)",
                          fontWeight: 600,
                          borderBottom: "1px solid var(--border)",
                          cursor: "pointer",
                          userSelect: "none",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {col.label}
                        {isActive && (
                          <span style={{ marginLeft: 4, fontSize: 10 }}>
                            {sortDir === "asc" ? "▲" : "▼"}
                          </span>
                        )}
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {sorted.map((row, ri) => (
                  <tr key={ri} style={{ borderBottom: "1px solid var(--border)" }}>
                    {effectiveCols.map(col => (
                      <td key={col.key} style={{ padding: "8px 12px", color: "var(--text-2)", verticalAlign: "top" }}>
                        <CellContent col={col} value={row[col.key]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {drilldown && (
          <div style={{ marginTop: 12, textAlign: "right" }}>
            <a
              href={drilldown.path}
              style={{
                fontSize: 12,
                color: "var(--accent, #6366f1)",
                textDecoration: "none",
                fontWeight: 500,
              }}
            >
              View full &rarr;
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
