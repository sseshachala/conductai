"use client"

import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import {
  getEdition,
  playbookDisplayName,
} from "@/lib/benchmark-editions"

// ─── Data shapes ─────────────────────────────────────────────────────────────

interface BaselinePlaybook {
  slug: string
  grade: string
  pct: number
  structural_score: number
  quality_score: number
  total_score: number
  total_max: number
}

interface EditionManifest {
  edition: string
  published_at: string
  model: string
  summary: { total_playbooks: number; average_pct: number }
  playbooks: BaselinePlaybook[]
}

interface ScenarioItem {
  id: string
  label: string
  tags: string[]
  expected_outcome_type: string
  expected_artifact_keys: string[]
  expected_should_review: boolean | null
  expected_should_scan: boolean | null
}

interface ScenarioSet {
  slug: string
  description: string
  scenario_count: number
  positive_count: number
  negative_count: number
  scenarios: ScenarioItem[]
}

interface CriterionResult {
  name: string
  passed: boolean
  points_earned: number
  points_possible: number
  detail: string
}

interface PlaybookLiveDetail {
  slug: string
  grade: string
  pct: number
  total_score: number
  total_max: number
  structural_score: number
  structural_max: number
  quality_score: number
  quality_max: number
  total_criteria?: number
  criteria: CriterionResult[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

const GRADE_BG: Record<string, string> = {
  A: "var(--ok-bg)",
  B: "#eff6ff",
  C: "var(--warn-bg)",
  D: "#fff7ed",
  F: "var(--err-bg)",
}

const GRADE_C: Record<string, string> = {
  A: "var(--ok)",
  B: "#1d4ed8",
  C: "var(--warn)",
  D: "#c2410c",
  F: "var(--err)",
}

const GRADE_BORDER: Record<string, string> = {
  A: "#6ee7b7",
  B: "#bfdbfe",
  C: "#fde68a",
  D: "#fed7aa",
  F: "#fecaca",
}

const GRADE_BAR: Record<string, string> = {
  A: "var(--ok)",
  B: "#60a5fa",
  C: "var(--warn)",
  D: "#fb923c",
  F: "var(--err)",
}

function gradeStyles(grade: string) {
  return {
    bg: GRADE_BG[grade] ?? "var(--surface-3)",
    text: GRADE_C[grade] ?? "var(--text-3)",
    bar: GRADE_BAR[grade] ?? "var(--border)",
    border: GRADE_BORDER[grade] ?? "var(--border)",
  }
}

function fmt(iso: string) {
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) }
  catch { return iso }
}

// ─── Score card ───────────────────────────────────────────────────────────────

function ScoreCard({
  baseline,
  editionLabel,
  model,
  publishedAt,
}: {
  baseline: BaselinePlaybook
  editionLabel: string
  model: string
  publishedAt: string
}) {
  const s = gradeStyles(baseline.grade)
  const structPct = baseline.total_max > 0 ? (baseline.structural_score / baseline.total_max) * 100 : 0
  const qualPct   = baseline.total_max > 0 ? (baseline.quality_score   / baseline.total_max) * 100 : 0

  return (
    <div className="card" style={{ padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 20 }}>
        {/* Grade */}
        <div style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 64,
          height: 64,
          borderRadius: 12,
          fontSize: 30,
          fontWeight: 900,
          background: s.bg,
          color: s.text,
        }}>
          {baseline.grade}
        </div>

        {/* Score and bars */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 24, fontWeight: 700, color: "var(--text)" }}>
              {baseline.pct.toFixed(0)}%
            </span>
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {baseline.total_score} / {baseline.total_max} pts
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {/* Structural bar */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className="eyebrow" style={{ width: 64, flexShrink: 0, color: "var(--text-muted)" }}>
                Structural
              </span>
              <div style={{
                width: 128,
                height: 6,
                borderRadius: 999,
                background: "var(--surface-3)",
                overflow: "hidden",
              }}>
                <div style={{
                  height: "100%",
                  background: "#60a5fa",
                  borderRadius: 999,
                  transition: "width 0.3s ease",
                  width: `${Math.min(structPct, 100)}%`,
                }} />
              </div>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>
                {baseline.structural_score} pts
              </span>
            </div>

            {/* Quality bar (only if non-zero) */}
            {baseline.quality_score > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className="eyebrow" style={{ width: 64, flexShrink: 0, color: "var(--text-muted)" }}>
                  Quality
                </span>
                <div style={{
                  width: 128,
                  height: 6,
                  borderRadius: 999,
                  background: "var(--surface-3)",
                  overflow: "hidden",
                }}>
                  <div style={{
                    height: "100%",
                    background: "#a78bfa",
                    borderRadius: 999,
                    transition: "width 0.3s ease",
                    width: `${Math.min(qualPct, 100)}%`,
                  }} />
                </div>
                <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>
                  {baseline.quality_score} pts
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Edition meta */}
        <div style={{ flexShrink: 0, textAlign: "right" }}>
          <span style={{
            display: "inline-flex",
            alignItems: "center",
            borderRadius: 999,
            padding: "2px 10px",
            fontSize: 10,
            fontWeight: 600,
            border: `1px solid ${s.border}`,
            background: s.bg,
            color: s.text,
          }}>
            {editionLabel}
          </span>
          <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>{fmt(publishedAt)}</p>
          <p className="mono" style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2, opacity: 0.6 }}>{model}</p>
        </div>
      </div>
    </div>
  )
}

