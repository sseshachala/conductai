"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
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
  passing: number
  failing: number
  average_pct: number
  grade_counts: GradeCounts
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
  /** Not stored in baseline snapshots — present only from live eval. */
  failing_criteria?: number
}

/** Shape returned by GET /eval/benchmark/editions/{slug} */
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

const GRADE_STYLE: Record<string, { bg: string; text: string; bar: string; dot: string; border: string }> = {
  A: { bg: "bg-emerald-50",  text: "text-emerald-700", bar: "bg-emerald-500", dot: "bg-emerald-400", border: "border-emerald-200" },
  B: { bg: "bg-blue-50",     text: "text-blue-700",    bar: "bg-blue-400",    dot: "bg-blue-400",    border: "border-blue-200"    },
  C: { bg: "bg-amber-50",    text: "text-amber-700",   bar: "bg-amber-400",   dot: "bg-amber-400",   border: "border-amber-200"   },
  D: { bg: "bg-orange-50",   text: "text-orange-700",  bar: "bg-orange-400",  dot: "bg-orange-400",  border: "border-orange-200"  },
  F: { bg: "bg-red-50",      text: "text-red-700",     bar: "bg-red-400",     dot: "bg-red-400",     border: "border-red-200"     },
}

function gs(grade: string) {
  return GRADE_STYLE[grade] ?? { bg: "bg-stone-100", text: "text-stone-500", bar: "bg-stone-300", dot: "bg-stone-300", border: "border-stone-200" }
}

function fmt(date: string) {
  try {
    return new Date(date).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
  } catch { return date }
}

// ─── Grade badge ──────────────────────────────────────────────────────────────

function GradeBadge({ grade, size = "sm" }: { grade: string; size?: "sm" | "lg" }) {
  const s = gs(grade)
  const cls = size === "lg"
    ? `w-12 h-12 rounded-xl text-xl font-black`
    : `w-7 h-7 rounded-lg text-xs font-bold`
  return (
    <span className={`inline-flex items-center justify-center shrink-0 ${cls} ${s.bg} ${s.text}`}>
      {grade}
    </span>
  )
}

// ─── Inline score bar ─────────────────────────────────────────────────────────

