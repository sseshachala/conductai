"use client"

import { apiUrl } from "@/lib/auth/runtime"
import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import { getEdition, playbookDisplayName } from "@/lib/benchmark-editions"
import { CriteriaSection } from "./CriteriaSection"
import { ScenarioCoverage } from "./ScenarioCoverage"
import { ScoreCard } from "./ScoreCard"
import { type BaselinePlaybook, type EditionManifest, type PlaybookLiveDetail, type ScenarioSet } from "./helpers"

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

export function DeepDiveContent({
  editionSlug,
  playbookSlug,
  getToken,
  workspaceId,
}: {
  editionSlug: string
  playbookSlug: string
  getToken: (() => Promise<string | null>) | null
  workspaceId?: string | null
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

      const base = apiUrl()
      const headers: Record<string, string> = {}

      try {
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
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

        // Edition manifest (required, need baseline score)
        if (editionRes) {
          if (!editionRes.ok) {
            const status = editionRes.status
            setError(
              status === 401 ? "Not authorised, check your session." :
              status === 403 ? "Forbidden, workspace role insufficient." :
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

        // Scenarios (optional, not all playbooks have multi-scenario fixtures)
        if (scenariosRes?.ok) {
          setScenarios(await scenariosRes.json())
        }

        // Current criteria breakdown (optional, show if available)
        if (liveRes?.ok) {
          setLive(await liveRes.json())
        }

      } catch {
        if (!cancelled) setError("Network error, could not reach the API.")
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