// ─── Scenario coverage ────────────────────────────────────────────────────────

function ScenarioCoverage({ scenarios }: { scenarios: ScenarioSet }) {
  const [expanded, setExpanded] = useState(false)

  function tagStyle(tag: string): React.CSSProperties {
    if (tag === "positive") return {
      background: "var(--ok-bg)",
      color: "var(--ok)",
      borderColor: "#6ee7b7",
    }
    if (tag === "negative") return {
      background: "var(--err-bg)",
      color: "var(--err)",
      borderColor: "#fca5a5",
    }
    return {
      background: "var(--surface-3)",
      color: "var(--text-3)",
      borderColor: "var(--border)",
    }
  }

  return (
    <section>
      <p className="eyebrow" style={{ color: "var(--text-muted)", marginBottom: 12 }}>
        Scenario coverage
      </p>

      <div className="card" style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* Summary row */}
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 24, fontWeight: 900, color: "var(--text)" }}>{scenarios.scenario_count}</p>
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>total</p>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--surface-3)" }} />
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 20, fontWeight: 700, color: "var(--ok)" }}>{scenarios.positive_count}</p>
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>positive</p>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--surface-3)" }} />
          <div style={{ textAlign: "center" }}>
            <p style={{ fontSize: 20, fontWeight: 700, color: "var(--err)" }}>{scenarios.negative_count}</p>
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>negative</p>
          </div>
          {scenarios.description && (
            <>
              <div style={{ width: 1, height: 32, background: "var(--surface-3)" }} />
              <p style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6, flex: 1 }}>
                {scenarios.description}
              </p>
            </>
          )}
        </div>

        {/* Toggle scenario list */}
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
            fontSize: 12,
            color: "var(--text-muted)",
            textAlign: "left",
          }}
        >
          {expanded ? "Hide scenarios" : `Show ${scenarios.scenario_count} scenarios`}
        </button>

        {expanded && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 4 }}>
            {scenarios.scenarios.map((s, i) => (
              <div
                key={s.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  padding: "8px 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--border)",
                }}
              >
                <span className="mono" style={{
                  fontSize: 10,
                  fontWeight: 900,
                  color: "var(--text-muted)",
                  marginTop: 2,
                  width: 16,
                  flexShrink: 0,
                }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{s.label}</p>
                  <p className="mono" style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>{s.id}</p>
                  <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                    expected: <span className="mono">{s.expected_outcome_type}</span>
                  </p>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 2, flexShrink: 0 }}>
                  {s.tags.map(tag => (
                    <span
                      key={tag}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        borderRadius: 999,
                        border: "1px solid",
                        padding: "2px 6px",
                        fontSize: 9,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        ...tagStyle(tag),
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

// ─── Criteria breakdown ───────────────────────────────────────────────────────

function CriterionRow({ c }: { c: CriterionResult }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ borderBottom: "1px solid var(--border)" }}>
      <button
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
          transition: "background 0.15s",
        }}
        onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
        onMouseLeave={e => (e.currentTarget.style.background = "none")}
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        <span style={{
          flexShrink: 0,
          width: 20,
          height: 20,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 10,
          fontWeight: 700,
          background: c.passed ? "var(--ok-bg)" : "var(--err-bg)",
          color: c.passed ? "var(--ok)" : "var(--err)",
        }}>
          {c.passed ? "✓" : "✗"}
        </span>
        <span className="mono" style={{ flex: 1, fontSize: 12, color: "var(--text-2)" }}>{c.name}</span>
        <span style={{
          fontSize: 12,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 500,
          color: c.passed ? "var(--ok)" : "var(--err)",
        }}>
          {c.points_earned} / {c.points_possible}
        </span>
        {c.detail && (
          <span style={{
            color: "var(--text-muted)",
            fontSize: 12,
            marginLeft: 4,
            display: "inline-block",
            transition: "transform 0.15s",
            transform: open ? "rotate(90deg)" : "none",
          }}>›</span>
        )}
      </button>

      {open && c.detail && (
        <div style={{ padding: "0 16px 12px", marginLeft: 32 }}>
          <p style={{
            fontSize: 12,
            color: "var(--text-3)",
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
          }}>{c.detail}</p>
        </div>
      )}
    </div>
  )
}