function ScoreBar({ pct, grade }: { pct: number; grade: string }) {
  const s = gs(grade)
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 rounded-full bg-stone-100 overflow-hidden">
        <div className={`h-full rounded-full ${s.bar} transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-stone-600 font-medium">{pct.toFixed(0)}%</span>
    </div>
  )
}

// ─── Grade distribution card ──────────────────────────────────────────────────

function DistributionCard({ summary }: { summary: EvalSummary }) {
  const counts = summary.grade_counts
  const total = GRADE_ORDER.reduce((s, g) => s + counts[g], 0)
  return (
    <div className="rounded-xl border border-stone-200 bg-white px-6 py-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-1">Grade distribution</p>
          <p className="text-xs text-stone-400">{total} playbooks scored</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-black text-stone-900">{summary.average_pct.toFixed(0)}%</p>
          <p className="text-[10px] text-stone-400">average score</p>
        </div>
      </div>

      {/* Segmented bar */}
      {total > 0 && (
        <div className="flex h-2.5 rounded-full overflow-hidden gap-px mb-4">
          {GRADE_ORDER.map(g => {
            const pct = (counts[g] / total) * 100
            if (pct === 0) return null
            return (
              <div key={g} className={`${gs(g).bar} transition-all`} style={{ width: `${pct}%` }} title={`${g}: ${counts[g]}`} />
            )
          })}
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-5">
        {GRADE_ORDER.map(g => (
          <div key={g} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${gs(g).dot}`} />
            <span className="text-xs text-stone-500">
              <span className="font-semibold text-stone-700">{g}</span> {counts[g]}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Leaderboard ──────────────────────────────────────────────────────────────

function Leaderboard({ playbooks, edition, editionSlug }: { playbooks: PlaybookRow[]; edition: BenchmarkEdition; editionSlug: string }) {
  const sorted = [...playbooks].sort((a, b) => {
    const go = { A: 0, B: 1, C: 2, D: 3, F: 4 } as Record<string, number>
    const gd = (go[a.grade] ?? 5) - (go[b.grade] ?? 5)
    return gd !== 0 ? gd : b.pct - a.pct
  })

  if (sorted.length === 0) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white px-6 py-12 text-center">
        <p className="text-sm text-stone-400">No playbook scores available yet.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      {/* Model label strip */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-stone-100 bg-stone-50">
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest">Leaderboard</p>
        <span className="inline-flex items-center gap-1.5 text-[10px] text-stone-500 bg-white border border-stone-200 rounded-full px-2.5 py-1 font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
          {edition.modelLabel}
        </span>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-100 text-left">
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide w-6">#</th>
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide">Playbook</th>
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide">Grade</th>
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide">Score</th>
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide hidden sm:table-cell">Structural</th>
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide hidden sm:table-cell">Quality</th>
            <th className="px-4 py-2.5 text-[10px] font-medium text-stone-400 uppercase tracking-wide text-right">Issues</th>
            <th className="px-2 py-2.5 w-6" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => {
            const s = gs(p.grade)
            // Show each sub-score as a proportion of total_max so the bar
            // widths reflect how structural and quality points contribute.
            const structPct = p.total_max > 0 ? Math.min((p.structural_score / p.total_max) * 100, 100) : 0
            const qualPct   = p.total_max > 0 ? Math.min((p.quality_score   / p.total_max) * 100, 100) : 0
            return (
              <tr key={p.slug} className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors group">
                <td className="px-4 py-3 text-xs text-stone-300 tabular-nums">{i + 1}</td>
                <td className="px-4 py-3">
                  <p className="text-sm font-medium text-stone-900">{playbookDisplayName(p.slug)}</p>
                  <p className="font-mono text-[10px] text-stone-400 mt-0.5">{p.slug}</p>
                </td>
                <td className="px-4 py-3">
                  <GradeBadge grade={p.grade} />
                </td>
                <td className="px-4 py-3">
                  <ScoreBar pct={p.pct} grade={p.grade} />
                </td>
                <td className="px-4 py-3 hidden sm:table-cell">
                  <span className="text-xs tabular-nums text-stone-500">
                    {p.structural_score}
                    <span className="text-stone-300"> / </span>
                    {p.total_max}
                  </span>
                  <div className="w-16 h-1 rounded-full bg-stone-100 overflow-hidden mt-1">
                    <div className="h-full bg-blue-300 rounded-full" style={{ width: `${structPct}%` }} />
                  </div>
                </td>
                <td className="px-4 py-3 hidden sm:table-cell">
                  {p.quality_score > 0 ? (
                    <>
                      <span className="text-xs tabular-nums text-stone-500">
                        {p.quality_score}
                        <span className="text-stone-300"> pts</span>
                      </span>
                      <div className="w-16 h-1 rounded-full bg-stone-100 overflow-hidden mt-1">
                        <div className="h-full bg-violet-300 rounded-full" style={{ width: `${qualPct}%` }} />
                      </div>
                    </>
                  ) : (
                    <span className="text-xs text-stone-300">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {(p.failing_criteria ?? 0) > 0 ? (
                    <span className={`inline-flex items-center gap-1 text-xs font-medium ${s.text}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                      {p.failing_criteria}
                    </span>
                  ) : (
                    <span className="text-xs text-emerald-500">✓</span>
                  )}
                </td>
                <td className="px-2 py-3">
                  <Link
                    href={`/benchmark/${editionSlug}/${p.slug}`}
                    className="text-stone-300 hover:text-indigo-500 transition-colors opacity-0 group-hover:opacity-100 text-sm"
                    title="View playbook deep-dive"
                  >
                    →
                  </Link>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Editorial findings ───────────────────────────────────────────────────────

function EditorialFindings({ edition }: { edition: BenchmarkEdition }) {
  if (edition.findings.length === 0) return null
  return (
    <section>
      <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-4">
        Key findings
      </p>
      <div className="space-y-3">
        {edition.findings.map((f, i) => (
          <div key={i} className="rounded-xl border border-stone-200 bg-white px-5 py-4 flex gap-4">
            <span className="shrink-0 text-[10px] font-black text-stone-300 tabular-nums mt-0.5 w-4">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <p className="text-sm font-semibold text-stone-900 mb-1">{f.headline}</p>
              <p className="text-xs text-stone-500 leading-relaxed">{f.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ─── Methodology ─────────────────────────────────────────────────────────────

function Methodology() {
  return (
    <section>
      <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-4">
        Methodology
      </p>
      <div className="rounded-xl border border-stone-200 bg-white px-6 py-5 space-y-4 text-xs text-stone-500 leading-relaxed">
        <div>
          <p className="font-semibold text-stone-700 mb-1">Scoring approach</p>
          <p>
            Each playbook is scored against a fixed set of structural and quality criteria. Structural
            criteria check that required fields are present and correctly wired (trigger, brain blocks,
            output blocks, parameter completeness). Quality criteria assess description completeness,
            output clarity, and documentation. Every criterion is pass/fail; the score is the sum of
            points earned divided by points possible.
          </p>
        </div>
        <div>
          <p className="font-semibold text-stone-700 mb-1">Grade scale</p>
          <div className="flex flex-wrap gap-2 mt-2">
            {[
              { grade: "A", range: "90–100%" },
              { grade: "B", range: "75–89%"  },
              { grade: "C", range: "60–74%"  },
              { grade: "D", range: "40–59%"  },
              { grade: "F", range: "0–39%"   },
            ].map(({ grade, range }) => {
              const s = gs(grade)
              return (
                <span key={grade} className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium ${s.bg} ${s.text} ${s.border}`}>
                  <span className="font-black">{grade}</span>
                  <span className="font-normal opacity-70">{range}</span>
                </span>
              )
            })}
          </div>
        </div>
        <div>
          <p className="font-semibold text-stone-700 mb-1">Scoring model</p>
          <p>
            Edition 001 uses structural scoring only — criteria are evaluated by static analysis of
            the playbook YAML, with no live LLM calls. Future editions will layer in live-mode scoring
            (Claude Haiku, Sonnet, and Opus) to measure output quality against fixture-defined
            expected outcomes.
          </p>
        </div>
        <div>
          <p className="font-semibold text-stone-700 mb-1">Reproducibility</p>
          <p>
            Structural scores are deterministic and fully reproducible from the playbook YAML. To
            reproduce any result, run{" "}
            <code className="font-mono text-[11px] bg-stone-100 px-1.5 py-0.5 rounded">
              conduct eval --playbook &lt;slug&gt;
            </code>{" "}
            against the same playbook version. Click any row arrow to see the full criteria
            breakdown for that playbook.
          </p>
        </div>
      </div>
    </section>
  )
}

// ─── Edition nav ──────────────────────────────────────────────────────────────

function EditionNav({ edition }: { edition: BenchmarkEdition }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {edition.prevEditionSlug ? (
        <Link
          href={`/benchmark/${edition.prevEditionSlug}`}
          className="text-stone-400 hover:text-stone-700 transition-colors"
        >
          ← Previous edition
        </Link>
      ) : (
        <span className="text-stone-200">← Previous edition</span>
      )}
      <span className="text-stone-200">·</span>
      {edition.nextEditionSlug ? (
        <Link
          href={`/benchmark/${edition.nextEditionSlug}`}
          className="text-stone-400 hover:text-stone-700 transition-colors"
        >
          Next edition →
        </Link>
      ) : (
        <span className="text-stone-200">Next edition →</span>
      )}
    </div>
  )
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-28 rounded-xl bg-stone-100 animate-pulse" />
      <div className="h-72 rounded-xl bg-stone-100 animate-pulse" />
      <div className="h-40 rounded-xl bg-stone-100 animate-pulse" />
    </div>
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
  const router = useRouter()
  const edition = getEdition(editionSlug)

  const [summary, setSummary] = useState<EvalSummary | null>(null)
  const [playbooks, setPlaybooks] = useState<PlaybookRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!edition) return
    // Capture a non-nullable snapshot so the async function can reference it
    // without TypeScript losing the narrowing across await boundaries.
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

        // ── Try frozen baseline first ──────────────────────────────────────
        // Editions with a committed baseline use the dedicated endpoint so
        // scores are immutable per edition, not re-evaluated on every view.
        if (ed.apiEditionSlug) {
          const manifestRes = await fetch(
            `${base}/eval/benchmark/editions/${ed.apiEditionSlug}`,
            { headers }
          )
          if (cancelled) return

          if (manifestRes.ok) {
            const manifest: EditionManifest = await manifestRes.json()
            setSummary(manifest.summary)
            setPlaybooks(
              manifest.playbooks.map(p => ({ ...p, failing_criteria: undefined }))
            )
            return
          }

          // 404 = edition not yet committed, fall through to live eval.
          // Any other non-OK status (401/403/500) is a real error.
          if (manifestRes.status !== 404) {
            const status = manifestRes.status
            setError(
              status === 401 ? "Not authorised — check your session." :
              status === 403 ? "Forbidden — workspace role insufficient." :
              `Benchmark endpoint returned ${status}.`
            )
            return
          }
        }

        // ── Fall back to live eval endpoints ───────────────────────────────
        // Used when no committed baseline exists for this edition yet.
        const [summaryRes, playbooksRes] = await Promise.all([
          fetch(`${base}/eval/summary`, { headers }),
          fetch(`${base}/eval/playbooks`, { headers }),
        ])

        if (cancelled) return

        if (!summaryRes.ok && !playbooksRes.ok) {
          const status = summaryRes.status
          setError(
            status === 401 ? "Not authorised — check your session." :
            status === 403 ? "Forbidden — workspace role insufficient." :
            status === 500 ? "Eval runner returned an error (500). Check the API logs." :
            `Both eval endpoints returned ${status}.`
          )
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

  // Unknown edition
  if (!edition) {
    return (
      <AppShell>
        <div className="mx-auto max-w-4xl px-6 py-10">
          <Link href="/benchmark" className="text-xs text-stone-400 hover:text-stone-600 transition-colors">
            ← Benchmark
          </Link>
          <div className="mt-8 rounded-xl border border-stone-200 bg-white px-6 py-10 text-center">
            <p className="text-sm font-medium text-stone-700">Edition not found</p>
            <p className="text-xs text-stone-400 mt-1">
              No benchmark edition exists for <code className="font-mono">{editionSlug}</code>.
            </p>
            <Link href="/benchmark" className="mt-4 inline-block text-xs text-indigo-600 hover:text-indigo-800 transition-colors">
              View latest edition →
            </Link>
          </div>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Page header */}
        <div className="mb-8">
          <div className="flex items-start justify-between mb-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2.5 py-0.5">
                {edition.label}
              </span>
              <span className="text-[10px] text-stone-400">{edition.period}</span>
            </div>
            <EditionNav edition={edition} />
          </div>
          <h1 className="text-2xl font-black text-stone-900 mt-2">Conduct AI Benchmark</h1>
          <p className="text-sm text-stone-400 mt-1">
            {edition.totalPlaybooks} playbooks · {edition.modelLabel}
            {summary && (
              <> · published {fmt(edition.publishedAt)}</>
            )}
          </p>
        </div>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <div className="rounded-xl border border-red-100 bg-red-50 px-5 py-4">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        ) : (
          <div className="space-y-10">

            {/* Grade distribution */}
            {summary && (
              <section>
                <DistributionCard summary={summary} />
              </section>
            )}

            {/* Leaderboard */}
            <section>
              <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-3">
                Leaderboard
              </p>
              <Leaderboard playbooks={playbooks} edition={edition} editionSlug={editionSlug} />
              <p className="text-[10px] text-stone-300 mt-2 text-right">
                Click the arrow on any row to view the playbook deep-dive.
              </p>
            </section>

            {/* Editorial findings */}
            <EditorialFindings edition={edition} />

            {/* Methodology */}
            <Methodology />

          </div>
        )}

      </div>
    </AppShell>
  )
}

// ─── Auth wrapper ─────────────────────────────────────────────────────────────

function BenchmarkWithAuth({ editionSlug }: { editionSlug: string }) {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
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
