"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

type Severity = "critical" | "high" | "medium" | "low" | "info"
type FindingStatus = "open" | "triaging" | "fixed" | "dismissed"

interface SecurityFinding {
  id: string
  severity: Severity
  type: string
  file_path: string | null
  line_number: number | null
  description: string
  tool: string | null
  repo: string | null
  status: FindingStatus
  created_at: string
  fixed_at: string | null
}

interface SecuritySummary {
  open: number
  critical_high: number
  fixed_this_month: number
  mttr_hours: number | null
}

const SEVERITY_STYLES: Record<Severity, { bg: string; color: string; label: string }> = {
  critical: { bg: "#fee2e2", color: "#dc2626", label: "Critical" },
  high:     { bg: "#fff7ed", color: "#ea580c", label: "High" },
  medium:   { bg: "#fefce8", color: "#ca8a04", label: "Medium" },
  low:      { bg: "#eff6ff", color: "#2563eb", label: "Low" },
  info:     { bg: "#f5f5f4", color: "#78716c", label: "Info" },
}

const STATUS_STYLES: Record<FindingStatus, { bg: string; color: string; label: string }> = {
  open:       { bg: "var(--surface-3)", color: "var(--text-3)",  label: "Open" },
  triaging:   { bg: "var(--info-bg)",   color: "var(--info)",    label: "Triaging" },
  fixed:      { bg: "var(--ok-bg)",     color: "var(--ok)",      label: "Fixed" },
  dismissed:  { bg: "var(--surface-3)", color: "var(--text-muted)", label: "Dismissed" },
}

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"]

