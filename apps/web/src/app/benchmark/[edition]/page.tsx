"use client"

import { useEffect, useState, useCallback } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import {
  getEdition,
  playbookDisplayName,
  type BenchmarkEdition,
} from "@/lib/benchmark-editions"

// ─── Data shapes ─────────────────────────────────────────────────────────────

interface GradeCounts { A: number; B: number; C: number; D: number; F: number }

interface EvalSummary {
  total_playbooks: number
  passing?: number
  failing?: number
  average_pct: number
  grade_counts?: GradeCounts
  generated_at?: string
}

interface PlaybookRow {
  slug: string
  grade: string
  pct: number
  total_score: number
  total_max: number
  structural_score: number
  quality_score: number
  failing_criteria?: number
}

interface EditionManifest {
  edition: string
  published_at: string
  model: string
  summary: EvalSummary
  playbooks: Array<{
    slug: string
    grade: string
    pct: number
    structural_score: number
    quality_score: number
    total_score: number
    total_max: number
  }>
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
const GRADE_SCALE: [string, string][] = [["A","90–100%"],["B","75–89%"],["C","60–74%"],["D","40–59%"],["F","0–39%"]]

function gradeC(g: string) { return GRADE_C[g] ?? "var(--text-3)" }
function gradeBg(g: string) { return GRADE_BG[g] ?? "var(--surface-3)" }

function fmt(date: string) {
  try { return new Date(date).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) }
  catch { return date }
}

// ─── Shared grade components ──────────────────────────────────────────────────

function GradeBadge({ grade }: { grade: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, borderRadius: 8, fontSize: 13, fontWeight: 800, background: gradeBg(grade), color: gradeC(grade) }}>
      {grade}
    </span>
  )
}

function PctBar({ pct, grade, w = 72 }: { pct: number; grade: string; w?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <div style={{ width: w, height: 6, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, height: "100%", borderRadius: 6, background: gradeC(grade) }} />
      </div>
      <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", width: 32, textAlign: "right" }}>{Math.round(pct)}%</span>
    </div>
  )
}

