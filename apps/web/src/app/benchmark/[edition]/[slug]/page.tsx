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

const GRADE_STYLE: Record<string, {
  bg: string; text: string; bar: string; border: string; dot: string
}> = {
  A: { bg: "bg-emerald-50", text: "text-emerald-700", bar: "bg-emerald-500", border: "border-emerald-200", dot: "bg-emerald-400" },
  B: { bg: "bg-blue-50",    text: "text-blue-700",    bar: "bg-blue-400",    border: "border-blue-200",    dot: "bg-blue-400"    },
  C: { bg: "bg-amber-50",   text: "text-amber-700",   bar: "bg-amber-400",   border: "border-amber-200",   dot: "bg-amber-400"   },
  D: { bg: "bg-orange-50",  text: "text-orange-700",  bar: "bg-orange-400",  border: "border-orange-200",  dot: "bg-orange-400"  },
  F: { bg: "bg-red-50",     text: "text-red-700",     bar: "bg-red-400",     border: "border-red-200",     dot: "bg-red-400"     },
}

function gs(grade: string) {
  return GRADE_STYLE[grade] ?? {
    bg: "bg-stone-100", text: "text-stone-500",
    bar: "bg-stone-300", border: "border-stone-200", dot: "bg-stone-300",
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
  const s = gs(baseline.grade)
  const structPct = baseline.total_max > 0 ? (baseline.structural_score / baseline.total_max) * 100 : 0
  const qualPct   = baseline.total_max > 0 ? (baseline.quality_score   / baseline.total_max) * 100 : 0

  return (
    <div className="rounded-xl border border-stone-200 bg-white px-6 py-5">
      <div className="flex items-start gap-5">
        {/* Grade */}
        <div className={`flex-shrink-0 flex items-center justify-center w-16 h-16 rounded-xl text-3xl font-black ${s.bg} ${s.text}`}>
          {baseline.grade}
        </div>

        {/* Score and bars */}
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-2xl font-bold text-stone-900">{baseline.pct.toFixed(0)}%</span>
            <span className="text-sm text-stone-400">{baseline.total_score} / {baseline.total_max} pts</span>
          </div>

          <div className="space-y-2">
            {/* Structural bar */}
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wide w-16 shrink-0">Structural</span>
              <div className="w-32 h-1.5 rounded-full bg-stone-100 overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full transition-all" style={{ width: `${Math.min(structPct, 100)}%` }} />
              </div>
              <span className="text-xs tabular-nums text-stone-500">{baseline.structural_score} pts</span>
            </div>

            {/* Quality bar (only if non-zero) */}
            {baseline.quality_score > 0 && (
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-medium text-stone-400 uppercase tracking-wide w-16 shrink-0">Quality</span>
                <div className="w-32 h-1.5 rounded-full bg-stone-100 overflow-hidden">
                  <div className="h-full bg-violet-400 rounded-full transition-all" style={{ width: `${Math.min(qualPct, 100)}%` }} />
                </div>
                <span className="text-xs tabular-nums text-stone-500">{baseline.quality_score} pts</span>
              </div>
            )}
          </div>
        </div>

        {/* Edition meta */}
        <div className="flex-shrink-0 text-right">
          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold border ${s.bg} ${s.text} ${s.border}`}>
            {editionLabel}
          </span>
          <p className="text-[10px] text-stone-400 mt-1.5">{fmt(publishedAt)}</p>
          <p className="text-[10px] text-stone-300 mt-0.5 font-mono">{model}</p>
        </div>
      </div>
    </div>
  )
}

// ─── Scenario coverage ────────────────────────────────────────────────────────

function ScenarioCoverage({ scenarios }: { scenarios: ScenarioSet }) {
  const [expanded, setExpanded] = useState(false)

  const tagColour = (tag: string): string => {
    if (tag === "positive") return "bg-emerald-50 text-emerald-700 border-emerald-200"
    if (tag === "negative") return "bg-red-50 text-red-600 border-red-200"
    return "bg-stone-100 text-stone-500 border-stone-200"
  }

  return (
    <section>
      <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-3">
        Scenario coverage
      </p>

      <div className="rounded-xl border border-stone-200 bg-white px-5 py-4 space-y-4">

        {/* Summary row */}
        <div className="flex items-center gap-6">
          <div className="text-center">
            <p className="text-2xl font-black text-stone-900">{scenarios.scenario_count}</p>
            <p className="text-[10px] text-stone-400">total</p>
          </div>
          <div className="w-px h-8 bg-stone-100" />
          <div className="text-center">
            <p className="text-xl font-bold text-emerald-700">{scenarios.positive_count}</p>
            <p className="text-[10px] text-stone-400">positive</p>
          </div>
          <div className="w-px h-8 bg-stone-100" />
          <div className="text-center">
            <p className="text-xl font-bold text-red-600">{scenarios.negative_count}</p>
            <p className="text-[10px] text-stone-400">negative</p>
          </div>
          {scenarios.description && (
            <>
              <div className="w-px h-8 bg-stone-100" />
              <p className="text-xs text-stone-400 leading-relaxed flex-1">{scenarios.description}</p>
            </>
          )}
        </div>

        {/* Toggle scenario list */}
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
        >
          {expanded ? "Hide scenarios" : `Show ${scenarios.scenario_count} scenarios`}
        </button>

        {expanded && (
          <div className="space-y-2 pt-1">
            {scenarios.scenarios.map((s, i) => (
              <div key={s.id} className="flex items-start gap-3 py-2 border-t border-stone-50 first:border-0">
                <span className="text-[10px] font-black text-stone-300 tabular-nums mt-0.5 w-4 shrink-0">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-stone-800 font-medium">{s.label}</p>
                  <p className="font-mono text-[10px] text-stone-400 mt-0.5">{s.id}</p>
                  <p className="text-[10px] text-stone-400 mt-0.5">
                    expected: <span className="font-mono">{s.expected_outcome_type}</span>
                  </p>
                </div>
                <div className="flex flex-wrap gap-1 mt-0.5 shrink-0">
                  {s.tags.map(tag => (
                    <span
                      key={tag}
                      className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${tagColour(tag)}`}
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
    <div className="border-b border-stone-100 last:border-0">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-stone-50 transition-colors text-left"
        onClick={() => setOpen(o => !o)}
        type="button"
      >
        <span className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
          c.passed ? "bg-emerald-100 text-emerald-600" : "bg-red-100 text-red-500"
        }`}>
          {c.passed ? "✓" : "✗"}
        </span>
        <span className="flex-1 font-mono text-xs text-stone-700">{c.name}</span>
        <span className={`text-xs tabular-nums font-medium ${c.passed ? "text-emerald-600" : "text-red-500"}`}>
          {c.points_earned} / {c.points_possible}
        </span>
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

function CriteriaSection({ live }: { live: PlaybookLiveDetail }) {
  const passing = live.criteria.filter(c => c.passed).length
  const failing  = live.criteria.filter(c => !c.passed).length

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest">
          Criteria breakdown
          <span className="ml-2 normal-case font-normal text-stone-300">(current)</span>
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
        {live.criteria.length === 0 ? (
          <div className="px-6 py-8 text-center text-sm text-stone-400">
            No criteria available for this playbook yet.
          </div>
        ) : (
          live.criteria.map((c, i) => <CriterionRow key={`${c.name}-${i}`} c={c} />)
        )}
      </div>

      <p className="text-[10px] text-stone-300 mt-2 text-right">
        Criteria reflect the latest published quality data, not necessarily the frozen edition score.
      </p>
    </section>
  )
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-24 rounded-xl bg-stone-100 animate-pulse" />
      <div className="h-40 rounded-xl bg-stone-100 animate-pulse" />
      <div className="h-64 rounded-xl bg-stone-100 animate-pulse" />
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
      className="inline-flex items-center gap-1.5 text-[10px] font-medium text-stone-500 hover:text-stone-800 border border-stone-200 hover:border-stone-300 rounded-full px-3 py-1 transition-colors bg-white"
    >
      {copied ? (
        <><span className="text-emerald-500">✓</span> Copied</>
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
        <div className="mx-auto max-w-3xl px-6 py-10">
          <Link href="/benchmark" className="text-xs text-stone-400 hover:text-stone-600 transition-colors">
            ← Benchmark
          </Link>
          <div className="mt-8 rounded-xl border border-stone-200 bg-white px-6 py-10 text-center">
            <p className="text-sm font-medium text-stone-700">Edition not found</p>
            <p className="text-xs text-stone-400 mt-1">
              No edition exists for <code className="font-mono">{editionSlug}</code>.
            </p>
            <Link href="/benchmark" className="mt-4 inline-block text-xs text-indigo-600 hover:text-indigo-800">
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
      <div className="mx-auto max-w-3xl px-6 py-10">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-xs text-stone-400 mb-6">
          <Link href="/benchmark" className="hover:text-stone-600 transition-colors">Benchmark</Link>
          <span className="text-stone-200">›</span>
          <Link href={`/benchmark/${editionSlug}`} className="hover:text-stone-600 transition-colors">{edition.label}</Link>
          <span className="text-stone-200">›</span>
          <span className="text-stone-600 font-medium">{displayName}</span>
        </div>

        {/* Page header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-semibold text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2.5 py-0.5">
              {edition.label}
            </span>
            <span className="text-[10px] text-stone-400">{edition.period}</span>
          </div>
          <h1 className="text-2xl font-black text-stone-900">{displayName}</h1>
          <p className="font-mono text-sm text-stone-400 mt-0.5">{playbookSlug}</p>
        </div>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <div className="rounded-xl border border-red-100 bg-red-50 px-5 py-4">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        ) : baseline ? (
          <div className="space-y-8">

            {/* Baseline score */}
            <section>
              <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-3">
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
            <div className="flex items-center justify-between pt-2 border-t border-stone-100">
              <Link
                href={`/benchmark/${editionSlug}`}
                className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
              >
                ← Back to {edition.label} leaderboard
              </Link>
              <div className="flex items-center gap-4">
                <ShareButton />
                <Link
                  href={`/eval/${encodeURIComponent(playbookSlug)}`}
                  className="text-xs text-indigo-600 hover:text-indigo-800 transition-colors font-medium"
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
