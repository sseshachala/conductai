"use client"

// Guard · Spend → Configure tab.
//
// The dashboard/metric surface that used to live here moved to
// /theguard/spend/glance (peer of Overview on /theguard). This tab
// is now focused on setting budgets + caps + alert thresholds.

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { GuardSectionTabs, SPEND_TABS } from "@/features/guard/GuardSectionTabs"
import { SpendControlsPanel } from "@/features/guard/spend/components"
import { useSpendState } from "@/features/guard/spend/useSpendState"

export default function SpendPage() {
  return <AppShell><SpendConfigureContent /></AppShell>
}

function SpendConfigureContent() {
  const router = useRouter()
  const s = useSpendState()

  // Viewers with no spend access still bounce to /theguard. Matches the
  // pre-split behavior.
  useEffect(() => {
    if (!s.roleLoading && !s.canViewSpend) router.replace("/theguard")
  }, [s.roleLoading, s.canViewSpend, router])

  if (!s.roleLoading && !s.canViewSpend) {
    return (
      <GuardShell lastFetched={s.lastUpdated}>
        <GuardSectionTabs tabs={SPEND_TABS} />
        <div className="card" style={{ padding: "64px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          You don&apos;t have access to spend data. Contact your admin.
        </div>
      </GuardShell>
    )
  }

  return (
    <GuardShell lastFetched={s.lastUpdated}>
      <GuardSectionTabs tabs={SPEND_TABS} />

      {s.error && (
        <div style={{
          borderRadius: 8,
          background: "var(--err-bg)",
          border: "1px solid var(--err-bd)",
          padding: "10px 16px",
          fontSize: 13,
          color: "var(--err)",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <span style={{ flex: 1 }}>{s.error}</span>
          <button
            onClick={s.load}
            style={{ fontSize: 12, fontWeight: 600, background: "var(--err)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 12px", cursor: "pointer", flexShrink: 0 }}
          >
            Retry
          </button>
        </div>
      )}

      {s.data === null && s.loading ? (
        <div className="card" style={{ height: 200, opacity: 0.5, marginBottom: 22 }} />
      ) : (
        <SpendControlsPanel
          settings={s.teamSettings}
          onSave={s.saveTeamSettings}
          currency={s.currency}
          readOnly={!s.isAdmin}
          totalCostUsd={s.data?.total_cost_usd ?? 0}
        />
      )}
    </GuardShell>
  )
}
