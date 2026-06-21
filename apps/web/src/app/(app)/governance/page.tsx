"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
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

interface FrameworkRow {
  framework: string
  rules_count: number
  controls: string[]
  packs: string[]
}

interface BonusFrameworkRow extends FrameworkRow {
  recommended_pack: string | null
}

interface FrameworksOut {
  installed: FrameworkRow[]
  bonus: BonusFrameworkRow[]
  total_rules: number
  rules_with_framework: number
}

interface NarrativeOut {
  paragraph: string
  generated_at: string
  source: "template" | "llm"
}

// Friendly display names for known framework prefixes.
const FRAMEWORK_LABEL: Record<string, string> = {
  SOC2: "SOC 2",
  ISO_42001: "ISO 42001",
  ISO_27001: "ISO 27001",
  EU_AI_ACT: "EU AI Act",
  GDPR: "GDPR",
  HIPAA: "HIPAA",
  PCI_DSS: "PCI DSS",
  OWASP: "OWASP Top 10",
  NIST: "NIST AI RMF",
  NIS2: "NIS 2",
  DORA: "DORA",
}

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
  const [frameworks, setFrameworks] = useState<FrameworksOut | null>(null)
  const [narrative, setNarrative] = useState<NarrativeOut | null>(null)
  const [activeFramework, setActiveFramework] = useState<string | null>(null)

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

      try {
        const res = await fetch(`${base}/governance/frameworks?workspace_id=${workspaceId}`, { headers })
        if (res.ok && !cancelled) {
          const data: FrameworksOut = await res.json()
          setFrameworks(data)
          if (!activeFramework) {
            const first = data.installed[0] || data.bonus[0]
            if (first) setActiveFramework(first.framework)
          }
        }
      } catch { /* non-fatal */ }

      try {
        const res = await fetch(`${base}/governance/narrative?workspace_id=${workspaceId}`, { headers })
        if (res.ok && !cancelled) setNarrative(await res.json())
      } catch { /* non-fatal */ }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, getToken, activeFramework])

  const { savings } = useGuardSavings(workspaceId)
  const totalSavedUsd = savings
    ? (savings.team_total.rtk_saved_usd || 0) + (savings.team_total.booster_saved_usd || 0)
    : 0

  const allFwRows: (FrameworkRow | BonusFrameworkRow)[] =
    frameworks ? [...frameworks.installed, ...frameworks.bonus] : []
  const activeFwRow = allFwRows.find(f => f.framework === activeFramework) || null

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

        {/* Narrative strip — template-generated (LLM upgrade in Phase 2) */}
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
            {narrative?.paragraph ?? "Loading summary…"}
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

        {/* Framework matrix */}
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 18,
          background: "var(--surface-1)",
          marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)" }}>
              Framework coverage
            </div>
            {frameworks && (
              <div style={{ fontSize: 11, color: "var(--text-3)" }}>
                {frameworks.rules_with_framework} of {frameworks.total_rules} rules tagged
              </div>
            )}
          </div>

          {!frameworks || (frameworks.installed.length === 0 && frameworks.bonus.length === 0) ? (
            <div style={{ fontSize: 13, color: "var(--text-3)" }}>
              No frameworks covered yet. Install a compliance pack from the marketplace to start.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              {/* Tier 1 — frameworks with a dedicated installed pack */}
              {frameworks.installed.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 8 }}>
                    Installed frameworks
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {frameworks.installed.map(fw => {
                      const isActive = fw.framework === activeFramework
                      return (
                        <button
                          key={fw.framework}
                          onClick={() => setActiveFramework(fw.framework)}
                          style={{
                            padding: "10px 14px",
                            borderRadius: 8,
                            border: `1px solid ${isActive ? "var(--accent-text)" : "var(--border)"}`,
                            background: isActive ? "var(--accent-weak)" : "var(--surface-2)",
                            color: isActive ? "var(--accent-text)" : "var(--text-1)",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: isActive ? 600 : 500,
                          }}
                        >
                          {FRAMEWORK_LABEL[fw.framework] ?? fw.framework}
                          <span style={{ marginLeft: 8, fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)" }}>
                            {fw.rules_count} {fw.rules_count === 1 ? "rule" : "rules"}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Tier 2 — bonus / cross-coverage from installed packs */}
              {frameworks.bonus.length > 0 && (
                <div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                      Bonus coverage
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text-3)" }}>
                      cross-tagged rules from your installed packs
                    </span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {frameworks.bonus.map(fw => {
                      const isActive = fw.framework === activeFramework
                      return (
                        <button
                          key={fw.framework}
                          onClick={() => setActiveFramework(fw.framework)}
                          style={{
                            padding: "10px 14px",
                            borderRadius: 8,
                            border: `1px dashed ${isActive ? "var(--accent-text)" : "var(--border)"}`,
                            background: isActive ? "var(--accent-weak)" : "var(--surface-1)",
                            color: isActive ? "var(--accent-text)" : "var(--text-2)",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: isActive ? 600 : 500,
                          }}
                        >
                          {FRAMEWORK_LABEL[fw.framework] ?? fw.framework}
                          <span style={{ marginLeft: 8, fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)" }}>
                            {fw.rules_count} {fw.rules_count === 1 ? "rule" : "rules"}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Per-control drill-down */}
        {activeFwRow && (
          <section style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 18,
            background: "var(--surface-1)",
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 12 }}>
              {FRAMEWORK_LABEL[activeFwRow.framework] ?? activeFwRow.framework} controls
            </div>
            {activeFwRow.controls.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-3)" }}>
                No specific controls tagged — this framework matches at the pack level only.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
                {activeFwRow.controls.map(ctrl => (
                  <div key={ctrl} style={{
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "10px 12px",
                    background: "var(--surface-2)",
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-1)" }}>{ctrl}</div>
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>covered</div>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-muted)" }}>
              Source packs: {activeFwRow.packs.join(", ")}
            </div>
            {(() => {
              const rec = (activeFwRow as BonusFrameworkRow).recommended_pack
              if (!rec) return null
              const label = FRAMEWORK_LABEL[activeFwRow.framework] ?? activeFwRow.framework
              return (
                <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-2)" }}>
                  Want dedicated {label} controls?{" "}
                  <Link href="/marketplace" style={{ color: "var(--accent-text)", textDecoration: "underline" }}>
                    Install {rec}
                  </Link>
                </div>
              )
            })()}
          </section>
        )}
      </div>
    </AppShell>
  )
}
