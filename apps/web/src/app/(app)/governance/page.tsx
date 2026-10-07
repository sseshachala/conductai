"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import type {
  SpendStats, InstalledPacksResponse, FrameworkRow, BonusFrameworkRow, FrameworksOut, NarrativeOut,
  ControlDrillOut, RecentEvent, CertificationOut, ChainVerifyOut, KpisOut,
} from "./_components/types"
import { KpiCard, fmtUsd, Skeleton, fmtInt } from "./_components/ui"
import { HeroBanner } from "./_components/HeroBanner"
import { FrameworkMatrix } from "./_components/FrameworkMatrix"
import { ControlDrillDown } from "./_components/ControlDrillDown"
import { RecentActivitySection, AuditIntegritySection } from "./_components/ActivitySections"

export default function GovernancePage() {
  const { activeWorkspace } = useWorkspace()
  const { authFetch } = useAuthFetch()
  const workspaceId = activeWorkspace?.id ?? null
  const [stats, setStats] = useState<SpendStats | null>(null)
  const [installedPacks, setInstalledPacks] = useState<string[]>([])
  const [frameworks, setFrameworks] = useState<FrameworksOut | null>(null)
  const [narrative, setNarrative] = useState<NarrativeOut | null>(null)
  const [narrativePeriod, setNarrativePeriod] = useState<"week" | "month">("week")
  const [activeFramework, setActiveFramework] = useState<string | null>(null)
  const [expandedRule, setExpandedRule] = useState<string | null>(null)
  const [activeControl, setActiveControl] = useState<string | null>(null)
  const [controlDrill, setControlDrill] = useState<ControlDrillOut | null>(null)
  const [drillLoading, setDrillLoading] = useState(false)
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([])
  const [recentLoaded, setRecentLoaded] = useState(false)
  const [kpis, setKpis] = useState<KpisOut | null>(null)
  const [eventFilter, setEventFilter] = useState<"" | "blocked" | "warned">("")
  // Live auto-refresh — Phase 1B governance polling
  const [tick, setTick] = useState(0)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)
  const [chain, setChain] = useState<ChainVerifyOut | null>(null)
  const [chainLoading, setChainLoading] = useState(false)
  const [certifications, setCertifications] = useState<CertificationOut[]>([])
  const [certifying, setCertifying] = useState<string | null>(null)

  // 60s auto-refresh — bumps tick which triggers the data useEffects below
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    const load = async () => {
      try {
        const res = await authFetch(`${API}/guard/spend?workspace_id=${workspaceId}`)
        if (res.ok && !cancelled) setStats(await res.json())
      } catch { /* non-fatal */ }

      try {
        const res = await authFetch(`${API}/compliance/packs/installed?workspace_id=${workspaceId}`)
        if (res.ok && !cancelled) {
          const data: InstalledPacksResponse = await res.json()
          setInstalledPacks(Array.isArray(data?.installed) ? data.installed : [])
        }
      } catch { /* non-fatal */ }

      try {
        const res = await authFetch(`${API}/governance/frameworks?workspace_id=${workspaceId}`)
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
        const res = await authFetch(`${API}/governance/narrative?workspace_id=${workspaceId}&period=${narrativePeriod}`)
        if (res.ok && !cancelled) setNarrative(await res.json())
      } catch { /* non-fatal */ }

      try {
        const filterParam = eventFilter ? `&decision=${eventFilter}` : ""
        const res = await authFetch(`${API}/governance/events/recent?workspace_id=${workspaceId}&limit=15${filterParam}`)
        if (res.ok && !cancelled) {
          setRecentEvents(await res.json())
          setRecentLoaded(true)
        }
      } catch { /* non-fatal */ }

      try {
        const res = await authFetch(`${API}/governance/kpis?workspace_id=${workspaceId}`)
        if (res.ok && !cancelled) setKpis(await res.json())
      } catch { /* non-fatal */ }

      if (!cancelled) setLastFetched(new Date())
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, authFetch, activeFramework, eventFilter, narrativePeriod, tick])

  // Certifications — only reload when installed packs change, not every 60s tick.
  useEffect(() => {
    if (!workspaceId || installedPacks.length === 0) return
    let cancelled = false
    const load = async () => {
      try {
        const res = await authFetch(`${API}/governance/certifications?workspace_id=${workspaceId}`)
        if (res.ok && !cancelled) setCertifications(await res.json())
      } catch { /* non-fatal */ }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, authFetch, installedPacks])

  // Fetch the rules covering the selected control whenever it changes.
  useEffect(() => {
    if (!workspaceId || !activeFramework || !activeControl) {
      setControlDrill(null)
      return
    }
    let cancelled = false
    const load = async () => {
      setDrillLoading(true)
      try {
        const res = await authFetch(
          `${API}/governance/frameworks/${activeFramework}/controls/${activeControl}/rules?workspace_id=${workspaceId}`
        )
        if (res.ok && !cancelled) setControlDrill(await res.json())
      } catch { /* non-fatal */ } finally {
        if (!cancelled) setDrillLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, authFetch, activeFramework, activeControl])

  const verifyChain = useCallback(async () => {
    if (!workspaceId) return
    setChainLoading(true)
    try {
      const res = await authFetch(`${API}/guard/verify/chain?workspace_id=${workspaceId}`)
      if (res.ok) setChain(await res.json())
    } finally {
      setChainLoading(false)
    }
  }, [workspaceId, authFetch])

  const certMap = Object.fromEntries(certifications.map(c => [c.pack_slug, c]))

  const doCertify = async (packSlug: string) => {
    if (!workspaceId) return
    setCertifying(packSlug)
    try {
      const res = await authFetch(`${API}/governance/certify?workspace_id=${workspaceId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pack_slug: packSlug }),
      })
      if (res.ok) {
        const fresh = await authFetch(`${API}/governance/certifications?workspace_id=${workspaceId}`)
        if (fresh.ok) setCertifications(await fresh.json())
      }
    } finally {
      setCertifying(null)
    }
  }

  const allFwRows: (FrameworkRow | BonusFrameworkRow)[] =
    frameworks ? [...frameworks.installed, ...frameworks.bonus] : []
  const activeFwRow = allFwRows.find(f => f.framework === activeFramework) || null

  return (
    <AppShell>
      <style>{`@keyframes conduct-skel { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }`}</style>
      <div style={{ padding: "24px 28px", maxWidth: 1280, margin: "0 auto" }}>
        <header style={{ marginBottom: 24, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, color: "var(--text-1)" }}>
              Runtime Governance
            </h1>
            <p style={{ fontSize: 13, color: "var(--text-3)", margin: "4px 0 0" }}>
              Certify your delegation policies, not just individual events. Who authorised this agent to act. Under what rules. What it did. Runtime admissibility states are logged at the execution boundary — every decision is custody proof, not a reconstruction.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-3)", paddingTop: 4 }}>
            <span className="conduct-pulse-dot" style={{ background: "var(--ok)" }} />
            <span>Auto-refresh · every 60s</span>
            {lastFetched && (
              <span style={{ color: "var(--text-muted)" }}>
                · updated {lastFetched.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>
        </header>

        {/* Hero status banner — dominates the screenshot */}
        {(!kpis && !frameworks) ? (
          <section style={{
            display: "flex", alignItems: "center", gap: 16,
            padding: "20px 22px", borderRadius: 12,
            border: "1px solid var(--border)", background: "var(--surface-2)", marginBottom: 20,
          }}>
            <Skeleton height={44} width={44} radius={10} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
              <Skeleton height={20} width="55%" />
              <Skeleton height={12} width="35%" />
            </div>
            <Skeleton height={36} width={120} radius={8} />
          </section>
        ) : (
          <HeroBanner kpis={kpis} frameworks={frameworks} />
        )}

        {/* Narrative strip — template-generated (LLM upgrade in Phase 2) */}
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "16px 18px",
          background: "var(--surface-2)",
          marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6, gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
              This {narrativePeriod} in plain English
            </div>
            <div style={{ display: "inline-flex", padding: 2, borderRadius: 9999, background: "var(--surface-3)", border: "1px solid var(--border)" }}>
              {(["week", "month"] as const).map(p => {
                const active = narrativePeriod === p
                return (
                  <button
                    key={p}
                    onClick={() => setNarrativePeriod(p)}
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "3px 12px",
                      borderRadius: 9999,
                      border: "none",
                      background: active ? "var(--accent)" : "transparent",
                      color: active ? "#fff" : "var(--text-muted)",
                      cursor: active ? "default" : "pointer",
                      textTransform: "capitalize",
                    }}
                  >
                    {p}
                  </button>
                )
              })}
            </div>
          </div>
          {narrative ? (
            <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-2)", margin: 0 }}>
              {narrative.paragraph}
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Skeleton height={14} width="92%" />
              <Skeleton height={14} width="78%" />
            </div>
          )}
        </section>

        {/* KPI cards */}
        {!kpis && !stats ? (
          <section style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
            {[0, 1, 2, 3].map(i => (
              <div key={i} style={{ padding: "16px 18px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface-1)", display: "flex", flexDirection: "column", gap: 10 }}>
                <Skeleton height={11} width="55%" />
                <Skeleton height={28} width="40%" />
                <Skeleton height={11} width="80%" />
              </div>
            ))}
          </section>
        ) : (
        <section style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          <KpiCard
            label="Guard ROI (month-to-date)"
            value={kpis ? fmtUsd(kpis.risk_avoided_usd_mtd) : "—"}
            sub={
              kpis && kpis.blocks_mtd > 0
                ? `${fmtInt(kpis.blocks_mtd)} risk events intercepted`
                : "no risk events intercepted yet"
            }
            tone={kpis && kpis.risk_avoided_usd_mtd > 0 ? "good" : "neutral"}
          />
          <KpiCard
            label="AI activity today"
            value={stats ? fmtInt(stats.events_today) : "—"}
            sub={
              kpis?.events_today.avg_7d != null
                ? `${stats?.active_developers ?? 0} active developers · 7d avg ${fmtInt(Math.round(kpis.events_today.avg_7d))}`
                : stats ? `${stats.active_developers} active developers` : "no data yet"
            }
            delta={kpis?.events_today.delta_pct ?? null}
            deltaSemantic="neutral"
          />
          <KpiCard
            label="Risk intercepted today"
            value={stats ? fmtInt(stats.blocked_today) : "—"}
            sub={
              kpis?.blocked_today.avg_7d != null
                ? `blocks · 7d avg ${kpis.blocked_today.avg_7d.toFixed(1)}`
                : stats && stats.blocked_today > 0 ? "blocks + warnings" : "no incidents"
            }
            tone={stats && stats.blocked_today > 0 ? "warn" : "neutral"}
            delta={kpis?.blocked_today.delta_pct ?? null}
            deltaSemantic="more_is_better"
          />
          <KpiCard
            label="Installed packs"
            value={`${installedPacks.length}`}
            sub={installedPacks.length > 0 ? "installed compliance packs" : "install packs to start coverage"}
            tone={installedPacks.length > 0 ? "good" : "neutral"}
          />
        </section>
        )}

        {/* Policy certification panel — issue #911 */}
        {installedPacks.length > 0 && (
          <section style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 18,
            background: "var(--surface-1)",
            marginBottom: 20,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 4 }}>
              Policy certification
            </div>
            <p style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 14px" }}>
              Quarterly review: certify that each delegation policy was reviewed and approved. Overdue after 90 days.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {installedPacks.map(slug => {
                const cert = certMap[slug]
                const certDate = cert ? new Date(cert.certified_at) : null
                const daysSince = certDate ? Math.floor((Date.now() - certDate.getTime()) / 86_400_000) : null
                const overdue = daysSince === null || daysSince > 90
                return (
                  <div key={slug} style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "10px 14px",
                    borderRadius: 8,
                    border: `1px solid ${overdue ? "var(--warn-bd, var(--border))" : "var(--ok-bd, var(--border))"}`,
                    background: overdue ? "var(--warn-bg, var(--surface-2))" : "var(--ok-bg, var(--surface-2))",
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>{slug}</div>
                      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>
                        {cert
                          ? `Last certified ${daysSince === 0 ? "today" : `${daysSince}d ago`} · ${cert.certified_by.startsWith("user_") ? "unknown user" : cert.certified_by}`
                          : "Never certified"}
                        {overdue && <span style={{ color: "var(--warn, #b45309)", marginLeft: 8 }}>⚠ overdue</span>}
                      </div>
                    </div>
                    <button
                      onClick={() => doCertify(slug)}
                      disabled={certifying === slug}
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: "6px 14px",
                        borderRadius: 6,
                        border: "1px solid var(--accent)",
                        background: "var(--accent)",
                        color: "#fff",
                        cursor: certifying === slug ? "wait" : "pointer",
                        opacity: certifying === slug ? 0.6 : 1,
                        flexShrink: 0,
                      }}
                    >
                      {certifying === slug ? "Certifying…" : "Certify"}
                    </button>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* Framework matrix */}
        <FrameworkMatrix
          frameworks={frameworks}
          activeFramework={activeFramework}
          setActiveFramework={setActiveFramework}
          certMap={certMap}
        />

        {/* Per-control drill-down */}
        {activeFwRow && (
          <ControlDrillDown
            activeFwRow={activeFwRow}
            activeControl={activeControl}
            setActiveControl={setActiveControl}
            controlDrill={controlDrill}
            drillLoading={drillLoading}
            expandedRule={expandedRule}
            setExpandedRule={setExpandedRule}
            frameworks={frameworks}
          />
        )}

        {/* Recent activity feed — top 6, same row component as /guard/activity */}
        <RecentActivitySection
          eventFilter={eventFilter}
          setEventFilter={setEventFilter}
          recentLoaded={recentLoaded}
          recentEvents={recentEvents}
        />
        {/* Audit log integrity */}
        <AuditIntegritySection chain={chain} chainLoading={chainLoading} verifyChain={verifyChain} />
      </div>
    </AppShell>
  )
}
