"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
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
  total_criteria: number
  run_count?: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

const GRADE_ORDER: (keyof GradeCounts)[] = ["A", "B", "C", "D", "F"]

const GRADE_STYLE: Record<string, { bg: string; text: string; bar: string; dot: string }> = {
  A: { bg: "bg-emerald-50",  text: "text-emerald-700", bar: "bg-emerald-500", dot: "bg-emerald-400" },
  B: { bg: "bg-blue-50",     text: "text-blue-700",    bar: "bg-blue-400",    dot: "bg-blue-400"    },
  C: { bg: "bg-amber-50",    text: "text-amber-700",   bar: "bg-amber-400",   dot: "bg-amber-400"   },
  D: { bg: "bg-orange-50",   text: "text-orange-700",  bar: "bg-orange-400",  dot: "bg-orange-400"  },
  F: { bg: "bg-red-50",      text: "text-red-700",     bar: "bg-red-400",     dot: "bg-red-400"     },
}

function gradeStyle(grade: string) {
  return GRADE_STYLE[grade] ?? { bg: "bg-stone-100", text: "text-stone-500", bar: "bg-stone-300", dot: "bg-stone-300" }
}

function GradeBadge({ grade }: { grade: string }) {
  const s = gradeStyle(grade)
  return (
    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold ${s.bg} ${s.text}`}>
      {grade}
    </span>
  )
}

function PassBar({ pct }: { pct: number }) {
  const colour =
    pct >= 90 ? "bg-emerald-400" :
    pct >= 70 ? "bg-blue-400"    :
    pct >= 50 ? "bg-amber-400"   :
    pct >= 30 ? "bg-orange-400"  :
                "bg-red-400"
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 rounded-full bg-stone-100 overflow-hidden">
        <div className={`h-full rounded-full ${colour} transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-stone-500">{pct.toFixed(0)}%</span>
    </div>
  )
}

// ─── Grade distribution bar ───────────────────────────────────────────────────

