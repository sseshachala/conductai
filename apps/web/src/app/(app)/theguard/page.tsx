"use client"

import Link from "next/link"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { OverviewHero } from "@/components/guard/overview/OverviewHero"
import { SpendGlance } from "@/features/guard/spend/SpendGlance"
import { CostTrendChart, ByToolTable } from "./_components/widgets"
import { useGuardDashboard } from "./_components/useGuardDashboard"
import { MetricsSection } from "./_components/MetricsSection"
import { ActivityFeedSection } from "./_components/ActivityFeedSection"


export default function GuardPage() {
  return <AppShell><GuardDashboard /></AppShell>
}

function GuardDashboard() {
  const s = useGuardDashboard()
  const {
    authFetch,
    teamId,
    teamLoading,
    permissions,
    permissionsLoading,
    events,
    stats,
    loading,
    live,
    lastUpdated,
    chartToken,
    agentCount,
    proxyCount,
    trialSession,
    view,
    setView,
    derivedStats,
    blockedToday,
  } = s

  if (!teamLoading && !teamId) {
    return (
      <GuardShell live={false} lastFetched={null}>
        <div style={{
          marginTop: 48,
          padding: "32px 24px",
          borderRadius: 12,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          textAlign: "center",
          maxWidth: 480,
          marginLeft: "auto",
          marginRight: "auto",
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>
            Guard is not set up for your organization.
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 20, lineHeight: 1.6 }}>
            Ask your workspace admin to run `conduct guard install` to get started.
          </p>
          <Link
            href="/settings/modules"
            style={{
              display: "inline-block",
              fontSize: 13,
              fontWeight: 600,
              padding: "8px 20px",
              borderRadius: 8,
              background: "var(--accent)",
              color: "var(--on-accent, #fff)",
              textDecoration: "none",
            }}
          >
            Go to Settings → Modules
          </Link>
        </div>
      </GuardShell>
    )
  }

  return (
    <GuardShell live={live} lastFetched={lastUpdated} agentCount={agentCount} proxyCount={proxyCount}>

      {/* #1567 empty-state CTA — new workspaces land on Try Guard in one click */}
      {!loading && trialSession && !trialSession.ineligible && !trialSession.expired && trialSession.cap_used === 0 && (
        <div style={{
          borderRadius: 8,
          border: "1px solid var(--brand-bd, #0f766e)",
          background: "var(--brand-bg, #ecfdf5)",
          padding: "12px 16px",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--brand-text, #064e3b)" }}>
              New here? See Guard allow, warn, block, and prove — in 30 seconds.
            </div>
            <div style={{ fontSize: 12, color: "var(--brand-text-2, #065f46)" }}>
              {trialSession.setup_required
                ? "A deployment administrator needs to configure the demo provider."
                : "Uses a 7-day trial identity. No personal provider key needed."}
            </div>
          </div>
          <Link
            href="/theguard/try"
            style={{
              fontSize: 13,
              fontWeight: 600,
              padding: "6px 14px",
              borderRadius: 6,
              background: "var(--brand-fg, #0f766e)",
              color: "white",
              textDecoration: "none",
            }}
          >
            Try Guard
          </Link>
        </div>
      )}

      {/* Viewer-scoped notice */}
      {!loading && !permissionsLoading && !permissions.canViewAllActivity && (
        <div style={{
          borderRadius: 8,
          border: "1px solid var(--warn-bd)",
          background: "var(--warn-bg)",
          padding: "10px 16px",
          fontSize: 12,
          color: "var(--warn)",
          marginBottom: 16,
        }}>
          You can view your own activity only. Contact your admin to request broader access.
        </div>
      )}

      {/* ── View toggle — in-page tabs: Overview | Spend at a glance ── */}
      {/* Insights was retired here; Spend at a glance replaces it with the
          Spend metric surface (currency + month picker + stat cards +
          savings + by-dev / by-tool tables). No URL change — stays on
          /theguard for context. */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ display: "flex", background: "var(--surface-3)", borderRadius: 8, padding: 3 }}>
          {(["overview", "spend_glance"] as const).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              style={{
                border: "none",
                background: view === v ? "var(--inverse)" : "transparent",
                color: view === v ? "var(--on-inverse)" : "var(--text-3)",
                fontSize: 12,
                fontWeight: 600,
                padding: "5px 14px",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              {v === "overview" ? "Overview" : "Spend at a glance"}
            </button>
          ))}
        </div>
      </div>

      {view === "spend_glance" && <SpendGlance />}

      {/* ── Overview ───────────────────────────────────────────────────────── */}
      {view === "overview" && <>

      <OverviewHero
        authFetch={authFetch}
        teamId={teamId}
        loading={loading}
        eventsToday={stats?.events_today ?? derivedStats.events_today}
        blockedToday={blockedToday}
        warnedToday={derivedStats.warned_today}
        agentPolicies={agentCount}
        proxyPolicies={proxyCount}
      />

      {/* Everything below is legacy secondary — spend, sessions, tokens saved,
          tool coverage table, cost chart. Kept for continuity; kept below the
          hero so the daily loop lands on the four primary surfaces first. */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, marginBottom: 12,
        fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-muted)",
      }}>
        <span>More metrics</span>
        <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </div>

      <MetricsSection s={s} />

      {/* Cost trend chart */}
      {!loading && teamId && (
        <CostTrendChart
          workspaceId={teamId}
          token={chartToken}
        />
      )}

      {/* By AI tool table */}
      {!loading && events.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <ByToolTable events={events} />
        </div>
      )}

      <ActivityFeedSection s={s} />

      </>}


    </GuardShell>
  )
}
