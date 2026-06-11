"use client"

import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

// ─── Data shapes ─────────────────────────────────────────────────────────────

interface GradeCounts {
  A: number
  B: number
  C: number
  D: number
  F: number
}

interface TopPlaybook {
  slug: string
  grade: string
  pct: number
}

interface EvalSummary {
  grade_counts: GradeCounts
  top_playbooks: TopPlaybook[]
}

interface PlaybookEval {
  slug: string
  grade: string
  pct: number
  failing_criteria: number
  total_criteria?: number
  total_max: number
  total_score: number
  structural_score?: number
  quality_score?: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

const GRADE_ORDER = ["A", "B", "C", "D", "F"] as const
const GRADE_C: Record<string, string> = { A: "#059669", B: "#2563eb", C: "#d97706", D: "#ea580c", F: "#dc2626" }
const GRADE_BG: Record<string, string> = { A: "#ecfdf5", B: "#eff6ff", C: "#fffbeb", D: "#fff7ed", F: "#fef2f2" }

function gradeC(g: string) { return GRADE_C[g] ?? "var(--text-3)" }
function gradeBg(g: string) { return GRADE_BG[g] ?? "var(--surface-3)" }

// ─── Shared grade components ──────────────────────────────────────────────────

function GradeBadge({ grade, lg }: { grade: string; lg?: boolean }) {
  const s = lg ? 46 : 28
  const f = lg ? 20 : 13
  return (
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: s, height: s, borderRadius: lg ? 12 : 8, fontSize: f, fontWeight: 800, background: gradeBg(grade), color: gradeC(grade) }}>
      {grade}
    </span>
  )
}

function PctBar({ pct }: { pct: number }) {
  const c = pct >= 90 ? "var(--ok)" : pct >= 75 ? "var(--info)" : pct >= 60 ? "var(--warn)" : pct >= 40 ? "#ea580c" : "var(--err)"
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <div style={{ width: 96, height: 6, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", borderRadius: 6, background: c }} />
      </div>
      <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", width: 32, textAlign: "right" }}>{Math.round(pct)}%</span>
    </div>
  )
}

function GradeStrip({ counts }: { counts: GradeCounts }) {
  const total = GRADE_ORDER.reduce((s, g) => s + (counts[g] ?? 0), 0) || 1
  return (
    <div style={{ display: "flex", height: 12, borderRadius: 20, overflow: "hidden", gap: 2 }}>
      {GRADE_ORDER.map(g => {
        const pct = ((counts[g] ?? 0) / total) * 100
        return pct > 0 ? <div key={g} title={`${g}: ${counts[g]}`} style={{ width: `${pct}%`, background: gradeC(g) }} /> : null
      })}
    </div>
  )
}

function GradeLegend({ counts }: { counts: GradeCounts }) {
  return (
    <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
      {GRADE_ORDER.map(g => (
        <span key={g} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--text-3)" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: gradeC(g) }} />
          <b style={{ color: "var(--text-2)" }}>{g}</b> {counts[g] ?? 0}
        </span>
      ))}
    </div>
  )
}

function ShareButton() {
  const [copied, setCopied] = useState(false)
  const copy = useCallback(() => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [])
  return (
    <button onClick={copy} className="btn btn-ghost" style={{ fontSize: 12 }}>
      <span style={{ transform: "rotate(-45deg)", display: "inline-block" }}>↗</span>
      {copied ? "Copied" : "Share"}
    </button>
  )
}

// ─── Page content ─────────────────────────────────────────────────────────────

function EvalContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [playbooks, setPlaybooks] = useState<PlaybookEval[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      const headers: Record<string, string> = {}
      try {
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
        const workspaceId = getCookie("delegator_project_id")
        if (workspaceId) headers["X-Workspace-Id"] = workspaceId

        const playbooksRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/eval/playbooks`, { headers })

        if (cancelled) return

        if (!playbooksRes.ok) {
          const status = playbooksRes.status
          setError(
            status === 401 ? "Not authorised — check your session." :
            status === 403 ? "Forbidden — workspace role may be insufficient." :
            status === 500 ? "The eval runner returned an error (500). Check the API logs." :
            `Eval endpoint returned ${status}.`
          )
          return
        }

        setPlaybooks(await playbooksRes.json())
      } catch {
        if (!cancelled) setError("Network error — could not reach the API.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const sorted = [...playbooks].sort((a, b) => {
    const order: Record<string, number> = { A: 0, B: 1, C: 2, D: 3, F: 4 }
    return (order[a.grade] ?? 5) - (order[b.grade] ?? 5)
  })

  const counts: GradeCounts = sorted.reduce(
    (acc, p) => {
      const g = p.grade as keyof GradeCounts
      if (g in acc) acc[g] += 1
      return acc
    },
    { A: 0, B: 0, C: 0, D: 0, F: 0 }
  )
  const total = GRADE_ORDER.reduce((s, g) => s + (counts[g] ?? 0), 0)
  const overall = counts.A / (total || 1) >= 0.5 ? "A" : "B"

  const top = sorted.slice(0, 6)

  return (
    <AppShell>
      <div style={{ maxWidth: 920, margin: "0 auto", padding: "30px 34px 80px" }}>
        {/* Header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-start" }}>
          <div>
            <h1 className="page-title">Quality</h1>
            <p className="page-sub">Playbook quality grades and failing criteria.</p>
          </div>
          <div style={{ marginLeft: "auto" }}><ShareButton /></div>
        </div>

        {loading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "40px 0" }}>Loading…</div>
        ) : error ? (
          <div className="card" style={{ padding: "16px 18px", color: "var(--err)", fontSize: 13 }}>{error}</div>
        ) : (
          <>
            {/* Distribution card */}
            <div className="card" style={{ padding: "20px 22px", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 16 }}>
                <div>
                  <div className="eyebrow" style={{ marginBottom: 3 }}>Overall quality</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{total} playbooks evaluated</div>
                </div>
                <div style={{ marginLeft: "auto" }}><GradeBadge grade={overall} lg /></div>
              </div>
              <div style={{ marginBottom: 14 }}><GradeStrip counts={counts} /></div>
              <GradeLegend counts={counts} />
            </div>

            {/* Top rated */}
            {top.length > 0 && (
              <>
                <div className="eyebrow" style={{ marginBottom: 10 }}>Top rated</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 26 }}>
                  {top.map(p => (
                    <Link key={p.slug} href={`/eval/${encodeURIComponent(p.slug)}`}
                      style={{ display: "flex", alignItems: "center", gap: 8, borderRadius: 9, padding: "6px 11px", background: gradeBg(p.grade), textDecoration: "none" }}>
                      <span style={{ fontSize: 12.5, fontWeight: 800, color: gradeC(p.grade) }}>{p.grade}</span>
                      <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>{p.slug}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{p.pct}%</span>
                    </Link>
                  ))}
                </div>
              </>
            )}

            {/* Quality table */}
            <div style={{ display: "flex", alignItems: "center", marginBottom: 11 }}>
              <span className="eyebrow">Playbook quality</span>
              <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>{sorted.length} playbooks</span>
            </div>
            <div className="card" style={{ overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1.6fr 0.6fr 1.2fr 1fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                {["Playbook", "Grade", "Pass rate", "Failing criteria"].map((h, i) => (
                  <div key={i} className="eyebrow" style={{ fontSize: 10, textAlign: i === 3 ? "right" : "left" }}>{h}</div>
                ))}
              </div>
              {sorted.length === 0 ? (
                <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>No published playbook evals available yet.</div>
              ) : (
                sorted.map(p => (
                  <Link key={p.slug} href={`/eval/${encodeURIComponent(p.slug)}`}
                    style={{ display: "grid", gridTemplateColumns: "1.6fr 0.6fr 1.2fr 1fr", gap: 14, padding: "11px 20px", borderBottom: "1px solid var(--border)", alignItems: "center", textDecoration: "none" }}
                    onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = "var(--surface-2)")}
                    onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = "")}>
                    <div>
                      <span className="mono" style={{ fontSize: 12, color: "var(--text-2)", background: "var(--surface-3)", padding: "2px 7px", borderRadius: 5 }}>{p.slug}</span>
                    </div>
                    <div><GradeBadge grade={p.grade} /></div>
                    <div><PctBar pct={p.pct} /></div>
                    <div style={{ textAlign: "right" }}>
                      {p.failing_criteria > 0
                        ? <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: "var(--err)" }}>
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--err)" }} />
                            {p.failing_criteria}
                            {p.total_criteria != null && <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> / {p.total_criteria}</span>}
                          </span>
                        : <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)" }}>All passing</span>
                      }
                    </div>
                  </Link>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}

// ─── Auth wrapper ─────────────────────────────────────────────────────────────

function EvalWithAuth() {
  const { getToken, isLoaded } = useAuth()
  if (!isLoaded) return null
  return <EvalContent getToken={getToken} />
}

export default function EvalPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <EvalWithAuth />
  return <EvalContent getToken={null} />
}