function SeverityPill({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      padding: "2px 9px",
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 700,
      background: s.bg,
      color: s.color,
      whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

function StatusBadge({ status }: { status: FindingStatus }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.open
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      padding: "2px 9px",
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 600,
      background: s.bg,
      color: s.color,
      whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

function SkeletonCard() {
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <div style={{ width: 60, height: 26, borderRadius: 6, background: "var(--surface-3)", marginBottom: 10 }} />
      <div style={{ width: 90, height: 10, borderRadius: 4, background: "var(--surface-3)" }} />
    </div>
  )
}

export default function SecurityPage() {
  const { getToken } = useAuth()

  const [summary, setSummary] = useState<SecuritySummary | null>(null)
  const [findings, setFindings] = useState<SecurityFinding[]>([])
  const [loading, setLoading] = useState(true)

  // Filters
  const [filterSeverity, setFilterSeverity] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterDays, setFilterDays] = useState(30)

  const buildHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id") ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`
    if (workspaceId) headers["x-workspace-id"] = workspaceId
    return headers
  }, [getToken])

  const load = useCallback(async (days: number) => {
    setLoading(true)
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    try {
      const headers = await buildHeaders()
      const [findingsRes, summaryRes] = await Promise.all([
        fetch(`${base}/security-findings?days=${days}&limit=100`, { headers }),
        fetch(`${base}/security-findings/summary?days=${days}`, { headers }),
      ])
      if (findingsRes.ok) setFindings(await findingsRes.json())
      if (summaryRes.ok) setSummary(await summaryRes.json())
    } catch {
      // non-fatal — keep last known state
    } finally {
      setLoading(false)
    }
  }, [buildHeaders])

  useEffect(() => {
    load(filterDays)
  }, [load, filterDays])

  const selectStyle: React.CSSProperties = {
    fontSize: 13,
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "6px 12px",
    background: "var(--surface)",
    color: "var(--text-2)",
    cursor: "pointer",
  }

  const filteredFindings = findings.filter(f => {
    if (filterSeverity !== "all" && f.severity !== filterSeverity) return false
    if (filterStatus !== "all" && f.status !== filterStatus) return false
    return true
  }).sort((a, b) => {
    const si = SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
    if (si !== 0) return si
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })

  const anyFilter = filterSeverity !== "all" || filterStatus !== "all"

  const kpiCards = [
    {
      v: loading ? "—" : String(summary?.open ?? 0),
      k: "Open",
      tone: (summary?.open ?? 0) > 0 ? "var(--err)" : "var(--ok)",
    },
    {
      v: loading ? "—" : String(summary?.critical_high ?? 0),
      k: "Critical / High",
      tone: (summary?.critical_high ?? 0) > 0 ? "var(--err)" : "var(--ok)",
    },
    {
      v: loading ? "—" : String(summary?.fixed_this_month ?? 0),
      k: "Fixed this month",
      tone: "var(--ok)",
    },
    {
      v: loading ? "—" : summary?.mttr_hours != null ? `${summary.mttr_hours.toFixed(1)}h` : "—",
      k: "MTTR",
      tone: "var(--text)",
    },
  ]

  return (
    <AppShell>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "30px 34px 80px" }}>

        {/* Header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-start" }}>
          <div>
            <h1 className="page-title">Security</h1>
            <p className="page-sub">Findings from AI tools surfaced by the Security Loop.</p>
          </div>
          <div style={{ marginLeft: "auto" }}>
            <button className="btn btn-ghost" onClick={() => load(filterDays)}>Refresh</button>
          </div>
        </div>

        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 24 }}>
          {loading
            ? [0, 1, 2, 3].map(i => <SkeletonCard key={i} />)
            : kpiCards.map(s => (
              <div key={s.k} className="card" style={{ padding: "16px 18px" }}>
                <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", color: s.tone, lineHeight: 1.1 }}>{s.v}</div>
                <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>{s.k}</div>
              </div>
            ))
          }
        </div>

        {/* Findings section */}
        <div className="eyebrow" style={{ marginBottom: 11 }}>
          Findings{" "}
          <span style={{ textTransform: "none", letterSpacing: 0, color: "var(--text-muted)", fontWeight: 500 }}>
            · last {filterDays} days
          </span>
        </div>

        {/* Filters bar */}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <select
            value={filterSeverity}
            onChange={e => setFilterSeverity(e.target.value)}
            style={selectStyle}
          >
            <option value="all">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>

          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)}
            style={selectStyle}
          >
            <option value="all">All statuses</option>
            <option value="open">Open</option>
            <option value="triaging">Triaging</option>
            <option value="fixed">Fixed</option>
            <option value="dismissed">Dismissed</option>
          </select>

          <select
            value={filterDays}
            onChange={e => setFilterDays(Number(e.target.value))}
            style={selectStyle}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>

          {anyFilter && (
            <button
              className="btn btn-ghost"
              style={{ fontSize: 12 }}
              onClick={() => { setFilterSeverity("all"); setFilterStatus("all") }}
            >
              Clear filters
            </button>
          )}

          <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
            {filteredFindings.length} finding{filteredFindings.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Findings table */}
        <div className="card" style={{ overflow: "hidden", marginBottom: 26 }}>
          {/* Column headers */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "100px 120px 1.4fr 2fr 90px 110px 80px 100px",
            gap: 12,
            padding: "10px 20px",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface-2)",
          }}>
            {["Severity", "Type", "File", "Description", "Tool", "Repo", "Age", "Status"].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
            ))}
          </div>

          {loading ? (
            <div style={{ padding: "20px", color: "var(--text-muted)", fontSize: 13 }}>Loading…</div>
          ) : filteredFindings.length === 0 ? (
            <div style={{ padding: "48px 20px", textAlign: "center" }}>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 6 }}>
                No findings yet — run{" "}
                <code style={{ fontSize: 12, background: "var(--surface-3)", padding: "1px 6px", borderRadius: 4 }}>
                  conduct emit finding
                </code>
                {" "}or install the Security Loop playbook.
              </div>
            </div>
          ) : (
            filteredFindings.map((f, i, arr) => {
              const filePart = f.file_path
                ? f.line_number != null
                  ? `${f.file_path}:${f.line_number}`
                  : f.file_path
                : "—"
              const desc = f.description.length > 80
                ? f.description.slice(0, 77) + "…"
                : f.description

              return (
                <div
                  key={f.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "100px 120px 1.4fr 2fr 90px 110px 80px 100px",
                    gap: 12,
                    padding: "12px 20px",
                    borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none",
                    alignItems: "center",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "")}
                >
                  <div><SeverityPill severity={f.severity} /></div>
                  <div style={{ fontSize: 12.5, color: "var(--text-2)", fontWeight: 500 }}>{f.type || "—"}</div>
                  <div
                    className="mono"
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-3)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={filePart !== "—" ? filePart : undefined}
                  >
                    {filePart}
                  </div>
                  <div
                    style={{
                      fontSize: 12.5,
                      color: "var(--text-2)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={f.description}
                  >
                    {desc}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{f.tool || "—"}</div>
                  <div
                    className="mono"
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={f.repo ?? undefined}
                  >
                    {f.repo || "—"}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{timeAgo(f.created_at)}</div>
                  <div><StatusBadge status={f.status} /></div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </AppShell>
  )
}
