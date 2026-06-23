"use client"

import { useEffect, useState } from "react"
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

interface KpiValue {
  value: number
  avg_7d: number | null
  delta_pct: number | null
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
  const [activeControl, setActiveControl] = useState<string | null>(null)
  const [controlDrill, setControlDrill] = useState<ControlDrillOut | null>(null)
  const [drillLoading, setDrillLoading] = useState(false)
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([])
  const [kpis, setKpis] = useState<KpisOut | null>(null)
  const [eventFilter, setEventFilter] = useState<"" | "blocked" | "warned">("")

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
        if (res.ok && !cancelled) setRecentEvents(await res.json())
      } catch { /* non-fatal */ }

      try {
        const res = await fetch(`${base}/governance/kpis?workspace_id=${workspaceId}`, { headers })
        if (res.ok && !cancelled) setKpis(await res.json())
      } catch { /* non-fatal */ }
    }
    load()
    return () => { cancelled = true }
  }, [workspaceId, getToken, activeFramework, eventFilter, narrativePeriod])

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
          <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-2)", margin: 0 }}>
            {narrative?.paragraph ?? "Loading summary…"}
          </p>
        </section>

        {/* KPI cards */}
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
                              href={`/guard/activity?rule_id=${encodeURIComponent(r.rule_id)}`}
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
                          <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-muted)" }}>
                            from <Link href={`/marketplace/${r.pack_slug}`} style={{ color: "var(--accent-text)", textDecoration: "none" }}>{r.pack_slug}</Link>
                          </div>
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
              href={eventFilter ? `/guard/activity?decision=${eventFilter}` : "/guard/activity"}
              style={{ fontSize: 11, color: "var(--accent-text)" }}
            >
              View all →
            </Link>
          </div>
          {recentEvents.length === 0 ? (
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
      </div>
    </AppShell>
  )
}
