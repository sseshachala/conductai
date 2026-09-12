"use client"

// Guard · Spend → Configure tab.
//
// Focused on setting budgets + caps + alert thresholds. Currency +
// month picker sit at the top so the budget's progress bar reflects
// the picked month (e.g. "how are we tracking against the $5k budget
// for October?") without leaving the tab.
//
// Metric-surface view (currency, stat cards, savings, by-dev, by-tool)
// lives in-page on /theguard as the "Spend at a glance" view.

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { GuardSectionTabs, SPEND_TABS } from "@/features/guard/GuardSectionTabs"
import { MonthPicker, SpendControlsPanel } from "@/features/guard/spend/components"
import type { Currency } from "@/features/guard/spend/shared"
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

      {/* Currency + month picker — wired to useSpendState so switching
          the month re-fetches spend for that period and the budget
          progress bar reflects it. */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, marginBottom: 20 }}>
        <select
          value={s.currency}
          onChange={e => s.setCurrency(e.target.value as Currency)}
          style={{
            fontSize: 12,
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "5px 10px",
            color: "var(--text-3)",
            background: "var(--surface)",
            outline: "none",
            cursor: "pointer",
          }}
        >
          <option value="USD">$ USD</option>
          <option value="EUR">€ EUR</option>
          <option value="INR">₹ INR</option>
        </select>
        <MonthPicker value={s.month} onChange={s.setMonth} />
      </div>

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
