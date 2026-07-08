"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"

interface FrameworkRow {
  framework: string
  controls: { control: string; rules: number; events_30d: number }[]
  rule_count: number
  events_30d: number
}

interface FrameworksOut {
  installed: FrameworkRow[]
  bonus: FrameworkRow[]
}

interface NarrativeOut {
  paragraph: string
}

interface RecentEventOut {
  id: string
  ts: string
  decision: string
  rule_id: string | null
  ai_tool: string
  tool_call: string
  user_email: string | null
  input_summary: string | null
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
}
function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
}

function todayIso() { return new Date().toISOString().slice(0, 10) }
function isoMonthsAgo(months: number) {
  const d = new Date()
  d.setMonth(d.getMonth() - months)
  return d.toISOString().slice(0, 10)
}

export default function Soc2ReportPage() {
  return <AppShell><Soc2Report /></AppShell>
}

function Soc2Report() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null

  const [from, setFrom] = useState<string>(isoMonthsAgo(1))
  const [to, setTo] = useState<string>(todayIso())
  const [narrative, setNarrative] = useState<NarrativeOut | null>(null)
  const [frameworks, setFrameworks] = useState<FrameworksOut | null>(null)
  const [events, setEvents] = useState<RecentEventOut[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const token = getToken ? await getToken() : null
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const fromIso = `${from}T00:00:00Z`
      const toIso = `${to}T23:59:59Z`

      const [nRes, fRes, eRes] = await Promise.all([
        fetch(`${base}/governance/narrative?workspace_id=${workspaceId}&period=month`, { headers }),
        fetch(`${base}/governance/frameworks?workspace_id=${workspaceId}`, { headers }),
        fetch(`${base}/governance/events/recent?workspace_id=${workspaceId}&limit=1000&from_dt=${encodeURIComponent(fromIso)}&to_dt=${encodeURIComponent(toIso)}`, { headers }),
      ])
      if (nRes.ok) setNarrative(await nRes.json())
      if (fRes.ok) setFrameworks(await fRes.json())
      if (eRes.ok) setEvents(await eRes.json())
    } finally {
      setLoading(false)
    }
  }, [workspaceId, getToken, from, to])

  useEffect(() => { load() }, [load])

  const soc2 = (frameworks?.installed ?? []).concat(frameworks?.bonus ?? []).find(f => f.framework.toUpperCase().startsWith("SOC2"))

  const blocked = events.filter(e => e.decision === "blocked").length
  const warned = events.filter(e => e.decision === "warned").length
  const total = events.length

  return (
    <>
      {/* Print-friendly CSS — applies only in print preview / PDF render */}
      <style>{`
        @page { size: Letter; margin: 0.6in; }
        @media print {
          .no-print { display: none !important; }
          body { background: #fff; }
          table { page-break-inside: auto; }
          tr { page-break-inside: avoid; page-break-after: auto; }
          h1, h2 { page-break-after: avoid; }
        }
        .report-shell { max-width: 8.5in; margin: 0 auto; padding: 24px; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; color: #111; background: #fff; }
        .report-shell h1 { font-size: 28px; font-weight: 700; margin: 0 0 6px; letter-spacing: -0.01em; }
        .report-shell h2 { font-size: 16px; font-weight: 600; margin: 24px 0 8px; border-bottom: 1px solid #e5e5e5; padding-bottom: 6px; }
        .report-shell .meta { font-size: 12px; color: #555; margin-bottom: 24px; }
        .report-shell .summary { font-size: 13.5px; line-height: 1.65; color: #222; padding: 14px 16px; border: 1px solid #e5e5e5; border-radius: 6px; background: #fafafa; }
        .report-shell table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 6px; }
        .report-shell th, .report-shell td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #ececec; vertical-align: top; }
        .report-shell th { font-weight: 600; background: #f5f5f5; }
        .report-shell .decision { font-weight: 600; text-transform: uppercase; font-size: 10px; }
        .report-shell .decision.blocked { color: var(--err); }
        .report-shell .decision.warned  { color: var(--warn); }
        .report-shell .decision.allowed { color: var(--ok); }
        .report-shell .decision.audited { color: var(--info); }
        .report-shell .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 10px 0 18px; }
        .report-shell .kpi { padding: 12px 14px; border: 1px solid #e5e5e5; border-radius: 6px; }
        .report-shell .kpi-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #777; }
        .report-shell .kpi-value { font-size: 22px; font-weight: 700; margin-top: 2px; }
      `}</style>

      <div className="no-print" style={{ display: "flex", gap: 10, padding: "12px 24px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)", alignItems: "center" }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>From <input type="date" value={from} onChange={e => setFrom(e.target.value)} style={{ marginLeft: 6, fontSize: 12 }} /></label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>To <input type="date" value={to} onChange={e => setTo(e.target.value)} style={{ marginLeft: 6, fontSize: 12 }} /></label>
        <button onClick={() => window.print()} className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }}>
          Print / Save as PDF
        </button>
      </div>

      <div className="report-shell">
        <h1>SOC 2 Compliance Report</h1>
        <div className="meta">
          {activeWorkspace?.name ?? "Workspace"} · {fmtDate(`${from}T00:00:00Z`)} – {fmtDate(`${to}T23:59:59Z`)} · Generated {fmtDate(new Date().toISOString())}
        </div>

        <h2>Executive summary</h2>
        <div className="summary">
          {loading ? "Loading…" : (narrative?.paragraph ?? "No activity in this period.")}
        </div>

        <div className="kpis">
          <div className="kpi"><div className="kpi-label">Events screened</div><div className="kpi-value">{total.toLocaleString()}</div></div>
          <div className="kpi"><div className="kpi-label">Blocked</div><div className="kpi-value" style={{ color: "var(--err)" }}>{blocked.toLocaleString()}</div></div>
          <div className="kpi"><div className="kpi-label">Warned</div><div className="kpi-value" style={{ color: "var(--warn)" }}>{warned.toLocaleString()}</div></div>
        </div>

        <h2>SOC 2 control coverage</h2>
        {soc2 ? (
          <table>
            <thead><tr><th>Control</th><th>Rules</th><th>Events (30d)</th></tr></thead>
            <tbody>
              {soc2.controls.length === 0 ? (
                <tr><td colSpan={3} style={{ color: "#777" }}>{soc2.rule_count} rule(s) tagged SOC 2, no control breakdown.</td></tr>
              ) : (
                soc2.controls.map(c => (
                  <tr key={c.control}>
                    <td>{c.control}</td>
                    <td>{c.rules}</td>
                    <td>{c.events_30d}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        ) : (
          <p style={{ fontSize: 12, color: "#777" }}>No SOC 2 pack installed. Install a pack with SOC 2-tagged rules from the marketplace to populate this section.</p>
        )}

        <h2>Event log</h2>
        {events.length === 0 ? (
          <p style={{ fontSize: 12, color: "#777" }}>No events in the selected range.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: "16%" }}>Date</th>
                <th style={{ width: "18%" }}>Developer</th>
                <th style={{ width: "12%" }}>Tool</th>
                <th style={{ width: "10%" }}>Decision</th>
                <th style={{ width: "20%" }}>Rule</th>
                <th>Call</th>
              </tr>
            </thead>
            <tbody>
              {events.map(e => (
                <tr key={e.id}>
                  <td>{fmtDateTime(e.ts)}</td>
                  <td>{e.user_email ?? "—"}</td>
                  <td>{e.ai_tool}</td>
                  <td><span className={`decision ${e.decision}`}>{e.decision}</span></td>
                  <td>{e.rule_id ?? "—"}</td>
                  <td style={{ wordBreak: "break-word" }}>{e.tool_call}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div style={{ marginTop: 32, paddingTop: 12, borderTop: "1px solid #e5e5e5", fontSize: 10, color: "#777" }}>
          Report generated by Conduct AI Guard · conductai.ai · Data sourced from guard_audit_events.
        </div>
      </div>
    </>
  )
}
