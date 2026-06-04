"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

// ─── Data shapes ─────────────────────────────────────────────────────────────

interface CriterionResult {
  name: string
  passed: boolean
  points_earned: number
  points_possible: number
  detail: string
}

interface EvalFixture {
  slug: string
  source: "embedded" | "file"
  trigger_payload: Record<string, unknown> | null
  initial_state: Record<string, unknown> | null
  expected_outcome_type: string
  expected_artifact_keys: string[]
  extra_assertions: unknown[]
}

interface PlaybookEvalDetail {
  slug: string
  grade: string
  pct: number
  total_score: number
  total_max: number
  structural_score: number
  structural_max: number
  quality_score: number
  quality_max: number
  criteria: CriterionResult[]
  fixture: EvalFixture | null
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

function gradeColors(grade: string) {
  return {
    bg: GRADE_BG[grade] ?? "var(--surface-3)",
    text: GRADE_C[grade] ?? "var(--text-3)",
  }
}

// ─── Criterion row ────────────────────────────────────────────────────────────

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
      >
        {/* Pass/fail indicator */}
        <span
          style={{
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
          }}
        >
          {c.passed ? "✓" : "✗"}
        </span>

        {/* Name */}
        <span className="mono" style={{ flex: 1, fontSize: 12, color: "var(--text-2)" }}>
          {c.name}
        </span>

        {/* Points */}
        <span
          style={{
            fontSize: 12,
            fontVariantNumeric: "tabular-nums",
            fontWeight: 500,
            color: c.passed ? "var(--ok)" : "var(--err)",
          }}
        >
          {c.points_earned} / {c.points_possible}
        </span>

        {/* Expand chevron */}
        {c.detail && (
          <span
            style={{
              color: "var(--text-muted)",
              fontSize: 12,
              marginLeft: 4,
              display: "inline-block",
              transition: "transform 0.15s",
              transform: open ? "rotate(90deg)" : "none",
            }}
          >
            ›
          </span>
        )}
      </button>

      {open && c.detail && (
        <div style={{ padding: "0 16px 12px", marginLeft: 32 }}>
          <p
            style={{
              fontSize: 12,
              color: "var(--text-3)",
              lineHeight: 1.6,
              whiteSpace: "pre-wrap",
              margin: 0,
            }}
          >
            {c.detail}
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Score summary strip ──────────────────────────────────────────────────────

function ScoreSummary({ detail }: { detail: PlaybookEvalDetail }) {
  const g = gradeColors(detail.grade)

  return (
    <div
      className="card"
      style={{ padding: "20px 24px", display: "flex", alignItems: "center", gap: 24 }}
    >
      {/* Big grade */}
      <div
        style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 64,
          height: 64,
          borderRadius: 12,
          fontSize: 30,
          fontWeight: 900,
          background: g.bg,
          color: g.text,
        }}
      >
        {detail.grade}
      </div>

      {/* Score breakdown */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 24, fontWeight: 700, color: "var(--text)" }}>
            {detail.pct.toFixed(0)}%
          </span>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {detail.total_score} / {detail.total_max} pts
          </span>
        </div>

        {/* Mini bars */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 8 }}>
          <ScorePill
            label="Structural"
            score={detail.structural_score}
            max={detail.structural_max}
            colour="#60a5fa"
          />
          {detail.quality_max > 0 && (
            <ScorePill
              label="Quality"
              score={detail.quality_score}
              max={detail.quality_max}
              colour="#a78bfa"
            />
          )}
        </div>
      </div>

      {/* Slug */}
      <span
        className="mono"
        style={{
          flexShrink: 0,
          fontSize: 13,
          color: "var(--text-muted)",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "6px 12px",
        }}
      >
        {detail.slug}
      </span>
    </div>
  )
}

function ScorePill({
  label,
  score,
  max,
  colour,
}: {
  label: string
  score: number
  max: number
  colour: string
}) {
  const pct = max > 0 ? (score / max) * 100 : 0
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span className="eyebrow" style={{ fontSize: 10 }}>{label}</span>
      <div
        style={{
          width: 80,
          height: 6,
          borderRadius: 999,
          background: "var(--surface-3)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            borderRadius: 999,
            background: colour,
            width: `${pct}%`,
            transition: "width 0.3s",
          }}
        />
      </div>
      <span
        style={{
          fontSize: 12,
          fontVariantNumeric: "tabular-nums",
          color: "var(--text-3)",
        }}
      >
        {score}/{max}
      </span>
    </div>
  )
}

// ─── Collapsible JSON block ───────────────────────────────────────────────────