function CriteriaSection({ live }: { live: PlaybookLiveDetail }) {
  const passing = live.criteria.filter(c => c.passed).length
  const failing  = live.criteria.filter(c => !c.passed).length

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p className="eyebrow" style={{ color: "var(--text-muted)" }}>
          Criteria breakdown
          <span style={{ marginLeft: 8, textTransform: "none", fontWeight: 400, color: "var(--text-muted)", opacity: 0.6 }}>
            (current)
          </span>
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {passing > 0 && (
            <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 500 }}>{passing} passing</span>
          )}
          {failing > 0 && (
            <span style={{ fontSize: 12, color: "var(--err)", fontWeight: 500 }}>{failing} failing</span>
          )}
        </div>
      </div>

      <div className="card" style={{ overflow: "hidden", padding: 0 }}>
        {live.criteria.length === 0 ? (
          <div style={{ padding: "32px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No criteria available for this playbook yet.
          </div>
        ) : (
          live.criteria.map((c, i) => <CriterionRow key={`${c.name}-${i}`} c={c} />)
        )}
      </div>

      <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 8, textAlign: "right", opacity: 0.7 }}>
        Criteria reflect the latest published quality data, not necessarily the frozen edition score.
      </p>
    </section>
  )
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ height: 96, borderRadius: 12, background: "var(--surface-3)", animation: "pulse 1.5s ease-in-out infinite" }} />
      <div style={{ height: 160, borderRadius: 12, background: "var(--surface-3)", animation: "pulse 1.5s ease-in-out infinite" }} />
      <div style={{ height: 256, borderRadius: 12, background: "var(--surface-3)", animation: "pulse 1.5s ease-in-out infinite" }} />
    </div>
  )
}

// ─── Share button ─────────────────────────────────────────────────────────────

function ShareButton() {
  const [copied, setCopied] = useState(false)
  const copy = useCallback(() => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [])
  return (
    <button
      onClick={copy}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 10,
        fontWeight: 500,
        color: "var(--text-3)",
        border: "1px solid var(--border)",
        borderRadius: 999,
        padding: "4px 12px",
        background: "var(--surface)",
        cursor: "pointer",
        transition: "color 0.15s, border-color 0.15s",
      }}
    >
      {copied ? (
        <><span style={{ color: "var(--ok)" }}>✓</span> Copied</>
      ) : (
        <><span>↗</span> Share</>
      )}
    </button>
  )
}

// ─── Page content ─────────────────────────────────────────────────────────────