function GradeDistributionCard({ counts }: { counts: GradeCounts }) {
  const total = GRADE_ORDER.reduce((s, g) => s + counts[g], 0)
  const overall =
    total === 0 ? null :
    counts.A / total >= 0.7 ? "A" :
    counts.F / total >= 0.3 ? "F" :
    (counts.A + counts.B) / total >= 0.7 ? "B" :
    (counts.D + counts.F) / total >= 0.4 ? "D" :
    "C"

  return (
    <div className="rounded-xl border border-stone-200 bg-white px-6 py-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-widest mb-0.5">
            Overall quality
          </p>
          <p className="text-xs text-stone-400">
            {total === 0 ? "No evals run yet" : `${total} playbook${total === 1 ? "" : "s"} evaluated`}
          </p>
        </div>
        {overall && (
          <div className={`flex items-center justify-center w-12 h-12 rounded-xl text-2xl font-black ${gradeStyle(overall).bg} ${gradeStyle(overall).text}`}>
            {overall}
          </div>
        )}
      </div>

      {/* Segmented bar */}
      {total > 0 && (
        <div className="mb-4">
          <div className="flex h-3 rounded-full overflow-hidden gap-px">
            {GRADE_ORDER.map(g => {
              const pct = (counts[g] / total) * 100
              if (pct === 0) return null
              return (
                <div
                  key={g}
                  className={`${gradeStyle(g).bar} transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${g}: ${counts[g]}`}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-5">
        {GRADE_ORDER.map(g => (
          <div key={g} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${gradeStyle(g).dot}`} />
            <span className="text-xs text-stone-500">
              <span className="font-semibold text-stone-700">{g}</span>
              {" "}{counts[g]}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Top playbooks strip ──────────────────────────────────────────────────────

function TopPlaybooksStrip({ playbooks }: { playbooks: TopPlaybook[] }) {
  if (playbooks.length === 0) return null
  return (
    <div>
      <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest mb-2">Top rated</p>
      <div className="flex flex-wrap gap-2">
        {playbooks.map(p => {
          const s = gradeStyle(p.grade)
          return (
            <div
              key={p.slug}
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 ${s.bg} border-transparent`}
            >
              <span className={`text-xs font-bold ${s.text}`}>{p.grade}</span>
              <span className="text-xs font-mono text-stone-700">{p.slug}</span>
              <span className="text-[11px] text-stone-400">{p.pct.toFixed(0)}%</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Quality table ────────────────────────────────────────────────────────────

function QualityTable({ playbooks }: { playbooks: PlaybookEval[] }) {
  const sorted = [...playbooks].sort((a, b) => {
    const order = { A: 0, B: 1, C: 2, D: 3, F: 4 }
    return (order[a.grade as keyof typeof order] ?? 5) - (order[b.grade as keyof typeof order] ?? 5)
  })

  if (sorted.length === 0) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white px-6 py-12 text-center">
        <p className="text-sm text-stone-400">No playbook evals available yet.</p>
        <p className="text-xs text-stone-300 mt-1">Run evals against your installed playbooks to populate this table.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-100 text-left">
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Playbook</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Grade</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400">Pass rate</th>
            <th className="px-4 py-3 text-xs font-medium text-stone-400 text-right">Failing criteria</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(p => (
            <tr key={p.slug} className="border-b border-stone-100 last:border-0 hover:bg-stone-50 transition-colors">
              <td className="px-4 py-3">
                <span className="font-mono text-xs text-stone-700 bg-stone-100 px-2 py-0.5 rounded">
                  {p.slug}
                </span>
              </td>
              <td className="px-4 py-3">
                <GradeBadge grade={p.grade} />
              </td>
              <td className="px-4 py-3">
                <PassBar pct={p.pct} />
              </td>
              <td className="px-4 py-3 text-right">
                {p.failing_criteria > 0 ? (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                    {p.failing_criteria}
                    {p.total_criteria > 0 && (
                      <span className="text-stone-400 font-normal"> / {p.total_criteria}</span>
                    )}
                  </span>
                ) : (
                  <span className="text-xs text-emerald-600 font-medium">All passing</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-32 rounded-xl bg-stone-100 animate-pulse" />
      <div className="h-48 rounded-xl bg-stone-100 animate-pulse" />
    </div>
  )
}

// ─── Page content ─────────────────────────────────────────────────────────────

function EvalContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [summary, setSummary] = useState<EvalSummary | null>(null)
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

        const [summaryRes, playbooksRes] = await Promise.all([
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/eval/summary`, { headers }),
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/eval/playbooks`, { headers }),
        ])

        if (cancelled) return

        if (!summaryRes.ok && !playbooksRes.ok) {
          setError("Could not load eval data.")
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
  }, [])

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-10">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Evals</h1>
            <p className="text-xs text-stone-400 mt-0.5">Playbook quality grades and failing criteria</p>
          </div>
        </div>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <div className="rounded-xl border border-red-100 bg-red-50 px-5 py-4">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        ) : (
          <div className="space-y-8">

            {/* Grade distribution card */}
            {summary && (
              <section>
                <GradeDistributionCard counts={summary.grade_counts} />
                {summary.top_playbooks.length > 0 && (
                  <div className="mt-4">
                    <TopPlaybooksStrip playbooks={summary.top_playbooks} />
                  </div>
                )}
              </section>
            )}

            {/* Per-playbook quality table */}
            <section>
              <div className="flex items-center justify-between mb-3">
                <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-widest">
                  Playbook quality
                </p>
                <p className="text-xs text-stone-300">{playbooks.length} playbook{playbooks.length === 1 ? "" : "s"}</p>
              </div>
              <QualityTable playbooks={playbooks} />
            </section>

          </div>
        )}
      </div>
    </AppShell>
  )
}

// ─── Auth wrapper ─────────────────────────────────────────────────────────────

function EvalWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
  if (!isLoaded) return null
  return <EvalContent getToken={getToken} />
}

export default function EvalPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <EvalWithAuth />
  return <EvalContent getToken={null} />
}
