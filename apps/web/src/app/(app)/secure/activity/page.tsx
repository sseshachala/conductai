"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell, SeverityPill, StatusBadge, SEVERITY_STYLES, STATUS_TRANSITIONS } from "../_components"
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
  reporter_email: string | null
  status: FindingStatus
  created_at: string
  source_run_id: string | null
}


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
  const [sortBy, setSortBy] = useState<"newest" | "severity">("newest")
  const [updating, setUpdating] = useState<Record<string, boolean>>({})
  const [triggering, setTriggering] = useState<Record<string, boolean>>({})

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

  const updateStatus = useCallback(async (id: string, next: FindingStatus) => {
    setUpdating(u => ({ ...u, [id]: true }))
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/security-findings/${id}?workspace_id=${wsId}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ status: next }),
      })
      if (res.ok) {
        const updated: SecurityFinding = await res.json()
        setFindings(prev => prev.map(f => f.id === id ? updated : f))
      }
    } catch {}
    finally { setUpdating(u => ({ ...u, [id]: false })) }
  }, [base, wsId, buildHeaders])

  const triggerFix = useCallback(async (id: string) => {
    setTriggering(t => ({ ...t, [id]: true }))
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/security-findings/${id}/trigger-fix?workspace_id=${wsId}`, {
        method: "POST", headers,
      })
      if (res.ok) {
        const r = await res.json()
        if (r.triggered) {
          setFindings(prev => prev.map(f => f.id === id ? { ...f, status: "triaging" } : f))
        }
      }
    } catch {}
    finally { setTriggering(t => ({ ...t, [id]: false })) }
  }, [base, wsId, buildHeaders])

  const tools = Array.from(new Set(findings.map(f => f.tool).filter(Boolean))) as string[]

  const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }
  const filtered = findings
    .filter(f =>
      (filterSeverity === "all" || f.severity === filterSeverity) &&
      (filterStatus === "all" || f.status === filterStatus) &&
      (filterTool === "all" || f.tool === filterTool)
    )
    .sort((a, b) => sortBy === "severity"
      ? (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)
      : new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )

  const selectStyle: React.CSSProperties = {
    fontSize: 13, border: "1px solid var(--border)", borderRadius: 8,
    padding: "6px 12px", background: "var(--surface)", color: "var(--text-2)", cursor: "pointer",
  }

  const cols = "100px 120px 1.4fr 1.8fr 100px 110px 90px 70px 120px 140px"
  const headers = ["Severity", "Type", "File", "Description", "Tool", "Reporter", "Session", "Age", "Status", "Actions"]

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
        <select value={sortBy} onChange={e => setSortBy(e.target.value as "newest" | "severity")} style={selectStyle}>
          <option value="newest">Sort: Newest first</option>
          <option value="severity">Sort: Severity</option>
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
          const reporter = f.reporter_email ? f.reporter_email.split("@")[0] : "—"
          const transitions = STATUS_TRANSITIONS[f.status] ?? []
          const busy = !!updating[f.id]
          const fixing = !!triggering[f.id]
          const canFix = (f.status === "open" || f.status === "triaging") && !!f.repo_full_name

          return (
            <div
              key={f.id}
              style={{
                display: "grid", gridTemplateColumns: cols, gap: 12, padding: "12px 20px",
                borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none",
                alignItems: "center",
                opacity: busy ? 0.6 : 1,
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
              onMouseLeave={e => (e.currentTarget.style.background = "")}
            >
              <SeverityPill severity={f.severity} />
              <div style={{ fontSize: 12.5, color: "var(--text-2)", fontWeight: 500 }}>{f.type || "—"}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filePart}</div>
              <div style={{ fontSize: 12.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.description}>
                {f.description.length > 72 ? f.description.slice(0, 69) + "…" : f.description}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>{f.tool || "—"}</div>
              <div className="mono" title={f.reporter_email ?? undefined} style={{ fontSize: 11.5, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{reporter}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{session}</div>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>{timeAgo(f.created_at)}</div>
              <StatusBadge status={f.status} />
              {/* Inline actions */}
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {transitions.map(t => (
                  <button
                    key={t.next}
                    disabled={busy || fixing}
                    onClick={() => updateStatus(f.id, t.next)}
                    style={{
                      fontSize: 10.5, fontWeight: 600, padding: "3px 8px", borderRadius: 6, cursor: (busy || fixing) ? "wait" : "pointer",
                      border: `1px solid ${t.tone === "ok" ? "var(--ok-bd)" : t.tone === "warn" ? "var(--warn-bd)" : "var(--err-bd)"}`,
                      background: t.tone === "ok" ? "var(--ok-bg)" : t.tone === "warn" ? "var(--warn-bg)" : "var(--err-bg)",
                      color: t.tone === "ok" ? "var(--ok)" : t.tone === "warn" ? "var(--warn)" : "var(--err)",
                    }}
                  >
                    {t.label}
                  </button>
                ))}
                {canFix && (
                  <button
                    disabled={fixing || busy}
                    onClick={() => triggerFix(f.id)}
                    style={{
                      fontSize: 10.5, fontWeight: 600, padding: "3px 8px", borderRadius: 6,
                      cursor: (fixing || busy) ? "wait" : "pointer",
                      border: "1px solid var(--accent-bd, var(--border-2))",
                      background: "var(--accent-bg, var(--surface-2))",
                      color: "var(--accent-text)",
                    }}
                  >
                    {fixing ? "…" : "Run fix"}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </SecureShell>
  )
}
