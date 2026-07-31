"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

interface ControlStatus { id: string; name: string; status: string; control: string }
interface Evidence {
  grade: string; coverage_pct: number; score: number;
  blocked_24h: number; events_24h: number;
  controls: ControlStatus[]; generated_at: string; workspace_id: string;
}

interface TestResult {
  asi: string; name: string; tool: string
  expected: string; actual: string; verdict: string; matched_rule: string | null
}
interface VerifyRunOut {
  run_id: string; score: number; grade: string
  passed_tests: number; total_tests: number
  results: TestResult[]; created_at: string
}
interface VerifyRunSummary {
  run_id: string; score: number; grade: string
  passed_tests: number; total_tests: number; created_at: string
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

const VERDICT_COLOR: Record<string, string> = {
  held: "var(--ok)", bypassed: "var(--block)", not_tested: "var(--warn)",
}
const VERDICT_BG: Record<string, string> = {
  held: "var(--ok-bg)", bypassed: "var(--block-bg)", not_tested: "var(--warn-bg)",
}
const VERDICT_BD: Record<string, string> = {
  held: "var(--ok-bd)", bypassed: "var(--block-bd)", not_tested: "var(--warn-bd)",
}

export default function CompliancePage() {
  return <AppShell><GuardShell><ComplianceContent /></GuardShell></AppShell>
}

function VerifyRunPanel({ wsId, authFetch }: { wsId: string; authFetch: any }) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<VerifyRunOut | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  async function handleRun() {
    setRunning(true)
    setRunError(null)
    try {
      const res = await guard.verify.run(authFetch, { workspace_id: wsId })
      if (!res.ok) throw new Error(`Verification failed (${res.status})`)
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Verification failed")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontWeight: 650, fontSize: 14 }}>Hook Policy Simulation</span>
        <button
          onClick={handleRun}
          disabled={running}
          className="btn btn-sm"
          style={{ opacity: running ? 0.6 : 1 }}
        >
          {running ? "Running…" : "Run Verification"}
        </button>
      </div>

      {runError && (
        <div style={{ padding: "12px 20px", fontSize: 13, color: "var(--block)" }}>{runError}</div>
      )}

      {!result && !runError && (
        <div style={{ padding: "24px 20px", fontSize: 13, color: "var(--text-muted)", textAlign: "center" }}>
          Simulate 10 representative tool calls against the compiled hook policy. No commands are executed; workspace advisory mode is respected.
        </div>
      )}

      {result && (
        <div>
          <div style={{ padding: "12px 20px", display: "flex", alignItems: "center", gap: 12, borderBottom: "1px solid var(--border)", fontSize: 13 }}>
            <span style={{ color: "var(--text-2)" }}>
              Simulation Score: {result.score}/100 · {result.passed_tests}/{result.total_tests} held
            </span>
            <span style={{ fontWeight: 600, color: "var(--text-2)" }}>· Grade</span>
            <span style={{
              fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 20,
              background: GRADE_BG[result.grade] ?? "var(--surface-2)",
              color: GRADE_COLOR[result.grade] ?? "var(--text-muted)",
              border: `1px solid ${GRADE_BD[result.grade] ?? "var(--border)"}`,
            }}>
              {result.grade}
            </span>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                {["ASI", "Test", "Expected", "Actual", "Verdict"].map(h => (
                  <th key={h} style={{ padding: "8px 16px", textAlign: "left", fontWeight: 600, fontSize: 11.5, color: "var(--text-3)", borderBottom: "1px solid var(--border)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.results.map((r, i) => {
                const vc  = VERDICT_COLOR[r.verdict] ?? "var(--text-muted)"
                const vb  = VERDICT_BG[r.verdict]   ?? "var(--surface-2)"
                const vbd = VERDICT_BD[r.verdict]   ?? "var(--border)"
                return (
                  <tr key={i} style={{ borderBottom: i < result.results.length - 1 ? "1px solid var(--border)" : "none" }}>
                    <td style={{ padding: "10px 16px", fontWeight: 600, fontFamily: "ui-monospace,monospace", fontSize: 12 }}>{r.asi}</td>
                    <td style={{ padding: "10px 16px", color: "var(--text-2)" }}>
                      <div>{r.name}</div>
                      {r.matched_rule && (
                        <div style={{ fontSize: 11, fontFamily: "ui-monospace,monospace", color: "var(--text-muted)", marginTop: 2 }}>{r.matched_rule}</div>
                      )}
                    </td>
                    <td style={{ padding: "10px 16px", color: "var(--text-3)", fontSize: 12 }}>{r.expected}</td>
                    <td style={{ padding: "10px 16px", color: "var(--text-3)", fontSize: 12 }}>{r.actual}</td>
                    <td style={{ padding: "10px 16px" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 20, background: vb, color: vc, border: `1px solid ${vbd}` }}>
                        {r.verdict}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ScoreHistory({ wsId, authFetch }: { wsId: string; authFetch: any }) {
  const [runs, setRuns] = useState<VerifyRunSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!wsId) return
    let cancelled = false
    ;(async () => {
      try {
        const data: any = await guard.verify.history(authFetch, { workspace_id: wsId, limit: "30" })
        if (!cancelled) setRuns(Array.isArray(data) ? data : (data?.runs ?? []))
      } catch {
        // silently leave runs empty
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [wsId, authFetch])

  const recent = runs.slice(0, 10)

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14 }}>
        Verification History
      </div>

      {loading && (
        <div style={{ padding: "24px 20px", fontSize: 13, color: "var(--text-muted)", textAlign: "center" }}>Loading…</div>
      )}

      {!loading && runs.length === 0 && (
        <div style={{ padding: "24px 20px", fontSize: 13, color: "var(--text-muted)", textAlign: "center" }}>No verification runs yet</div>
      )}

      {!loading && runs.length > 0 && (
        <div>
          {/* Mini bar chart */}
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 48, overflow: "hidden" }}>
              {runs.map((r, i) => {
                const barHeight = Math.max(4, Math.round((r.score / 100) * 48))
                const barColor = GRADE_COLOR[r.grade] ?? "var(--text-muted)"
                const dateStr = new Date(r.created_at).toLocaleDateString()
                return (
                  <div
                    key={r.run_id ?? i}
                    title={`${r.grade} (${r.score}) — ${dateStr}`}
                    style={{
                      width: 8,
                      height: barHeight,
                      background: barColor,
                      borderRadius: 2,
                      flexShrink: 0,
                      cursor: "default",
                    }}
                  />
                )
              })}
            </div>
          </div>

          {/* Last 10 runs table */}
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--surface-2)" }}>
                {["Date", "Grade", "Score", "Passed/Total"].map(h => (
                  <th key={h} style={{ padding: "8px 16px", textAlign: "left", fontWeight: 600, fontSize: 11.5, color: "var(--text-3)", borderBottom: "1px solid var(--border)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.map((r, i) => {
                const gc  = GRADE_COLOR[r.grade] ?? "var(--text-muted)"
                const gb  = GRADE_BG[r.grade]   ?? "var(--surface-2)"
                const gbd = GRADE_BD[r.grade]   ?? "var(--border)"
                return (
                  <tr key={r.run_id ?? i} style={{ borderBottom: i < recent.length - 1 ? "1px solid var(--border)" : "none" }}>
                    <td style={{ padding: "10px 16px", color: "var(--text-2)", fontSize: 12 }}>
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td style={{ padding: "10px 16px" }}>
                      <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 20, background: gb, color: gc, border: `1px solid ${gbd}` }}>
                        {r.grade}
                      </span>
                    </td>
                    <td style={{ padding: "10px 16px", color: "var(--text-2)", fontSize: 12 }}>{r.score}/100</td>
                    <td style={{ padding: "10px 16px", color: "var(--text-3)", fontSize: 12 }}>{r.passed_tests}/{r.total_tests}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ComplianceContent() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id ?? null
  const router = useRouter()
  const { permissions, loading: roleLoading } = useGuardRole()
  useEffect(() => {
    if (!roleLoading && !permissions.canEditPolicies) router.replace("/theguard")
  }, [roleLoading, permissions.canEditPolicies, router])

  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!wsId) return
    let cancelled = false
    ;(async () => {
      try {
        const data = await guard.verify.evidence(authFetch, { workspace_id: wsId })
        if (!cancelled) setEvidence(data)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load")
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [wsId, authFetch])

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

      {wsId && (
        <>
          <VerifyRunPanel wsId={wsId} authFetch={authFetch} />
          <ScoreHistory wsId={wsId} authFetch={authFetch} />
        </>
      )}
    </div>
  )
}