function GradeStrip({ counts, height = 10 }: { counts: GradeCounts; height?: number }) {
  const total = GRADE_ORDER.reduce((s, g) => s + (counts[g] ?? 0), 0) || 1
  return (
    <div style={{ display: "flex", height, borderRadius: 20, overflow: "hidden", gap: 2 }}>
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

function BenchmarkContent({
  editionSlug,
  getToken,
}: {
  editionSlug: string
  getToken: (() => Promise<string | null>) | null
}) {
  const edition = getEdition(editionSlug)

  const [summary, setSummary] = useState<EvalSummary | null>(null)
  const [playbooks, setPlaybooks] = useState<PlaybookRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!edition) return
    const ed = edition
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      const base = process.env.NEXT_PUBLIC_API_URL
      const headers: Record<string, string> = {}
      try {
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
        const workspaceId = getCookie("delegator_project_id")
        if (workspaceId) headers["X-Workspace-Id"] = workspaceId

        if (ed.apiEditionSlug) {
          const manifestRes = await fetch(`${base}/eval/benchmark/editions/${ed.apiEditionSlug}`, { headers })
          if (cancelled) return
          if (manifestRes.ok) {
            const manifest: EditionManifest = await manifestRes.json()
            setSummary(manifest.summary)
            setPlaybooks(manifest.playbooks.map(p => ({ ...p, failing_criteria: undefined })))
            return
          }
          if (manifestRes.status !== 404) {
            const status = manifestRes.status
            setError(status === 401 ? "Not authorised." : status === 403 ? "Forbidden." : `Benchmark endpoint returned ${status}.`)
            return
          }
        }

        const [summaryRes, playbooksRes] = await Promise.all([
          fetch(`${base}/eval/summary`, { headers }),
          fetch(`${base}/eval/playbooks`, { headers }),
        ])
        if (cancelled) return
        if (!summaryRes.ok && !playbooksRes.ok) {
          setError(`Both eval endpoints returned ${summaryRes.status}.`)
          return
        }
        if (summaryRes.ok) setSummary(await summaryRes.json())
        if (playbooksRes.ok) setPlaybooks(await playbooksRes.json())
      } catch {
        if (!cancelled) setError("Network error — could not reach the API.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editionSlug])

  if (!edition) {
    return (
      <AppShell>
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "30px 34px 80px" }}>
          <div className="card" style={{ padding: "32px", textAlign: "center" }}>
            <p style={{ fontWeight: 600, fontSize: 14 }}>Edition not found</p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>No benchmark edition exists for <code className="mono">{editionSlug}</code>.</p>
            <Link href="/benchmark" style={{ fontSize: 12, color: "var(--accent)", marginTop: 12, display: "inline-block" }}>View latest edition →</Link>
          </div>
        </div>
      </AppShell>
    )
  }

  const sorted = [...playbooks].sort((a, b) => {
    const go: Record<string, number> = { A: 0, B: 1, C: 2, D: 3, F: 4 }
    const gd = (go[a.grade] ?? 5) - (go[b.grade] ?? 5)
    return gd !== 0 ? gd : b.pct - a.pct
  })

  const counts: GradeCounts = summary?.grade_counts ?? { A: 0, B: 0, C: 0, D: 0, F: 0 }

  return (
    <AppShell>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "30px 34px 80px" }}>

        {/* Edition header */}
        <div style={{ marginBottom: 26 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
            <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--accent-text)", background: "var(--accent-weak)", border: "1px solid var(--accent-ring)", borderRadius: 20, padding: "2px 10px" }}>{edition.label}</span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{edition.period}</span>
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14, fontSize: 12, color: "var(--text-muted)" }}>
              {edition.prevEditionSlug
                ? <Link href={`/benchmark/${edition.prevEditionSlug}`} style={{ color: "var(--text-3)", textDecoration: "none" }}>← Previous</Link>
                : <span style={{ opacity: 0.4 }}>← Previous</span>}
              {edition.nextEditionSlug
                ? <Link href={`/benchmark/${edition.nextEditionSlug}`} style={{ color: "var(--text-3)", textDecoration: "none" }}>Next →</Link>
                : <span style={{ opacity: 0.4 }}>Next →</span>}
              <ShareButton />
            </div>
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-.025em", margin: "4px 0 0" }}>Conduct AI Benchmark</h1>
          <p className="page-sub" style={{ marginTop: 6 }}>
            {edition.totalPlaybooks} playbooks · {edition.modelLabel}{summary && ` · published ${fmt(edition.publishedAt)}`}
          </p>
        </div>

        {loading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "40px 0" }}>Loading…</div>
        ) : error ? (
          <div className="card" style={{ padding: "16px 18px", color: "var(--err)", fontSize: 13 }}>{error}</div>
        ) : (
          <>
            {/* Grade distribution */}
            <div className="card" style={{ padding: "20px 22px", marginBottom: 28 }}>
              <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 16 }}>
                <div>
                  <div className="eyebrow" style={{ marginBottom: 3 }}>Grade distribution</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{edition.totalPlaybooks} playbooks scored</div>
                </div>
                <div style={{ marginLeft: "auto", textAlign: "right" }}>
                  <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-.02em" }}>{summary ? `${summary.average_pct.toFixed(0)}%` : "—"}</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>average score</div>
                </div>
              </div>
              <div style={{ marginBottom: 14 }}><GradeStrip counts={counts} height={10} /></div>
              <GradeLegend counts={counts} />
            </div>

            {/* Leaderboard */}
            <div className="eyebrow" style={{ marginBottom: 11 }}>Leaderboard</div>
            <div className="card" style={{ overflow: "hidden", marginBottom: 28 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                <span className="eyebrow" style={{ fontSize: 9.5 }}>Ranked by grade</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10.5, color: "var(--text-2)", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 20, padding: "3px 9px", fontWeight: 600 }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)" }} />{edition.modelLabel}
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "24px 1.8fr 0.6fr 1.1fr 1fr 0.8fr 0.5fr", gap: 12, padding: "9px 18px", borderBottom: "1px solid var(--border)" }}>
                {["#", "Playbook", "Grade", "Score", "Structural", "Quality", "Issues"].map((h, i) => (
                  <div key={i} className="eyebrow" style={{ fontSize: 9.5, textAlign: i >= 4 ? "right" : "left" }}>{h}</div>
                ))}
              </div>
              {sorted.length === 0 ? (
                <div style={{ padding: "32px 18px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>No playbook scores available yet.</div>
              ) : (
                sorted.map((p, i) => {
                  const structPct = p.total_max > 0 ? Math.min((p.structural_score / p.total_max) * 100, 100) : 0
                  const qualPct = p.total_max > 0 ? Math.min((p.quality_score / p.total_max) * 100, 100) : 0
                  return (
                    <div key={p.slug} style={{ display: "grid", gridTemplateColumns: "24px 1.8fr 0.6fr 1.1fr 1fr 0.8fr 0.5fr", gap: 12, padding: "11px 18px", borderBottom: i < sorted.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "")}>
                      <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{i + 1}</div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{playbookDisplayName(p.slug)}</div>
                        <div className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>{p.slug}</div>
                      </div>
                      <div><GradeBadge grade={p.grade} /></div>
                      <div><PctBar pct={p.pct} grade={p.grade} w={72} /></div>
                      <div style={{ textAlign: "right" }}>
                        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)" }}>{p.structural_score}<span style={{ color: "var(--text-muted)" }}> / {p.total_max}</span></div>
                        <div style={{ width: 60, height: 4, borderRadius: 4, background: "var(--surface-3)", overflow: "hidden", marginLeft: "auto", marginTop: 4 }}>
                          <div style={{ width: `${structPct}%`, height: "100%", background: "#60a5fa" }} />
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)" }}>{p.quality_score}<span style={{ color: "var(--text-muted)" }}> pts</span></div>
                        <div style={{ width: 60, height: 4, borderRadius: 4, background: "var(--surface-3)", overflow: "hidden", marginLeft: "auto", marginTop: 4 }}>
                          <div style={{ width: `${qualPct}%`, height: "100%", background: "#a78bfa" }} />
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        {(p.failing_criteria ?? 0) > 0
                          ? <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, color: gradeC(p.grade) }}>
                              <span style={{ width: 6, height: 6, borderRadius: "50%", background: gradeC(p.grade) }} />{p.failing_criteria}
                            </span>
                          : <span style={{ fontSize: 13, color: "var(--ok)" }}>✓</span>
                        }
                      </div>
                    </div>
                  )
                })
              )}
            </div>

            {/* Key findings */}
            {edition.findings.length > 0 && (
              <>
                <div className="eyebrow" style={{ marginBottom: 14 }}>Key findings</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 11, marginBottom: 28 }}>
                  {edition.findings.map((f, i) => (
                    <div key={i} className="card" style={{ padding: "15px 18px", display: "flex", gap: 15 }}>
                      <span className="mono" style={{ fontSize: 11, fontWeight: 800, color: "var(--text-muted)", marginTop: 1 }}>{String(i + 1).padStart(2, "0")}</span>
                      <div>
                        <div style={{ fontWeight: 650, fontSize: 14, marginBottom: 4 }}>{f.headline}</div>
                        <div style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.55 }}>{f.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Methodology */}
            <div className="eyebrow" style={{ marginBottom: 14 }}>Methodology</div>
            <div className="card card-pad" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <div style={{ fontWeight: 650, fontSize: 13.5, marginBottom: 5 }}>Scoring approach</div>
                <p style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.6, margin: 0 }}>
                  Each playbook is scored against a fixed set of structural and quality criteria. Structural criteria check that required fields are present and correctly wired (trigger, brain blocks, output blocks, parameter completeness). Quality criteria assess description completeness, output clarity, and documentation. Every criterion is pass/fail.
                </p>
              </div>
              <div>
                <div style={{ fontWeight: 650, fontSize: 13.5, marginBottom: 8 }}>Grade scale</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {GRADE_SCALE.map(([g, r]) => (
                    <span key={g} style={{ display: "inline-flex", alignItems: "center", gap: 7, borderRadius: 8, padding: "4px 10px", fontSize: 12, fontWeight: 600, background: gradeBg(g), color: gradeC(g) }}>
                      <b style={{ fontWeight: 800 }}>{g}</b><span style={{ opacity: 0.7, fontWeight: 500 }}>{r}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <div style={{ fontWeight: 650, fontSize: 13.5, marginBottom: 5 }}>Reproducibility</div>
                <p style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.6, margin: 0 }}>
                  Structural scores are deterministic and fully reproducible from the playbook YAML. To reproduce any result, run{" "}
                  <code className="mono" style={{ background: "var(--surface-3)", padding: "1px 6px", borderRadius: 4 }}>conduct eval --playbook &lt;slug&gt;</code>
                  {" "}against the same playbook version.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}

// ─── Auth wrapper ─────────────────────────────────────────────────────────────

function BenchmarkWithAuth({ editionSlug }: { editionSlug: string }) {
  const { getToken, isLoaded } = useAuth()
  if (!isLoaded) return null
  return <BenchmarkContent editionSlug={editionSlug} getToken={getToken} />
}

export default function BenchmarkEditionPage() {
  const params = useParams()
  const edition = Array.isArray(params.edition) ? params.edition[0] : (params.edition as string)
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <BenchmarkWithAuth editionSlug={edition} />
  return <BenchmarkContent editionSlug={edition} getToken={null} />
}
