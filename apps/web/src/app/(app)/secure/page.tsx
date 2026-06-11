"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell, SeverityPill, StatusBadge, FindingsTable } from "./_components"
import type { SecurityFinding, FindingStatus } from "./_components"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface SecuritySummary {
  total: number
  by_severity: Record<string, number>
  by_status: Record<string, number>
  mttr_hours: number | null
}

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

export default function SecureOverviewPage() {
  return <AppShell><SecureOverview /></AppShell>
}

function SecureOverview() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id
  const [summary, setSummary] = useState<SecuritySummary | null>(null)
  const [findings, setFindings] = useState<SecurityFinding[]>([])
  const [loading, setLoading] = useState(true)
  const [filterSeverity, setFilterSeverity] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterDays, setFilterDays] = useState(30)
  const [updating, setUpdating] = useState<Record<string, boolean>>({})

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const buildHeaders = useCallback(async () => {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }, [getToken])

  const load = useCallback(async (days: number) => {
    setLoading(true)
    try {
      const headers = await buildHeaders()
      const [fr, sr] = await Promise.all([
        fetch(`${base}/security-findings?workspace_id=${wsId}&days=${days}&limit=100`, { headers }),
        fetch(`${base}/security-findings/summary?workspace_id=${wsId}&days=${days}`, { headers }),
      ])
      if (fr.ok) setFindings(await fr.json())
      if (sr.ok) setSummary(await sr.json())
    } catch {}
    finally { setLoading(false) }
  }, [base, wsId, buildHeaders])

  useEffect(() => {
    load(filterDays)
    const t = setInterval(() => load(filterDays), 30_000)
    return () => clearInterval(t)
  }, [load, filterDays])

  const updateStatus = useCallback(async (id: string, next: FindingStatus) => {
    setUpdating(u => ({ ...u, [id]: true }))
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/security-findings/${id}?workspace_id=${wsId}`, {
        method: "PATCH", headers, body: JSON.stringify({ status: next }),
      })
      if (res.ok) {
        const updated: SecurityFinding = await res.json()
        setFindings(prev => prev.map(f => f.id === id ? updated : f))
      }
    } catch {}
    finally { setUpdating(u => ({ ...u, [id]: false })) }
  }, [base, wsId, buildHeaders])

  const selectStyle: React.CSSProperties = {
    fontSize: 13, border: "1px solid var(--border)", borderRadius: 8,
    padding: "6px 12px", background: "var(--surface)", color: "var(--text-2)", cursor: "pointer",
  }

  const filteredFindings = findings
    .filter(f => (filterSeverity === "all" || f.severity === filterSeverity) && (filterStatus === "all" || f.status === filterStatus))
    .sort((a, b) => {
      const si = SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
      return si !== 0 ? si : new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  const open = summary?.by_status?.open ?? 0
  const critHigh = (summary?.by_severity?.critical ?? 0) + (summary?.by_severity?.high ?? 0)
  const fixed = summary?.by_status?.fixed ?? 0

  const kpis = [
    { v: loading ? "—" : String(open),     k: "Open",             tone: open > 0 ? "var(--err)" : "var(--ok)" },
    { v: loading ? "—" : String(critHigh), k: "Critical / High",  tone: critHigh > 0 ? "var(--err)" : "var(--ok)" },
    { v: loading ? "—" : String(fixed),    k: "Fixed this month", tone: "var(--ok)" },
    { v: loading ? "—" : summary?.mttr_hours != null ? `${summary.mttr_hours.toFixed(1)}h` : "—", k: "MTTR", tone: "var(--text)" },
  ]

  return (
    <SecureShell>
      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 24 }}>
        {kpis.map(s => (
          <div key={s.k} className="card" style={{ padding: "16px 18px" }}>
            <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", color: s.tone, lineHeight: 1.1 }}>{s.v}</div>
            <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>{s.k}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)} style={selectStyle}>
          <option value="all">All severities</option>
          {["critical","high","medium","low","info"].map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase()+s.slice(1)}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={selectStyle}>
          <option value="all">All statuses</option>
          {["open","triaging","fixed","dismissed"].map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase()+s.slice(1)}</option>)}
        </select>
        <select value={filterDays} onChange={e => setFilterDays(Number(e.target.value))} style={selectStyle}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
          {filteredFindings.length} finding{filteredFindings.length !== 1 ? "s" : ""}
        </span>
      </div>

      <FindingsTable findings={filteredFindings} loading={loading} onStatusChange={updateStatus} updating={updating} />
    </SecureShell>
  )
}
