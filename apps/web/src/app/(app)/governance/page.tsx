"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { ActivityRow, ActivityHeader } from "@/components/guard/ActivityRow"

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

interface RuleDrillRow {
  rule_id: string
  description: string | null
  action: string
  severity: string | null
  pack_slug: string
  match_tool: string | null
  match_pattern: string | null
  match_path_pattern: string | null
  recommendation: string | null
  iso_control: string | null
  frameworks: string[]
  events_30d: number
}

interface ControlDrillOut {
  framework: string
  control: string | null
  rules: RuleDrillRow[]
}

interface RecentEvent {
  id: string
  ts: string
  decision: string
  rule_id: string | null
  ai_tool: string
  tool_call: string
  user_email: string | null
  input_summary: string | null
}

interface CertificationOut {
  id: string
  pack_slug: string
  certified_by: string
  policy_version: string | null
  certified_at: string
}

interface KpiValue {
  value: number
  avg_7d: number | null
  delta_pct: number | null
}

interface ChainVerifyOut {
  valid: boolean
  events_checked: number
  broken_at: string | null
  first_event: string | null
  last_event: string | null
  verified_at: string
}

interface KpisOut {
  events_today: KpiValue
  blocked_today: KpiValue
  active_developers_today: KpiValue
  risk_avoided_usd_mtd: number
  blocks_mtd: number
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

function KpiCard({ label, value, sub, tone = "neutral", delta, deltaSemantic = "neutral" }: {
  label: string
  value: string
  sub?: string
  tone?: "neutral" | "good" | "warn"
  delta?: number | null              // signed % vs baseline; null/undefined hides
  deltaSemantic?: "neutral" | "more_is_better" | "less_is_better"
}) {
  const valueColor =
    tone === "good" ? "var(--accent-text)" :
    tone === "warn" ? "var(--text-1)" : "var(--text-1)"

  // Color the delta arrow based on direction + semantic.
  let deltaColor = "var(--text-3)"
  if (typeof delta === "number" && delta !== 0) {
    if (deltaSemantic === "more_is_better") {
      deltaColor = delta > 0 ? "#16a34a" : "#dc2626"
    } else if (deltaSemantic === "less_is_better") {
      deltaColor = delta > 0 ? "#dc2626" : "#16a34a"
    }
  }

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "14px 16px",
      background: "var(--surface-1)",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 6 }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>
          {label}
        </div>
        {typeof delta === "number" && (
          <span title="vs 7-day average" style={{ fontSize: 11, fontWeight: 600, color: deltaColor }}>
            {delta > 0 ? "↑" : delta < 0 ? "↓" : "—"} {Math.abs(delta)}%
          </span>
        )}
      </div>
      <div style={{ fontSize: 24, fontWeight: 600, color: valueColor, marginTop: 6 }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{sub ?? "\u00a0"}</div>
    </div>
  )
}

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(0)}`

// Reusable shimmer skeleton — for progressive section loads.
function Skeleton({ height = 14, width = "100%", radius = 6, style }: { height?: number | string; width?: number | string; radius?: number; style?: React.CSSProperties }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-block",
        height: typeof height === "number" ? `${height}px` : height,
        width: typeof width === "number" ? `${width}px` : width,
        borderRadius: radius,
        background: "linear-gradient(90deg, var(--surface-2) 0%, var(--surface-3, var(--border)) 50%, var(--surface-2) 100%)",
        backgroundSize: "200% 100%",
        animation: "conduct-skel 1.4s ease-in-out infinite",
        ...style,
      }}
    />
  )
}

// Format a drilled rule as YAML for inline preview.
function formatRuleYaml(r: {
  rule_id: string
  description?: string | null
  action: string
  severity?: string | null
  match_tool?: string | null
  match_pattern?: string | null
  match_path_pattern?: string | null
  recommendation?: string | null
  iso_control?: string | null
  frameworks?: string[]
  pack_slug: string
}): string {
  const yq = (v: string) => /[:#\-?{}\[\],&*!|>'"%@`]/.test(v) || v.includes("  ") ? JSON.stringify(v) : v
  const lines: string[] = []
  lines.push(`- id: ${r.rule_id}`)
  if (r.description) lines.push(`  description: ${yq(r.description)}`)
  lines.push(`  action: ${r.action}`)
  if (r.severity) lines.push(`  severity: ${r.severity}`)
  if (r.match_tool) lines.push(`  match_tool: ${r.match_tool}`)
  if (r.match_pattern) lines.push(`  match_pattern: ${yq(r.match_pattern)}`)
  if (r.match_path_pattern) lines.push(`  match_path_pattern: ${yq(r.match_path_pattern)}`)
  if (r.frameworks && r.frameworks.length > 0) {
    lines.push(`  frameworks:`)
    for (const f of r.frameworks) lines.push(`    - ${f}`)
  }
  if (r.iso_control) lines.push(`  iso_control: ${r.iso_control}`)
  if (r.recommendation) lines.push(`  recommendation: ${yq(r.recommendation)}`)
  lines.push(`  pack: ${r.pack_slug}`)
  return lines.join("\n")
}