function CollapsibleJson({
  label,
  data,
}: {
  label: string
  data: Record<string, unknown>
}) {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <button
        style={{
          fontSize: 12,
          color: open ? "var(--text-3)" : "var(--text-muted)",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
          transition: "color 0.15s",
        }}
        onMouseEnter={e => (e.currentTarget.style.color = "var(--text-3)")}
        onMouseLeave={e => (e.currentTarget.style.color = open ? "var(--text-3)" : "var(--text-muted)")}
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        {open ? `Hide ${label}` : `Show ${label}`}
      </button>
      {open && (
        <pre
          className="mono"
          style={{
            marginTop: 8,
            fontSize: 11,
            color: "var(--text-2)",
            background: "var(--surface-2)",
            borderRadius: 8,
            padding: 12,
            overflowX: "auto",
            maxHeight: 256,
            overflowY: "auto",
            whiteSpace: "pre",
          }}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ─── Fixture section ──────────────────────────────────────────────────────────

function FixtureSection({ fixture }: { fixture: EvalFixture }) {
  const isFile = fixture.source === "file"

  return (
    <div>
      <p className="eyebrow" style={{ marginBottom: 12 }}>
        Fixture
      </p>

      <div className="card" style={{ padding: "16px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Source + outcome type row */}
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
            {/* Source badge */}
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                borderRadius: 999,
                padding: "2px 8px",
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.04em",
                background: isFile ? "#eff6ff" : "var(--surface-3)",
                color: isFile ? "#2563eb" : "var(--text-3)",
              }}
            >
              {fixture.source}
            </span>

            {/* Expected outcome type */}
            <span
              className="mono"
              style={{
                fontSize: 12,
                color: "var(--text-2)",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 4,
                padding: "2px 8px",
              }}
            >
              {fixture.expected_outcome_type}
            </span>
          </div>

          {/* Artifact keys */}
          <div>
            <p className="eyebrow" style={{ fontSize: 10, marginBottom: 6 }}>
              Expected artifact keys
            </p>
            {fixture.expected_artifact_keys.length === 0 ? (
              <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                none
              </span>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {fixture.expected_artifact_keys.map(key => (
                  <span
                    key={key}
                    className="mono"
                    style={{
                      fontSize: 12,
                      color: "var(--text-2)",
                      background: "var(--surface-3)",
                      borderRadius: 4,
                      padding: "2px 8px",
                    }}
                  >
                    {key}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Trigger payload */}
          {fixture.trigger_payload && Object.keys(fixture.trigger_payload).length > 0 && (
            <div>
              <p className="eyebrow" style={{ fontSize: 10, marginBottom: 6 }}>
                Trigger payload
              </p>
              <CollapsibleJson label="payload" data={fixture.trigger_payload} />
            </div>
          )}

          {/* Initial state */}
          {fixture.initial_state && Object.keys(fixture.initial_state).length > 0 && (
            <div>
              <p className="eyebrow" style={{ fontSize: 10, marginBottom: 6 }}>
                Initial state
              </p>
              <CollapsibleJson label="initial state" data={fixture.initial_state} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Page content ─────────────────────────────────────────────────────────────

function EvalDetailContent({
  slug,
  getToken,
}: {
  slug: string
  getToken: (() => Promise<string | null>) | null
}) {
  const [detail, setDetail] = useState<PlaybookEvalDetail | null>(null)
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

        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/eval/playbooks/${encodeURIComponent(slug)}`, { headers })

        if (cancelled) return

        if (!res.ok) {
          const hint =
            res.status === 404 ? `Playbook "${slug}" not found in eval results.` :
            res.status === 401 ? "Not authorised — check your session." :
            res.status === 403 ? "Forbidden — workspace role may be insufficient." :
            `API returned ${res.status}.`
          setError(hint)
          return
        }

        setDetail(await res.json())
      } catch {
        if (!cancelled) setError("Network error — could not reach the API.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  const passing = detail?.criteria.filter(c => c.passed).length ?? 0
  const failing = detail?.criteria.filter(c => !c.passed).length ?? 0

  return (
    <AppShell>
      <div style={{ maxWidth: 768, margin: "0 auto", padding: "40px 24px" }}>

        {/* Header row */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <Link
            href="/eval"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              color: "var(--text-muted)",
              textDecoration: "none",
              transition: "color 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text-3)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            ← Quality
          </Link>
        </div>

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div
              style={{
                height: 96,
                borderRadius: 12,
                background: "var(--surface-3)",
                animation: "pulse 1.5s ease-in-out infinite",
              }}
            />
            <div
              style={{
                height: 256,
                borderRadius: 12,
                background: "var(--surface-3)",
                animation: "pulse 1.5s ease-in-out infinite",
              }}
            />
          </div>
        ) : error ? (
          <div
            style={{
              borderRadius: 12,
              border: "1px solid var(--err-bg)",
              background: "var(--err-bg)",
              padding: "16px 20px",
            }}
          >
            <p style={{ fontSize: 13, color: "var(--err)", margin: 0 }}>{error}</p>
          </div>
        ) : detail ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

            {/* Score summary */}
            <ScoreSummary detail={detail} />

            {/* Criteria list */}
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                }}
              >
                <p className="eyebrow" style={{ margin: 0 }}>
                  Criteria
                </p>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  {passing > 0 && (
                    <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 500 }}>
                      {passing} passing
                    </span>
                  )}
                  {failing > 0 && (
                    <span style={{ fontSize: 12, color: "var(--err)", fontWeight: 500 }}>
                      {failing} failing
                    </span>
                  )}
                </div>
              </div>

              <div
                className="card"
                style={{ overflow: "hidden", padding: 0 }}
              >
                {detail.criteria.length === 0 ? (
                  <div
                    style={{
                      padding: "32px 24px",
                      textAlign: "center",
                      fontSize: 13,
                      color: "var(--text-muted)",
                    }}
                  >
                    No criteria scored for this playbook.
                  </div>
                ) : (
                  detail.criteria.map((c, i) => <CriterionRow key={`${c.name}-${i}`} c={c} />)
                )}
              </div>
            </div>

            {/* Fixture section */}
            {detail.fixture && (
              <FixtureSection fixture={detail.fixture} />
            )}

          </div>
        ) : null}
      </div>
    </AppShell>
  )
}

// ─── Auth wrapper ─────────────────────────────────────────────────────────────

function EvalDetailWithAuth({ slug }: { slug: string }) {
  const { getToken, isLoaded } = useAuth()
  if (!isLoaded) return null
  return <EvalDetailContent slug={slug} getToken={getToken} />
}

export default function EvalDetailPage() {
  const params = useParams()
  const slug = Array.isArray(params.slug) ? params.slug[0] : (params.slug as string)
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <EvalDetailWithAuth slug={slug} />
  return <EvalDetailContent slug={slug} getToken={null} />
}
