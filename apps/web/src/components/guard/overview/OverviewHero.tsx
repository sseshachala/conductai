"use client"

// OverviewHero — four primary Guard surfaces at the top of /theguard.
// The daily loop lands here: Live Activity → Inbox → Controls → Agents.
// Everything else on the Overview page is relegated below this row.
//
// Owns its own inbox-count fetch so the tile can render even when the
// parent page hasn't loaded everything. All other counts are received
// as props from GuardDashboard — the parent already fetches them for
// the "More metrics" grid, so this avoids duplicate calls.

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import type { AuthFetch } from "@/lib/api"
import { guardInbox } from "@/lib/api"

// ─── Types ────────────────────────────────────────────────────────────────

type Tone = "accent" | "ok" | "warn" | "err" | "plain"

interface CoverageRow {
  mcp_registered?: string[]
  hook_registered?: string[]
}

export interface OverviewHeroProps {
  authFetch: AuthFetch
  teamId: string | null
  loading: boolean
  eventsToday: number
  blockedToday: number
  warnedToday: number
  agentPolicies: number | null
  proxyPolicies: number | null
  toolCoverage: CoverageRow[]
}

// ─── Tile primitive ───────────────────────────────────────────────────────

const TONE_COLOR: Record<Tone, string> = {
  accent: "var(--accent-text)",
  ok:     "var(--ok)",
  warn:   "var(--warn)",
  err:    "var(--err)",
  plain:  "var(--text)",
}

function HeroTile({
  title,
  value,
  sub,
  tone = "plain",
}: {
  title: string
  value: number | string
  sub?: React.ReactNode
  tone?: Tone
}) {
  return (
    <div className="card" style={{ padding: "18px 20px", cursor: "pointer", height: "100%" }}>
      <div style={{
        fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5,
        color: "var(--text-muted)", marginBottom: 8, fontWeight: 600,
      }}>
        {title}
      </div>
      <div style={{
        fontSize: 34, fontWeight: 700, letterSpacing: "-.02em",
        color: TONE_COLOR[tone], lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ─── Inbox count hook ─────────────────────────────────────────────────────

function useInboxCounts(authFetch: AuthFetch, teamId: string | null) {
  const [counts, setCounts] = useState<{ open: number; triaging: number } | null>(null)

  const load = useCallback(async () => {
    if (!teamId) return
    try {
      const rows = await guardInbox.list(authFetch, { limit: 500 })
      setCounts({
        open:     rows.filter(r => r.status === "open").length,
        triaging: rows.filter(r => r.status === "triaging").length,
      })
    } catch {
      // Non-fatal — hero tile shows "—" instead
    }
  }, [authFetch, teamId])

  useEffect(() => { void load() }, [load])

  return counts
}

// ─── Component ────────────────────────────────────────────────────────────

export function OverviewHero({
  authFetch,
  teamId,
  loading,
  eventsToday,
  blockedToday,
  warnedToday,
  agentPolicies,
  proxyPolicies,
  toolCoverage,
}: OverviewHeroProps) {
  const inboxCounts = useInboxCounts(authFetch, teamId)

  const coveredDevs = toolCoverage.filter(
    d => (d.mcp_registered?.length ?? 0) + (d.hook_registered?.length ?? 0) > 0,
  ).length

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      gap: 12,
      marginBottom: 20,
    }}>
      <Link href="/logs/guard" style={{ textDecoration: "none" }}>
        <HeroTile
          title="Live Activity"
          value={loading ? "—" : eventsToday.toLocaleString()}
          sub={loading ? "loading…" : `${blockedToday} blocked · ${warnedToday} warned today`}
          tone={blockedToday > 0 ? "err" : "ok"}
        />
      </Link>
      <Link href="/theguard/inbox" style={{ textDecoration: "none" }}>
        <HeroTile
          title="Inbox"
          value={inboxCounts == null ? "—" : inboxCounts.open}
          sub={inboxCounts == null ? "loading…" : `${inboxCounts.triaging} triaging · click to resolve`}
          tone={inboxCounts != null && inboxCounts.open > 0 ? "warn" : "ok"}
        />
      </Link>
      <Link href="/theguard/policies" style={{ textDecoration: "none" }}>
        <HeroTile
          title="Controls"
          value={
            agentPolicies == null && proxyPolicies == null
              ? "—"
              : (agentPolicies ?? 0) + (proxyPolicies ?? 0)
          }
          sub={
            agentPolicies == null && proxyPolicies == null
              ? "loading…"
              : `${agentPolicies ?? 0} agent · ${proxyPolicies ?? 0} proxy`
          }
          tone="plain"
        />
      </Link>
      <Link href="/theguard/discovery" style={{ textDecoration: "none" }}>
        <HeroTile
          title="Agents Discovered"
          value={toolCoverage.length}
          sub={
            toolCoverage.length === 0
              ? "run discovery to populate"
              : `${coveredDevs}/${toolCoverage.length} under Guard`
          }
          tone={toolCoverage.length === 0 ? "plain" : "ok"}
        />
      </Link>
    </div>
  )
}
