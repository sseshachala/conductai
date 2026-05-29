"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
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

const GRADE_STYLE: Record<string, { bg: string; text: string }> = {
  A: { bg: "bg-emerald-50", text: "text-emerald-700" },
  B: { bg: "bg-blue-50",    text: "text-blue-700"    },
  C: { bg: "bg-amber-50",   text: "text-amber-700"   },
  D: { bg: "bg-orange-50",  text: "text-orange-700"  },
  F: { bg: "bg-red-50",     text: "text-red-700"     },
}

function gradeStyle(grade: string) {
  return GRADE_STYLE[grade] ?? { bg: "bg-stone-100", text: "text-stone-500" }
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <span
      className="inline-block w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin"
      aria-hidden="true"
    />
  )
}

// ─── Criterion row ────────────────────────────────────────────────────────────

function CriterionRow({ c }: { c: CriterionResult }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-stone-100 last:border-0">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-stone-50 transition-colors text-left"
        onClick={() => setOpen(o => !o)}
      >
        {/* Pass/fail indicator */}
        <span className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
          c.passed ? "bg-emerald-100 text-emerald-600" : "bg-red-100 text-red-500"
        }`}>
          {c.passed ? "✓" : "✗"}
        </span>

        {/* Name */}
        <span className="flex-1 font-mono text-xs text-stone-700">{c.name}</span>

        {/* Points */}
        <span className={`text-xs tabular-nums font-medium ${c.passed ? "text-emerald-600" : "text-red-500"}`}>
          {c.points_earned} / {c.points_possible}
        </span>

        {/* Expand chevron */}
        {c.detail && (
          <span className={`text-stone-300 text-xs ml-1 transition-transform ${open ? "rotate-90" : ""}`}>›</span>
        )}
      </button>

      {open && c.detail && (
        <div className="px-4 pb-3 ml-8">
          <p className="text-xs text-stone-500 leading-relaxed whitespace-pre-wrap">{c.detail}</p>
        </div>
      )}
    </div>
  )
}

// ─── Score summary strip ──────────────────────────────────────────────────────

function ScoreSummary({ detail }: { detail: PlaybookEvalDetail }) {
  const s = gradeStyle(detail.grade)

  return (
    <div className="rounded-xl border border-stone-200 bg-white px-6 py-5 flex items-center gap-6">
      {/* Big grade */}
      <div className={`flex-shrink-0 flex items-center justify-center w-16 h-16 rounded-xl text-3xl font-black ${s.bg} ${s.text}`}>
        {detail.grade}
      </div>

      {/* Score breakdown */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-2xl font-bold text-stone-900">{detail.pct.toFixed(0)}%</span>
          <span className="text-sm text-stone-400">
            {detail.total_score} / {detail.total_max} pts
          </span>
        </div>

        {/* Mini bars */}
        <div className="flex items-center gap-4 mt-2">
          <ScorePill label="Structural" score={detail.structural_score} max={detail.structural_max} colour="bg-blue-400" />
          {detail.quality_max > 0 && (
            <ScorePill label="Quality" score={detail.quality_score} max={detail.quality_max} colour="bg-violet-400" />
          )}
        </div>
      </div>

      {/* Slug */}
      <span className="flex-shrink-0 font-mono text-sm text-stone-400 bg-stone-50 border border-stone-100 rounded-lg px-3 py-1.5">
        {detail.slug}
      </span>
    </div>
  )
}

function ScorePill({ label, score, max, colour }: { label: string; score: number; max: number; colour: string }) {
  const pct = max > 0 ? (score / max) * 100 : 0
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wide">{label}</span>
      <div className="w-20 h-1.5 rounded-full bg-stone-100 overflow-hidden">
        <div className={`h-full rounded-full ${colour} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-stone-500">{score}/{max}</span>
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
        className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        {open ? `Hide ${label}` : `Show ${label}`}
      </button>
      {open && (
        <pre className="mt-2 text-[11px] font-mono text-stone-600 bg-stone-50 rounded-lg p-3 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre">
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
      <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-3">
        Fixture
      </p>

      <div className="rounded-xl border border-stone-200 bg-white px-5 py-4 space-y-4">
        {/* Source + outcome type row */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Source badge */}
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide ${
            isFile
              ? "bg-blue-50 text-blue-600"
              : "bg-stone-100 text-stone-500"
          }`}>
            {fixture.source}
          </span>

          {/* Expected outcome type */}
          <span className="font-mono text-xs text-stone-600 bg-stone-50 border border-stone-100 rounded px-2 py-0.5">
            {fixture.expected_outcome_type}
          </span>
        </div>

        {/* Artifact keys */}
        <div>
          <p className="text-[10px] font-medium text-stone-400 uppercase tracking-wide mb-1.5">
            Expected artifact keys
          </p>
          {fixture.expected_artifact_keys.length === 0 ? (
            <span className="font-mono text-xs text-stone-400">none</span>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {fixture.expected_artifact_keys.map(key => (
                <span
                  key={key}
                  className="font-mono text-xs text-stone-600 bg-stone-100 rounded px-2 py-0.5"
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
            <p className="text-[10px] font-medium text-stone-400 uppercase tracking-wide mb-1.5">
              Trigger payload
            </p>
            <CollapsibleJson label="payload" data={fixture.trigger_payload} />
          </div>
        )}

        {/* Initial state */}
        {fixture.initial_state && Object.keys(fixture.initial_state).length > 0 && (
          <div>
            <p className="text-[10px] font-medium text-stone-400 uppercase tracking-wide mb-1.5">
              Initial state
            </p>
            <CollapsibleJson label="initial state" data={fixture.initial_state} />
          </div>
        )}
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
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

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

  async function handleRunEval() {
    setRunning(true)
    setRunError(null)

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const workspaceId = getCookie("delegator_project_id")
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/eval/run/${encodeURIComponent(slug)}`,
        { method: "POST", headers }
      )

      if (!res.ok) {
        const hint =
          res.status === 401 ? "Not authorised — check your session." :
          res.status === 403 ? "Forbidden — workspace role may be insufficient." :
          res.status === 404 ? `Playbook "${slug}" not found.` :
          `Run failed with status ${res.status}.`
        setRunError(hint)
        return
      }

      const fresh: PlaybookEvalDetail = await res.json()
      setDetail(fresh)
    } catch {
      setRunError("Network error — could not reach the API.")
    } finally {
      setRunning(false)
    }
  }

  const passing = detail?.criteria.filter(c => c.passed).length ?? 0
  const failing = detail?.criteria.filter(c => !c.passed).length ?? 0

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">

        {/* Header row: back link + run button */}
        <div className="flex items-center justify-between mb-6">
          <Link
            href="/eval"
            className="inline-flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-600 transition-colors"
          >
            ← Quality
          </Link>

          {!loading && !error && detail && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={running}
                onClick={handleRunEval}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium bg-stone-900 text-white hover:bg-stone-700 transition-colors disabled:opacity-50"
              >
                {running && <Spinner />}
                {running ? "Running…" : "Run eval"}
              </button>
            </div>
          )}
        </div>

        {/* Inline run error */}
        {runError && (
          <div className="mb-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3">
            <p className="text-xs text-red-600">{runError}</p>
          </div>
        )}

        {loading ? (
          <div className="space-y-4">
            <div className="h-24 rounded-xl bg-stone-100 animate-pulse" />
            <div className="h-64 rounded-xl bg-stone-100 animate-pulse" />
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-100 bg-red-50 px-5 py-4">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        ) : detail ? (
          <div className="space-y-6">

            {/* Score summary */}
            <ScoreSummary detail={detail} />

            {/* Criteria list */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest">
                  Criteria
                </p>
                <div className="flex items-center gap-3">
                  {passing > 0 && (
                    <span className="text-xs text-emerald-600 font-medium">{passing} passing</span>
                  )}
                  {failing > 0 && (
                    <span className="text-xs text-red-500 font-medium">{failing} failing</span>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
                {detail.criteria.length === 0 ? (
                  <div className="px-6 py-8 text-center text-sm text-stone-400">
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
