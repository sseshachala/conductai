"use client"

import { useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"

interface ControlStatus { id: string; name: string; status: string; control: string }
interface Evidence {
  grade: string; coverage_pct: number; score: number;
  blocked_24h: number; events_24h: number;
  controls: ControlStatus[]; generated_at: string; workspace_id: string;
}

const GRADE_COLOR: Record<string, string> = {
  A: "var(--ok)", B: "var(--ok)", C: "var(--warn)", D: "var(--warn)", F: "var(--block)",
}
const GRADE_BG: Record<string, string> = {
  A: "var(--ok-bg)", B: "var(--ok-bg)", C: "var(--warn-bg)", D: "var(--warn-bg)", F: "var(--block-bg)",
}
const GRADE_BD: Record<string, string> = {
  A: "var(--ok-bd)", B: "var(--ok-bd)", C: "var(--warn-bd)", D: "var(--warn-bd)", F: "var(--block-bd)",
}
const STATUS_COLOR: Record<string, string> = {
  active: "var(--ok)", partial: "var(--warn)", missing: "var(--block)",
}
const STATUS_BG: Record<string, string> = {
  active: "var(--ok-bg)", partial: "var(--warn-bg)", missing: "var(--block-bg)",
}
const STATUS_BD: Record<string, string> = {
  active: "var(--ok-bd)", partial: "var(--warn-bd)", missing: "var(--block-bd)",
}

export default function CompliancePage() {
  return <AppShell><GuardShell><ComplianceContent /></GuardShell></AppShell>
}

function ComplianceContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id ?? null
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!wsId) return
    let cancelled = false
    ;(async () => {
      try {
        const token = await getToken()
        const h: Record<string, string> = {}
        if (token) h["Authorization"] = `Bearer ${token}`
        const res = await fetch(`${base}/guard/verify/evidence?workspace_id=${wsId}`, { headers: h })
        if (!res.ok) throw new Error(`Failed to load evidence (${res.status})`)
        const data = await res.json()
        if (!cancelled) setEvidence(data)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load")
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [wsId, base, getToken])

  function downloadEvidence() {
    if (!evidence) return
    const blob = new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url; a.download = "conduct-evidence.json"; a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return <div style={{ padding: "40px 0", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
  if (error || !evidence) return <div style={{ padding: "16px", color: "var(--err)", fontSize: 13 }}>{error ?? "No data"}</div>

  const { grade, coverage_pct, score, blocked_24h, events_24h, controls, generated_at } = evidence
  const gc  = GRADE_COLOR[grade] ?? "var(--text-muted)"
  const gb  = GRADE_BG[grade]   ?? "var(--surface-2)"
  const gbd = GRADE_BD[grade]   ?? "var(--border)"

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Grade + summary */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{
            width: 72, height: 72, borderRadius: 16,
            background: gb, border: `2px solid ${gbd}`,
            display: "grid", placeItems: "center", flexShrink: 0,
          }}>
            <span style={{ fontSize: 36, fontWeight: 800, color: gc, letterSpacing: "-.03em" }}>{grade}</span>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>Governance Grade</div>
            <div style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 10 }}>
              Score {score}/100 · {coverage_pct}% OWASP ASI controls active · {blocked_24h} blocked / {events_24h} events (24h)
            </div>
            <div style={{ height: 6, borderRadius: 4, background: "var(--surface-3)", overflow: "hidden", maxWidth: 360 }}>
              <div style={{ height: "100%", width: `${coverage_pct}%`, background: gc, borderRadius: 4, transition: "width .4s" }} />
            </div>
          </div>
          <button onClick={downloadEvidence} className="btn btn-ghost btn-sm" style={{ flexShrink: 0 }}>
            Download evidence.json
          </button>
        </div>
      </div>

      {/* Controls table */}
      <div className="card" style={{ overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14 }}>
          OWASP Agentic Top 10 — Control Coverage
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "var(--surface-2)" }}>
              {["Control", "Name", "Status", "Conduct enforcement"].map(h => (
                <th key={h} style={{ padding: "8px 16px", textAlign: "left", fontWeight: 600, fontSize: 11.5, color: "var(--text-3)", borderBottom: "1px solid var(--border)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {controls.map((c, i) => {
              const sc  = STATUS_COLOR[c.status] ?? "var(--text-muted)"
              const sb  = STATUS_BG[c.status]   ?? "var(--surface-2)"
              const sbd = STATUS_BD[c.status]   ?? "var(--border)"
              return (
                <tr key={c.id} style={{ borderBottom: i < controls.length - 1 ? "1px solid var(--border)" : "none" }}>
                  <td style={{ padding: "10px 16px", fontWeight: 600, fontFamily: "ui-monospace,monospace", fontSize: 12 }}>{c.id}</td>
                  <td style={{ padding: "10px 16px", color: "var(--text-2)" }}>{c.name}</td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 20, background: sb, color: sc, border: `1px solid ${sbd}` }}>
                      {c.status}
                    </span>
                  </td>
                  <td style={{ padding: "10px 16px", color: "var(--text-3)", fontSize: 12 }}>{c.control}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div style={{ padding: "10px 16px", fontSize: 11, color: "var(--text-muted)", borderTop: "1px solid var(--border)" }}>
          Generated {new Date(generated_at).toLocaleString()}
        </div>
      </div>
    </div>
  )
}
