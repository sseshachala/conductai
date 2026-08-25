"use client"
import { API } from "@/lib/api"

import { useEffect, useState, useCallback } from "react"
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts"
import { DecisionBadge } from "@/components/guard/DecisionBadge"

function fmt(n: number): string {
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M"
  if (Math.abs(n) >= 1_000)     return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K"
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SpecKpi {
  label: string
  endpoint: string
  field: string          // field name on object response, or "count" for array length
  params?: Record<string, string | number>
  color?: string         // "err" | "warn" | "ok" — maps to sbadge CSS class for value color
}

export interface SpecChart {
  type: "bar" | "line"
  title: string
  endpoint: string
  field: string          // sub-array key on object response (e.g. "by_ai_tool")
  x: string              // x-axis field name in each row
  y: string              // y-axis field name in each row
}

export interface SpecTable {
  title: string
  endpoint: string
  params?: Record<string, string | number>
}

export interface GlensDashboardSpec {
  title: string
  kpis: SpecKpi[]
  charts: SpecChart[]
  tables?: SpecTable[]
}

interface ChartPoint {
  x: string
  y: number
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Find the x-axis key (date/label) from a row object. */
function detectXKey(row: Record<string, unknown>): string | null {
  const candidates = ["date", "week", "day", "month", "model", "agent", "group", "label", "name"]
  for (const k of candidates) {
    if (k in row) return k
  }
  return null
}

/** Find the y-axis key (numeric value) from a row object. */
function detectYKey(row: Record<string, unknown>, skipKey: string): string | null {
  const candidates = ["count", "total", "amount", "cost", "value", "tokens"]
  for (const k of candidates) {
    if (k in row && k !== skipKey) return k
  }
  // Fallback: first numeric key that isn't the x key
  for (const [k, v] of Object.entries(row)) {
    if (k !== skipKey && typeof v === "number") return k
  }
  return null
}

function rowsToChartPoints(rows: Record<string, unknown>[]): ChartPoint[] {
  if (rows.length === 0) return []
  const xKey = detectXKey(rows[0])
  if (!xKey) return []
  const yKey = detectYKey(rows[0], xKey)
  if (!yKey) return []
  return rows.map(row => ({
    x: String(row[xKey] ?? ""),
    y: Number(row[yKey] ?? 0),
  }))
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

// ─── KPI tile ─────────────────────────────────────────────────────────────────

function KpiTile({
  kpi,
  authFetch,
}: {
  kpi: SpecKpi
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
}) {
  const [value, setValue] = useState<string | number>("—")

  useEffect(() => {
    const qs = kpi.params
      ? "?" + new URLSearchParams(Object.fromEntries(Object.entries(kpi.params).map(([k, v]) => [k, String(v)]))).toString()
      : ""
    authFetch(`${API}${kpi.endpoint}${qs}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data == null) return
        if (kpi.field === "count" && Array.isArray(data)) {
          setValue(fmt(data.length))
        } else if (!Array.isArray(data) && kpi.field in data) {
          const raw = data[kpi.field]
          setValue(typeof raw === "number" ? fmt(raw) : String(raw))
        }
      })
      .catch(() => {})
  }, [kpi, authFetch])

  return (
    <div style={{ flex: "1 1 140px", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-card)", padding: "14px 16px" }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>
        {kpi.label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: kpi.color ? `var(--${kpi.color})` : "var(--text)" }}>{value}</div>
    </div>
  )
}

// ─── Single chart ─────────────────────────────────────────────────────────────

function ChartBlock({
  chart,
  authFetch,
}: {
  chart: SpecChart
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
}) {
  const [points, setPoints] = useState<ChartPoint[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function load() {
      try {
          const res = await authFetch(`${API}${chart.endpoint}`, { signal: controller.signal })
        if (!res.ok) {
          if (!cancelled) setFailed(true)
          return
        }
        const raw: unknown = await res.json()
        if (!cancelled) {
          // Response may be an object with a sub-array (e.g. spend summary)
          // or a direct array
          let rows: Record<string, unknown>[]
          if (Array.isArray(raw)) {
            rows = raw as Record<string, unknown>[]
          } else if (raw && typeof raw === "object" && chart.field in (raw as object)) {
            const sub = (raw as Record<string, unknown>)[chart.field]
            rows = Array.isArray(sub) ? sub as Record<string, unknown>[] : []
          } else {
            rows = []
          }
          setPoints(rows.map(row => ({
            x: String(row[chart.x] ?? ""),
            y: Number(row[chart.y] ?? 0),
          })))
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return
        if (!cancelled) setFailed(true)
      }
    }

    load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [chart.endpoint, chart.field, chart.x, chart.y, authFetch])

  const containerStyle: React.CSSProperties = {
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--r-card)",
    padding: "14px 16px",
  }

  const titleStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: ".04em",
    marginBottom: 10,
  }

  if (failed) {
    return (
      <div style={containerStyle}>
        <div style={titleStyle}>{chart.title}</div>
        <div
          style={{
            height: 120,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            color: "var(--text-muted)",
          }}
        >
          Could not load chart data
        </div>
      </div>
    )
  }

  if (points === null) {
    return (
      <div style={containerStyle}>
        <div style={titleStyle}>{chart.title}</div>
        <div
          style={{
            height: 120,
            background: "var(--surface-3, var(--surface))",
            borderRadius: 6,
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        />
      </div>
    )
  }

  if (points.length === 0) {
    return (
      <div style={containerStyle}>
        <div style={titleStyle}>{chart.title}</div>
        <div
          style={{
            height: 120,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            color: "var(--text-muted)",
          }}
        >
          No data available
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={titleStyle}>{chart.title}</div>
      <ResponsiveContainer width="100%" height={120}>
        {chart.type === "bar" ? (
          <BarChart data={points} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="x"
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
              }}
              formatter={(val) => [String(val ?? 0), chart.title]}
            />
            <Bar dataKey="y" name={chart.title} fill="var(--accent)" radius={[3, 3, 0, 0]} />
          </BarChart>
        ) : (
          <LineChart data={points} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="x"
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
              }}
              formatter={(val) => [String(val ?? 0), chart.title]}
            />
            <Line
              type="monotone"
              dataKey="y"
              name={chart.title}
              stroke="var(--accent)"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

// ─── HTML export ──────────────────────────────────────────────────────────────

function buildExportHtml(spec: GlensDashboardSpec, _unused: unknown[]): string {
  const kpiHtml = spec.kpis
    .map(k => `
    <div class="kpi">
      <div class="kpi-label">${escapeHtml(String(k.label))}</div>
      <div class="kpi-value">—</div>
    </div>`)
    .join("")

  const metaHtml = `<span>Exported: ${new Date().toLocaleString()}</span>`

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${escapeHtml(spec.title)} — Lens Export</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f9fa; color: #1a1a2e; padding: 32px 24px; }
  h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
  .meta { font-size: 12px; color: #666; margin-bottom: 28px; }
  .kpi-grid { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 28px; }
  .kpi { flex: 1 1 140px; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; }
  .kpi-label { font-size: 10px; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
  .kpi-value { font-size: 24px; font-weight: 700; color: #1a1a2e; }
  .section-title { font-size: 11px; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: .06em; margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; font-size: 13px; }
  th { text-align: left; padding: 8px 12px; background: #f1f5f9; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; color: #666; border-bottom: 1px solid #e2e8f0; }
  td { padding: 9px 12px; border-bottom: 1px solid #f1f5f9; color: #333; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  .note { margin-top: 28px; font-size: 11px; color: #aaa; }
</style>
</head>
<body>
<h1>${escapeHtml(spec.title)}</h1>
<p class="meta">${metaHtml}</p>
<div class="kpi-grid">${kpiHtml}</div>
<p class="note">Generated by Lens · ConductGuard</p>
</body>
</html>`
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function triggerDownload(html: string, filename: string) {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ─── Main shared dashboard component ──────────────────────────────────────────

export interface GlensDashboardProps {
  spec: GlensDashboardSpec
  sessionId: string
  /** Compact = rendered inside the panel (420px). Full = full page. */
  compact?: boolean
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onPin?: () => void
}

// ─── Table block ──────────────────────────────────────────────────────────────

function TableBlock({
  table,
  authFetch,
}: {
  table: SpecTable
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
}) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([])

  useEffect(() => {
    const qs = table.params
      ? "?" + new URLSearchParams(Object.fromEntries(Object.entries(table.params).map(([k, v]) => [k, String(v)]))).toString()
      : ""
    authFetch(`${API}${table.endpoint}${qs}`)
      .then(r => r.ok ? r.json() : [])
      .then(d => setRows(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [table, authFetch])

  const cols = rows.length > 0
    ? ["decision", "ai_tool", "user_email", "rule_id"].filter(k => k in rows[0])
    : []

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 8 }}>
        {table.title}
      </div>
      {rows.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "12px 0" }}>No data.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {cols.map(col => (
                  <th key={col} style={{ textAlign: "left", padding: "6px 10px", borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", fontSize: 10, letterSpacing: ".04em" }}>
                    {col.replace(/_/g, " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} style={{ borderBottom: "1px solid var(--border)" }}>
                  {cols.map(col => (
                    <td key={col} style={{ padding: "8px 10px", color: "var(--text-2)", verticalAlign: "top" }}>
                      {col === "decision"
                        ? <DecisionBadge decision={String(row[col] ?? "")} />
                        : String(row[col] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function GlensDashboard({
  spec,
  sessionId,
  compact = true,
  authFetch,
  onPin,
}: GlensDashboardProps) {
  const handleExport = useCallback(() => {
    const html = buildExportHtml(spec, [])
    const filename = `glens-${slugify(spec.title)}-${todayIso()}.html`
    triggerDownload(html, filename)
  }, [spec])

  return (
    <div>
      {/* Title + actions */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: compact ? 16 : 24,
        }}
      >
        <h2
          style={{
            fontSize: compact ? 16 : 20,
            fontWeight: 700,
            color: "var(--text)",
            flex: 1,
            margin: 0,
          }}
        >
          {spec.title}
        </h2>
        {onPin && (
          <button
            onClick={onPin}
            title="Open full page"
            aria-label="Open full dashboard page"
            style={{
              fontSize: 14,
              background: "none",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-btn)",
              padding: "4px 8px",
              cursor: "pointer",
              color: "var(--text-2)",
            }}
          >
            ↗
          </button>
        )}
        <button
          onClick={handleExport}
          title="Export as HTML"
          aria-label="Export dashboard as HTML"
          style={{
            fontSize: 14,
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-btn)",
            padding: "4px 8px",
            cursor: "pointer",
            color: "var(--text-2)",
          }}
        >
          ⬇
        </button>
      </div>


      {/* KPI tiles */}
      {spec.kpis.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            marginBottom: compact ? 16 : 24,
          }}
        >
          {spec.kpis.map(kpi => (
            <KpiTile key={kpi.label} kpi={kpi} authFetch={authFetch} />
          ))}
        </div>
      )}

      {/* Charts */}
      {spec.charts.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            marginBottom: compact ? 16 : 24,
          }}
        >
          {spec.charts.map(chart => (
            <ChartBlock key={`${chart.endpoint}-${chart.field}`} chart={chart} authFetch={authFetch} />
          ))}
        </div>
      )}

      {/* Tables */}
      {(spec.tables ?? []).map((tbl, ti) => (
        <TableBlock key={ti} table={tbl} authFetch={authFetch} />
      ))}

      {/* Non-compact: session link */}
      {!compact && (
        <div
          style={{
            marginTop: 32,
            paddingTop: 16,
            borderTop: "1px solid var(--border)",
            fontSize: 11,
            color: "var(--text-muted)",
          }}
        >
          Session ID: {sessionId}
        </div>
      )}
    </div>
  )
}