function DeepDiveContent({
  editionSlug,
  playbookSlug,
  getToken,
}: {
  editionSlug: string
  playbookSlug: string
  getToken: (() => Promise<string | null>) | null
}) {
  const edition = getEdition(editionSlug)

  const [baseline, setBaseline]   = useState<BaselinePlaybook | null>(null)
  const [manifest, setManifest]   = useState<EditionManifest | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioSet | null>(null)
  const [live, setLive]           = useState<PlaybookLiveDetail | null>(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)

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

        // Fetch all three in parallel: edition manifest, scenarios, current detail
        const [editionRes, scenariosRes, liveRes] = await Promise.all([
          ed.apiEditionSlug
            ? fetch(`${base}/eval/benchmark/editions/${ed.apiEditionSlug}`, { headers })
            : null,
          fetch(`${base}/eval/scenarios/${encodeURIComponent(playbookSlug)}`, { headers }),
          fetch(`${base}/eval/playbooks/${encodeURIComponent(playbookSlug)}`, { headers }),
        ])

        if (cancelled) return

        // Edition manifest (required — need baseline score)
        if (editionRes) {
          if (!editionRes.ok) {
            const status = editionRes.status
            setError(
              status === 401 ? "Not authorised — check your session." :
              status === 403 ? "Forbidden — workspace role insufficient." :
              status === 404 ? `Edition "${editionSlug}" has no committed baseline yet.` :
              `Benchmark endpoint returned ${status}.`
            )
            return
          }
          const m: EditionManifest = await editionRes.json()
          setManifest(m)
          const row = m.playbooks.find(p => p.slug === playbookSlug)
          if (!row) {
            setError(`Playbook "${playbookSlug}" was not scored in ${ed.label}.`)
            return
          }
          setBaseline(row)
        } else {
          setError("No committed baseline for this edition. Publish a baseline first.")
          return
        }

        // Scenarios (optional — not all playbooks have multi-scenario fixtures)
        if (scenariosRes?.ok) {
          setScenarios(await scenariosRes.json())
        }

        // Current criteria breakdown (optional — show if available)
        if (liveRes?.ok) {
          setLive(await liveRes.json())
        }

      } catch {
        if (!cancelled) setError("Network error — could not reach the API.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editionSlug, playbookSlug])

  // Unknown edition
  if (!edition) {
    return (
      <AppShell>
        <div style={{ maxWidth: 768, margin: "0 auto", padding: "40px 24px" }}>
          <Link
            href="/benchmark"
            style={{ fontSize: 12, color: "var(--text-muted)", textDecoration: "none" }}
          >
            ← Benchmark
          </Link>
          <div className="card" style={{ marginTop: 32, padding: "40px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 13, fontWeight: 500, color: "var(--text-2)" }}>Edition not found</p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              No edition exists for <code className="mono">{editionSlug}</code>.
            </p>
            <Link
              href="/benchmark"
              style={{ display: "inline-block", marginTop: 16, fontSize: 12, color: "var(--accent)", textDecoration: "none" }}
            >
              View latest edition →
            </Link>
          </div>
        </div>
      </AppShell>
    )
  }

  const displayName = playbookDisplayName(playbookSlug)

  return (
    <AppShell>
      <div style={{ maxWidth: 768, margin: "0 auto", padding: "40px 24px" }}>

        {/* Breadcrumb */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)", marginBottom: 24 }}>
          <Link href="/benchmark" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Benchmark</Link>
          <span style={{ color: "var(--border)" }}>›</span>
          <Link href={`/benchmark/${editionSlug}`} style={{ color: "var(--text-muted)", textDecoration: "none" }}>{edition.label}</Link>
          <span style={{ color: "var(--border)" }}>›</span>
          <span style={{ color: "var(--text-2)", fontWeight: 500 }}>{displayName}</span>
        </div>

        {/* Page header */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{
              fontSize: 10,
              fontWeight: 600,
              color: "var(--accent)",
              background: "color-mix(in srgb, var(--accent) 10%, transparent)",
              border: "1px solid color-mix(in srgb, var(--accent) 20%, transparent)",
              borderRadius: 999,
              padding: "2px 10px",
            }}>
              {edition.label}
            </span>
            <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{edition.period}</span>
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 900, color: "var(--text)", margin: 0 }}>{displayName}</h1>
          <p className="mono" style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>{playbookSlug}</p>
        </div>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <div style={{
            borderRadius: 12,
            border: "1px solid var(--err-bg)",
            background: "var(--err-bg)",
            padding: "16px 20px",
          }}>
            <p style={{ fontSize: 13, color: "var(--err)" }}>{error}</p>
          </div>
        ) : baseline ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>

            {/* Baseline score */}
            <section>
              <p className="eyebrow" style={{ color: "var(--text-muted)", marginBottom: 12 }}>
                Edition score
              </p>
              <ScoreCard
                baseline={baseline}
                editionLabel={edition.label}
                model={manifest?.model ?? edition.modelLabel}
                publishedAt={manifest?.published_at ?? edition.publishedAt}
              />
            </section>

            {/* Scenario coverage */}
            {scenarios && (
              <ScenarioCoverage scenarios={scenarios} />
            )}

            {/* Current criteria breakdown */}
            {live && (
              <CriteriaSection live={live} />
            )}

            {/* Footer links */}
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              paddingTop: 8,
              borderTop: "1px solid var(--border)",
            }}>
              <Link
                href={`/benchmark/${editionSlug}`}
                style={{ fontSize: 12, color: "var(--text-muted)", textDecoration: "none" }}
              >
                ← Back to {edition.label} leaderboard
              </Link>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <ShareButton />
                <Link
                  href={`/eval/${encodeURIComponent(playbookSlug)}`}
                  style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none", fontWeight: 500 }}
                >
                  View quality details →
                </Link>
              </div>
            </div>

          </div>
        ) : null}

      </div>
    </AppShell>
  )
}

// ─── Auth wrapper (optional — benchmark is public) ────────────────────────────

function DeepDiveWithAuth({
  editionSlug,
  playbookSlug,
}: {
  editionSlug: string
  playbookSlug: string
}) {
  const { getToken, isLoaded } = useAuth()
  if (!isLoaded) return null
  return <DeepDiveContent editionSlug={editionSlug} playbookSlug={playbookSlug} getToken={getToken} />
}

export default function BenchmarkDeepDivePage() {
  const params = useParams()
  const editionSlug  = Array.isArray(params.edition) ? params.edition[0] : (params.edition as string)
  const playbookSlug = Array.isArray(params.slug)    ? params.slug[0]    : (params.slug    as string)
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <DeepDiveWithAuth editionSlug={editionSlug} playbookSlug={playbookSlug} />
  return <DeepDiveContent editionSlug={editionSlug} playbookSlug={playbookSlug} getToken={null} />
}
