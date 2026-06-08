"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell, SeverityPill, StatusBadge, SEVERITY_STYLES } from "../_components"
import { timeAgo } from "@/lib/runUtils"
import { useWorkspace } from "@/lib/WorkspaceContext"

type Severity = "critical" | "high" | "medium" | "low" | "info"
type FindingStatus = "open" | "triaging" | "fixed" | "dismissed"

interface SecurityFinding {
  id: string
  severity: Severity
  type: string
  file: string | null
  line: number | null
  description: string
  tool: string | null
  repo_full_name: string | null
  status: FindingStatus
  created_at: string
  source_run_id: string | null
}

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"]

export default function SecureActivityPage() {
  return <AppShell><ActivityContent /></AppShell>
}

function ActivityContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id
  const [findings, setFindings] = useState<SecurityFinding[]>([])
  const [loading, setLoading] = useState(true)
  const [filterSeverity, setFilterSeverity] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterTool, setFilterTool] = useState("all")
  const [filterDays, setFilterDays] = useState(30)

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const buildHeaders = useCallback(async () => {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }, [getToken])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/security-findings?workspace_id=${wsId}&days=${filterDays}&limit=500`, { headers })
      if (res.ok) setFindings(await res.json())
    } catch {}
    finally { setLoading(false) }
  }, [base, wsId, buildHeaders, filterDays])

  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  const tools = Array.from(new Set(findings.map(f => f.tool).filter(Boolean))) as string[]

  const filtered = findings
    .filter(f =>
      (filterSeverity === "all" || f.severity === filterSeverity) &&
      (filterStatus === "all" || f.status === filterStatus) &&
      (filterTool === "all" || f.tool === filterTool)
    )
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  const selectStyle: React.CSSProperties = {
    fontSize: 13, border: "1px solid var(--border)", borderRadius: 8,
    padding: "6px 12px", background: "var(--surface)", color: "var(--text-2)", cursor: "pointer",
  }

  const cols = "100px 120px 1.6fr 2fr 100px 120px 90px 80px 100px"
  const headers = ["Severity", "Type", "File", "Description", "Tool", "Repo", "Session", "Age", "Status"]

  return (
    <SecureShell>
      <div className="eyebrow" style={{ marginBottom: 11 }}>
        Activity log{" "}
        <span style={{ textTransform: "none", letterSpacing: 0, color: "var(--text-muted)", fontWeight: 500 }}>
          · last {filterDays} days
        </span>
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 14 }}>
        <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)} style={selectStyle}>
          <option value="all">All severities</option>
          {["critical","high","medium","low","info"].map(s => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase()+s.slice(1)}</option>
          ))}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={selectStyle}>
          <option value="all">All statuses</option>
          {["open","triaging","fixed","dismissed"].map(s => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase()+s.slice(1)}</option>
          ))}
        </select>
        <select value={filterTool} onChange={e => setFilterTool(e.target.value)} style={selectStyle}>
          <option value="all">All tools</option>
          {tools.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={filterDays} onChange={e => setFilterDays(Number(e.target.value))} style={selectStyle}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
          {filtered.length} finding{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Table */}
      <div className="card" style={{ overflow: "hidden", marginBottom: 26 }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          {headers.map(h => <div key={h} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>)}
        </div>
        {loading ? (
          <div style={{ padding: 20, fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: "48px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No findings match your filters.
          </div>
        ) : filtered.map((f, i, arr) => {
          const filePart = f.file ? (f.line != null ? `${f.file}:${f.line}` : f.file) : "—"
          const session = f.source_run_id ? f.source_run_id.slice(0, 8) : "—"
          return (
            <div
              key={f.id}
              style={{ display: "grid", gridTemplateColumns: cols, gap: 12, padding: "12px 20px", borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center" }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
              onMouseLeave={e => (e.currentTarget.style.background = "")}
            >
              <SeverityPill severity={f.severity} />
              <div style={{ fontSize: 12.5, color: "var(--text-2)", fontWeight: 500 }}>{f.type || "—"}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filePart}</div>
              <div style={{ fontSize: 12.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.description}>
                {f.description.length > 80 ? f.description.slice(0, 77) + "…" : f.description}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>{f.tool || "—"}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.repo_full_name || "—"}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{session}</div>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>{timeAgo(f.created_at)}</div>
              <StatusBadge status={f.status} />
            </div>
          )
        })}
      </div>
    </SecureShell>
  )
}
