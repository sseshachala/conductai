"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import { usePathname } from "next/navigation"
import AppShell from "@/components/AppShell"
import { timeAgo } from "@/lib/runUtils"

// ─── Types ────────────────────────────────────────────────────────────────────

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
}

interface SecuritySummary {
  total: number
  by_severity: Record<string, number>
  by_status: Record<string, number>
  mttr_hours: number | null
}

// ─── Shared styles ────────────────────────────────────────────────────────────

export const SEVERITY_STYLES: Record<Severity, { bg: string; color: string; label: string }> = {
  critical: { bg: "#fee2e2", color: "#dc2626", label: "Critical" },
  high:     { bg: "#fff7ed", color: "#ea580c", label: "High" },
  medium:   { bg: "#fefce8", color: "#ca8a04", label: "Medium" },
  low:      { bg: "#eff6ff", color: "#2563eb", label: "Low" },
  info:     { bg: "#f5f5f4", color: "#78716c", label: "Info" },
}

export const STATUS_STYLES: Record<FindingStatus, { bg: string; color: string; label: string }> = {
  open:      { bg: "var(--surface-3)", color: "var(--text-3)",     label: "Open" },
  triaging:  { bg: "var(--info-bg)",   color: "var(--info)",       label: "Triaging" },
  fixed:     { bg: "var(--ok-bg)",     color: "var(--ok)",         label: "Fixed" },
  dismissed: { bg: "var(--surface-3)", color: "var(--text-muted)", label: "Dismissed" },
}

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"]

// ─── Secure Shell ─────────────────────────────────────────────────────────────

const SECURE_TABS = [
  { href: "/secure",           label: "Overview"  },
  { href: "/secure/activity",  label: "Activity"  },
  { href: "/secure/policies",  label: "Policies"  },
  { href: "/secure/settings",  label: "Settings"  },
]

export function SecureShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
              Secure
            </h1>
            <span className="sbadge ok" style={{ marginTop: 2 }}>
              <span className="conduct-pulse-dot" />
              active
            </span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
            Security Loop for Claude Code — captures findings from every AI-assisted coding session.
          </p>
        </div>
      </div>
      <div className="guard-tab-nav">
        {SECURE_TABS.map(tab => {
          const isActive = tab.href === "/secure"
            ? pathname === "/secure"
            : pathname?.startsWith(tab.href)
          return (
            <Link key={tab.href} href={tab.href} className={`guard-tab${isActive ? " active" : ""}`}>
              {tab.label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}

// ─── Shared components ────────────────────────────────────────────────────────

export function SeverityPill({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "2px 9px", borderRadius: 20,
      fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.open
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "2px 9px", borderRadius: 20,
      fontSize: 11, fontWeight: 600,
      background: s.bg, color: s.color, whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

// ─── Overview page ────────────────────────────────────────────────────────────

export default function SecureOverviewPage() {
  return <AppShell><SecureOverview /></AppShell>
}

function SecureOverview() {
  const { getToken } = useAuth()
  const [summary, setSummary] = useState<SecuritySummary | null>(null)
  const [findings, setFindings] = useState<SecurityFinding[]>([])
  const [loading, setLoading] = useState(true)
  const [filterSeverity, setFilterSeverity] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterDays, setFilterDays] = useState(30)

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
        fetch(`${base}/security-findings?days=${days}&limit=100`, { headers }),
        fetch(`${base}/security-findings/summary?days=${days}`, { headers }),
      ])
      if (fr.ok) setFindings(await fr.json())
      if (sr.ok) setSummary(await sr.json())
    } catch {}
    finally { setLoading(false) }
  }, [base, buildHeaders])

  useEffect(() => { load(filterDays) }, [load, filterDays])

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
    { v: loading ? "—" : String(open),                                       k: "Open",            tone: open > 0 ? "var(--err)" : "var(--ok)" },
    { v: loading ? "—" : String(critHigh),                                    k: "Critical / High", tone: critHigh > 0 ? "var(--err)" : "var(--ok)" },
    { v: loading ? "—" : String(fixed),                                       k: "Fixed this month", tone: "var(--ok)" },
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

      {/* Findings table */}
      <FindingsTable findings={filteredFindings} loading={loading} />
    </SecureShell>
  )
}

// ─── Findings table (shared) ──────────────────────────────────────────────────

export function FindingsTable({ findings, loading }: { findings: SecurityFinding[]; loading: boolean }) {
  const cols = "100px 120px 1.4fr 2fr 90px 110px 80px 100px"
  const headers = ["Severity", "Type", "File", "Description", "Tool", "Repo", "Age", "Status"]
  return (
    <div className="card" style={{ overflow: "hidden", marginBottom: 26 }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
        {headers.map(h => <div key={h} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>)}
      </div>
      {loading ? (
        <div style={{ padding: 20, fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
      ) : findings.length === 0 ? (
        <div style={{ padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 6 }}>
            No findings — enable Security Emit in{" "}
            <Link href="/secure/settings" style={{ color: "var(--accent)", textDecoration: "none" }}>Settings</Link>
            {" "}to start capturing.
          </div>
        </div>
      ) : findings.map((f, i, arr) => {
        const filePart = f.file ? (f.line != null ? `${f.file}:${f.line}` : f.file) : "—"
        return (
          <div
            key={f.id}
            style={{ display: "grid", gridTemplateColumns: cols, gap: 12, padding: "12px 20px", borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            <SeverityPill severity={f.severity} />
            <div style={{ fontSize: 12.5, color: "var(--text-2)", fontWeight: 500 }}>{f.type || "—"}</div>
            <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={filePart !== "—" ? filePart : undefined}>{filePart}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.description}>{f.description.length > 80 ? f.description.slice(0, 77) + "…" : f.description}</div>
            <div style={{ fontSize: 12, color: "var(--text-3)" }}>{f.tool || "—"}</div>
            <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.repo_full_name || "—"}</div>
            <div style={{ fontSize: 12, color: "var(--text-3)" }}>{timeAgo(f.created_at)}</div>
            <StatusBadge status={f.status} />
          </div>
        )
      })}
    </div>
  )
}
