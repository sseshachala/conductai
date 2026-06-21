"use client"

import { useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardSavings } from "@/hooks/useGuardSavings"

interface SpendStats {
  active_developers: number
  events_today: number
  blocked_today: number
  tokens_saved_today: number
}

interface InstalledPacksResponse { installed: string[] }

function KpiCard({ label, value, sub, tone = "neutral" }: {
  label: string
  value: string
  sub?: string
  tone?: "neutral" | "good" | "warn"
}) {
  const valueColor =
    tone === "good" ? "var(--accent-text)" :
    tone === "warn" ? "var(--text-1)" : "var(--text-1)"
  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "14px 16px",
      background: "var(--surface-1)",
    }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 600, color: valueColor, marginTop: 6 }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{sub ?? "\u00a0"}</div>
    </div>
  )
}

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(0)}`

const fmtInt = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`

export default function GovernancePage() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const { getToken } = useAuth()
  const [stats, setStats] = useState<SpendStats | null>(null)
  const [installedPacks, setInstalledPacks] = useState<string[]>([])

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    const load = async () => {
      const token = await getToken()
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""

      try {
        const res = await fetch(`${base}/guard/spend?workspace_id=${workspaceId}`, { headers })
        if (res.ok && !cancelled) setStats(await res.json())
      } catch { /* non-fatal */ }

      try {
        const res = await fetch(`${base}/compliance/packs/installed?workspace_id=${workspaceId}`, { headers })
        if (res.ok && !cancelled) {
          const data: InstalledPacksResponse = await res.json()
          setInstalledPacks(Array.isArray(data?.installed) ? data.installed : [])
        }
      } catch { /* non-fatal */ }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, getToken])

  const { savings } = useGuardSavings(workspaceId)
  const totalSavedUsd = savings
    ? (savings.team_total.rtk_saved_usd || 0) + (savings.team_total.booster_saved_usd || 0)
    : 0

  return (
    <AppShell>
      <div style={{ padding: "24px 28px", maxWidth: 1280, margin: "0 auto" }}>
        <header style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, color: "var(--text-1)" }}>
            Governance
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: "4px 0 0" }}>
            One outcome surface for engineering, security, and finance — ROI, behavioral insights, compliance proof.
          </p>
        </header>

        {/* AI Narrative Strip — placeholder, real LLM-generated paragraph lands in 750e */}
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "16px 18px",
          background: "var(--surface-2)",
          marginBottom: 20,
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>
            This week in plain English
          </div>
          <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-2)", margin: 0 }}>
            Narrative summary not yet generated. The daily LLM job will fill this in once analytics data is flowing.
          </p>
        </section>

        {/* KPI cards */}
        <section style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          <KpiCard
            label="AI ROI"
            value={savings ? fmtUsd(totalSavedUsd) : "—"}
            sub={savings ? "saved via RTK + Booster" : "tooling savings pending"}
            tone={totalSavedUsd > 0 ? "good" : "neutral"}
          />
          <KpiCard
            label="AI activity today"
            value={stats ? fmtInt(stats.events_today) : "—"}
            sub={stats ? `${stats.active_developers} active developers` : "no data yet"}
          />
          <KpiCard
            label="Risk intercepted today"
            value={stats ? fmtInt(stats.blocked_today) : "—"}
            sub={stats && stats.blocked_today > 0 ? "blocks + warnings" : "no incidents"}
            tone={stats && stats.blocked_today > 0 ? "warn" : "neutral"}
          />
          <KpiCard
            label="Compliance packs"
            value={`${installedPacks.length}`}
            sub={installedPacks.length > 0 ? "frameworks covered" : "install packs to start coverage"}
            tone={installedPacks.length > 0 ? "good" : "neutral"}
          />
        </section>

        {/* Framework matrix — placeholder, real data lands in 750c */}
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 18,
          background: "var(--surface-1)",
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 12 }}>
            Framework coverage
          </div>
          <div style={{ fontSize: 13, color: "var(--text-3)" }}>
            Multi-framework matrix renders here once rules are installed and the `/governance/frameworks` endpoint ships (750c).
          </div>
        </section>
      </div>
    </AppShell>
  )
}