const fmtInt = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`

const DECISION_COLOR: Record<string, string> = {
  blocked: "#dc2626",
  warned: "#d97706",
  audited: "#2563eb",
  allowed: "#16a34a",
  approval: "#7c3aed",
}

function DecisionDot({ decision }: { decision: string }) {
  const color = DECISION_COLOR[decision] ?? "#6b7280"
  return (
    <span title={decision} style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      fontSize: 11,
      fontWeight: 600,
      color,
      textTransform: "capitalize",
    }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
      {decision}
    </span>
  )
}

function timeAgo(iso: string): string {
  try {
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return ""
    const delta = Math.max(0, Date.now() - t)
    const m = Math.floor(delta / 60000)
    if (m < 1) return "just now"
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    const d = Math.floor(h / 24)
    return `${d}d ago`
  } catch {
    return ""
  }
}

export default function GovernancePage() {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const { getToken } = useAuth()
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
        const res = await fetch(`${base}/governance/narrative?workspace_id=${workspaceId}&period=${narrativePeriod}`, { headers })
        if (res.ok && !cancelled) setNarrative(await res.json())
      } catch { /* non-fatal */ }

      try {
        const filterParam = eventFilter ? `&decision=${eventFilter}` : ""
        const res = await fetch(`${base}/governance/events/recent?workspace_id=${workspaceId}&limit=15${filterParam}`, { headers })
        if (res.ok && !cancelled) {
          setRecentEvents(await res.json())
          setRecentLoaded(true)
        }
      } catch { /* non-fatal */ }

      try {
        const res = await fetch(`${base}/governance/kpis?workspace_id=${workspaceId}`, { headers })
        if (res.ok && !cancelled) setKpis(await res.json())
      } catch { /* non-fatal */ }

      if (!cancelled) setLastFetched(new Date())
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, getToken, activeFramework, eventFilter, narrativePeriod, tick])

  // Certifications — only reload when installed packs change, not every 60s tick.
  useEffect(() => {
    if (!workspaceId || installedPacks.length === 0) return
    let cancelled = false
    const load = async () => {
      const token = await getToken()
      const hdrs: Record<string, string> = {}
      if (token) hdrs["Authorization"] = `Bearer ${token}`
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? ""
      try {
        const res = await fetch(`${apiBase}/governance/certifications?workspace_id=${workspaceId}`, { headers: hdrs })
        if (res.ok && !cancelled) setCertifications(await res.json())
      } catch { /* non-fatal */ }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, getToken, installedPacks])

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
        const token = await getToken()
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        const base = process.env.NEXT_PUBLIC_API_URL ?? ""
        const res = await fetch(
          `${base}/governance/frameworks/${activeFramework}/controls/${activeControl}/rules?workspace_id=${workspaceId}`,
          { headers },
        )
        if (res.ok && !cancelled) setControlDrill(await res.json())
      } catch { /* non-fatal */ } finally {
        if (!cancelled) setDrillLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, getToken, activeFramework, activeControl])

  const verifyChain = useCallback(async () => {
    if (!workspaceId) return
    setChainLoading(true)
    try {
      const token = await getToken()
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await fetch(`${base}/guard/verify/chain?workspace_id=${workspaceId}`, { headers })
      if (res.ok) setChain(await res.json())
    } finally {
      setChainLoading(false)
    }
  }, [workspaceId, getToken])

  const certMap = Object.fromEntries(certifications.map(c => [c.pack_slug, c]))

  const doCertify = async (packSlug: string) => {
    if (!workspaceId) return
    setCertifying(packSlug)
    try {
      const token = await getToken()
      const hdrs: Record<string, string> = { "Content-Type": "application/json" }
      if (token) hdrs["Authorization"] = `Bearer ${token}`
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await fetch(`${apiBase}/governance/certify?workspace_id=${workspaceId}`, {
        method: "POST",
        headers: hdrs,
        body: JSON.stringify({ pack_slug: packSlug }),
      })
      if (res.ok) {
        const fresh = await fetch(`${apiBase}/governance/certifications?workspace_id=${workspaceId}`, { headers: hdrs })
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
              Governance
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
        ) : (() => {
          const installedCount = frameworks?.installed.length ?? 0
          const bonusCount = frameworks?.bonus.length ?? 0
          const totalFrameworks = installedCount + bonusCount
          const totalRules = (frameworks?.installed ?? []).reduce((s, f) => s + f.rules_count, 0)
            + (frameworks?.bonus ?? []).reduce((s, f) => s + f.rules_count, 0)
          const blocksMtd = kpis?.blocks_mtd ?? 0
          const riskAvoidedUsd = kpis?.risk_avoided_usd_mtd ?? 0

          let tone: "good" | "warn" | "info" = "good"
          let title = "All systems compliant"
          let sub = `${totalRules} policies live across ${totalFrameworks} framework${totalFrameworks === 1 ? "" : "s"}`
          let action: { label: string; href: string } | null = null

          if (totalFrameworks === 0) {
            tone = "info"
            title = "No compliance frameworks active"
            sub = "Install a pack from the marketplace to start coverage"
            action = { label: "Browse Marketplace →", href: "/marketplace" }
          } else if (blocksMtd > 0) {
            tone = "warn"
            title = `${blocksMtd.toLocaleString()} risk event${blocksMtd === 1 ? "" : "s"} intercepted this month`
            sub = `~${fmtUsd(riskAvoidedUsd)} risk avoided · ${totalRules} policies live across ${totalFrameworks} framework${totalFrameworks === 1 ? "" : "s"}`
            action = { label: "View Activity →", href: "/theguard/activity?decision=blocked" }
          }

          const colors = {
            good: { bg: "var(--ok-bg)",  border: "var(--ok-bd)",  text: "var(--ok)",  iconBg: "var(--ok)" },
            warn: { bg: "var(--accent-weak)", border: "var(--accent)", text: "var(--accent)", iconBg: "var(--accent)" },
            info: { bg: "var(--info-bg)", border: "var(--info-bd)", text: "var(--info)", iconBg: "var(--info)" },
          }[tone]

          return (
            <section style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              padding: "20px 22px",
              borderRadius: 12,
              border: `1.5px solid ${colors.border}`,
              background: colors.bg,
              marginBottom: 20,
            }}>
              <span style={{
                width: 44,
                height: 44,
                borderRadius: 10,
                background: colors.iconBg,
                color: "#fff",
                display: "grid",
                placeItems: "center",
                flexShrink: 0,
              }}>
                {tone === "good" ? (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : tone === "warn" ? (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    <polyline points="9 12 11 14 15 10" />
                  </svg>
                ) : (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                )}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 19, fontWeight: 700, color: colors.text, letterSpacing: "-0.01em", lineHeight: 1.2 }}>
                  {title}
                </div>
                <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 4 }}>
                  {sub}
                </div>
              </div>
              {action && (
                <a href={action.href} style={{
                  fontSize: 13,
                  fontWeight: 600,
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: `1px solid ${colors.border}`,
                  background: "var(--surface)",
                  color: colors.text,
                  textDecoration: "none",
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}>
                  {action.label}
                </a>
              )}
            </section>
          )
        })()}

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
                ? `${fmtInt(kpis.blocks_mtd)} risk events intercepted · industry avg $15K each`
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
            label="Compliance packs"
            value={`${installedPacks.length}`}
            sub={installedPacks.length > 0 ? "frameworks covered" : "install packs to start coverage"}
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

          {!frameworks ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {[120, 145, 100, 130, 110].map((w, i) => (
                <Skeleton key={i} height={56} width={w} radius={8} />
              ))}
            </div>
          ) : (frameworks.installed.length === 0 && frameworks.bonus.length === 0) ? (
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
                      const packCert = fw.packs.map(p => certMap[p]).find(Boolean)
                      const certLabel = packCert
                        ? `certified ${Math.floor((Date.now() - new Date(packCert.certified_at).getTime()) / 86_400_000)}d ago`
                        : null
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
                            textAlign: "left",
                          }}
                        >
                          {FRAMEWORK_LABEL[fw.framework] ?? fw.framework}
                          <span style={{ marginLeft: 8, fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)" }}>
                            {fw.rules_count} {fw.rules_count === 1 ? "rule" : "rules"}
                          </span>
                          {certLabel && (
                            <span style={{ display: "block", fontSize: 10, color: "var(--ok, #16a34a)", marginTop: 2 }}>
                              ✓ {certLabel}
                            </span>
                          )}
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
              <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
                {activeFwRow.controls.map(ctrl => {
                  const isActive = ctrl === activeControl
                  return (
                    <button
                      key={ctrl}
                      onClick={() => setActiveControl(isActive ? null : ctrl)}
                      style={{
                        textAlign: "left",
                        border: `1px solid ${isActive ? "var(--accent-text)" : "var(--border)"}`,
                        borderRadius: 6,
                        padding: "10px 12px",
                        background: isActive ? "var(--accent-weak)" : "var(--surface-2)",
                        color: isActive ? "var(--accent-text)" : "var(--text-1)",
                        cursor: "pointer",
                        fontFamily: "inherit",
                      }}
                    >
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{ctrl}</div>
                      <div style={{ fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)", marginTop: 2 }}>
                        {isActive ? "showing rules ↓" : "covered · click to view rules"}
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Drill-down: rules covering the selected control */}
              {activeControl && (
                <div style={{ marginTop: 16, padding: "14px 16px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)" }}>
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                      Rules covering {activeFwRow.framework}: {activeControl}
                    </div>
                    {controlDrill && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {controlDrill.rules.length} {controlDrill.rules.length === 1 ? "rule" : "rules"}
                      </div>
                    )}
                  </div>
                  {drillLoading && (
                    <div style={{ fontSize: 12, color: "var(--text-3)" }}>Loading rules…</div>
                  )}
                  {!drillLoading && controlDrill && controlDrill.rules.length === 0 && (
                    <div style={{ fontSize: 12, color: "var(--text-3)" }}>No rules cover this control yet.</div>
                  )}
                  {!drillLoading && controlDrill && controlDrill.rules.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {controlDrill.rules.map(r => (
                        <div key={r.rule_id} style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px 12px" }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                              <Link href={`/marketplace/${r.pack_slug}`} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", textDecoration: "none" }}>
                                {r.rule_id}
                              </Link>
                              <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "var(--surface-2)", color: "var(--text-2)", textTransform: "uppercase", fontWeight: 600 }}>
                                {r.action}
                              </span>
                              {r.severity && (
                                <span style={{ fontSize: 10, color: "var(--text-3)" }}>severity: {r.severity}</span>
                              )}
                            </div>
                            <Link
                              href={`/theguard/activity?rule_id=${encodeURIComponent(r.rule_id)}`}
                              style={{ fontSize: 11, color: "var(--accent-text)", whiteSpace: "nowrap" }}
                            >
                              {r.events_30d} {r.events_30d === 1 ? "event" : "events"} · 30d →
                            </Link>
                          </div>
                          {r.description && (
                            <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-2)" }}>{r.description}</div>
                          )}
                          {(r.match_tool || r.match_pattern) && (
                            <div style={{ marginTop: 4, fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono, ui-monospace, monospace)" }}>
                              {r.match_tool && <span>tool: {r.match_tool}</span>}
                              {r.match_tool && r.match_pattern && <span> · </span>}
                              {r.match_pattern && <span style={{ wordBreak: "break-all" }}>{r.match_pattern}</span>}
                            </div>
                          )}
                          <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-muted)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span>from <Link href={`/marketplace/${r.pack_slug}`} style={{ color: "var(--accent-text)", textDecoration: "none" }}>{r.pack_slug}</Link></span>
                            <button
                              type="button"
                              onClick={() => setExpandedRule(expandedRule === r.rule_id ? null : r.rule_id)}
                              style={{ fontSize: 10, fontWeight: 600, color: "var(--accent-text)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                            >
                              {expandedRule === r.rule_id ? "hide YAML ↑" : "show YAML ↓"}
                            </button>
                          </div>
                          {expandedRule === r.rule_id && (
                            <pre style={{
                              marginTop: 8,
                              padding: "10px 12px",
                              background: "var(--surface-3, #0d0d10)",
                              color: "var(--text-1)",
                              border: "1px solid var(--border)",
                              borderRadius: 6,
                              fontFamily: "ui-monospace, monospace",
                              fontSize: 11,
                              lineHeight: 1.55,
                              overflowX: "auto",
                              whiteSpace: "pre",
                            }}>{formatRuleYaml(r)}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              </>
            )}
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-muted)" }}>
              Source packs: {activeFwRow.packs.join(", ")}
            </div>
            {(() => {
              // Only render CTA when the active framework is a "bonus" one — i.e. its
              // dedicated pack isn't installed. Installed-tier frameworks already get
              // dedicated coverage so no CTA is needed.
              const isBonus = frameworks?.bonus.some(b => b.framework === activeFwRow.framework)
              if (!isBonus) return null
              const rec = (activeFwRow as BonusFrameworkRow).recommended_pack
              const label = FRAMEWORK_LABEL[activeFwRow.framework] ?? activeFwRow.framework
              if (rec) {
                return (
                  <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-2)" }}>
                    Want dedicated {label} controls?{" "}
                    <Link href={`/marketplace/${rec}`} style={{ color: "var(--accent-text)", textDecoration: "underline" }}>
                      Install {rec}
                    </Link>
                  </div>
                )
              }
              return (
                <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}>
                  Dedicated {label} pack — <em>coming soon</em>. Currently covered via cross-tagged rules from your installed packs.
                </div>
              )
            })()}
          </section>
        )}

        {/* Recent activity feed — top 6, same row component as /guard/activity */}
        <section style={{
          marginTop: 20,
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "var(--surface-1)",
          overflow: "hidden",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid var(--border)", gap: 12, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)" }}>Recent activity</div>
              <div style={{ display: "flex", gap: 4 }}>
                {([
                  { key: "", label: "All" },
                  { key: "blocked", label: "Blocked" },
                  { key: "warned", label: "Warned" },
                ] as const).map(chip => {
                  const active = eventFilter === chip.key
                  return (
                    <button
                      key={chip.key || "all"}
                      onClick={() => setEventFilter(chip.key as typeof eventFilter)}
                      style={{
                        fontSize: 11,
                        fontWeight: active ? 600 : 500,
                        padding: "3px 10px",
                        borderRadius: 12,
                        border: `1px solid ${active ? "var(--accent-text)" : "var(--border)"}`,
                        background: active ? "var(--accent-weak)" : "transparent",
                        color: active ? "var(--accent-text)" : "var(--text-2)",
                        cursor: "pointer",
                      }}
                    >
                      {chip.label}
                    </button>
                  )
                })}
              </div>
            </div>
            <Link
              href={eventFilter ? `/theguard/activity?decision=${eventFilter}` : "/theguard/activity"}
              style={{ fontSize: 11, color: "var(--accent-text)" }}
            >
              View all →
            </Link>
          </div>
          {!recentLoaded ? (
            <div style={{ padding: "8px 18px 14px" }}>
              {[0, 1, 2, 3, 4, 5].map(i => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: i < 5 ? "1px solid var(--border)" : "none" }}>
                  <Skeleton height={12} width={70} />
                  <Skeleton height={12} width={90} />
                  <Skeleton height={12} width={120} />
                  <Skeleton height={12} width="40%" />
                </div>
              ))}
            </div>
          ) : recentEvents.length === 0 ? (
            <div style={{ padding: "14px 18px", fontSize: 12, color: "var(--text-3)" }}>
              No events yet. Activity will appear here as your team uses AI tools.
            </div>
          ) : (
            <>
              <ActivityHeader />
              {recentEvents.slice(0, 6).map((ev, i, arr) => (
                <ActivityRow key={ev.id} ev={ev} isLast={i === arr.length - 1} />
              ))}
            </>
          )}
        </section>
        {/* Audit log integrity */}
        <section style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 18, background: "var(--surface-1)", marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 4 }}>Audit log integrity</div>
              {chain ? (
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: chain.valid ? "var(--ok)" : "var(--err)", display: "inline-block", flexShrink: 0 }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: chain.valid ? "var(--ok)" : "var(--err)" }}>
                    {chain.valid ? "Chain intact" : "Chain broken"}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                    {chain.events_checked.toLocaleString()} events verified
                    {chain.first_event && chain.last_event && (
                      <> · {new Date(chain.first_event).toLocaleDateString()} – {new Date(chain.last_event).toLocaleDateString()}</>
                    )}
                  </span>
                  {!chain.valid && chain.broken_at && (
                    <span style={{ fontSize: 12, color: "var(--err)" }}>First broken link: {new Date(chain.broken_at).toLocaleString()}</span>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-3)" }}>
                  SHA-256 chain links every audit event to the previous one — custody proof at the execution boundary. Click to confirm the log has not been altered and that every Governance Authorization Artifact is intact.
                </div>
              )}
            </div>
            <button onClick={verifyChain} disabled={chainLoading} className="btn btn-sm" style={{ flexShrink: 0 }}>
              {chainLoading ? "Verifying…" : chain ? "Re-verify" : "Verify integrity"}
            </button>
          </div>
        </section>
      </div>
    </AppShell>
  )
}
