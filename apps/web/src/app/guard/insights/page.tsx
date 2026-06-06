"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardSavings } from "@/hooks/useGuardSavings"
import AppShell from "@/components/AppShell"
import GuardNav from "@/components/guard/GuardNav"

// ─── Types ────────────────────────────────────────────────────────────────────

interface AuditEvent {
  id: string
  ts: string
  user_email: string | null
  ai_tool: string
  tool_call: string
  input_summary: string | null
  decision: string
  rule_id: string | null
  rule_message: string | null
  tokens_before: number | null
  tokens_after: number | null
  cost_usd_after: number | null
}

interface DeveloperTool {
  user_email: string
  detected_tools: string[]
  mcp_registered: string[]
  hook_registered: string[]
  reported_at: string
}

interface SavingsSummary {
  team_total: {
    rtk_saved_tokens: number
    rtk_saved_usd: number
    booster_saved_tokens: number
    booster_saved_usd: number
  }
  by_developer: {
    member_email: string
    rtk_saved_tokens: number
    booster_saved_tokens: number
    rtk_saved_usd: number
    booster_saved_usd: number
  }[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number, decimals = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function fmtK(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

const DECISION_COLOR: Record<string, string> = {
  blocked: "var(--err, #dc2626)",
  warned:  "var(--warn, #d97706)",
  allowed: "var(--ok, #16a34a)",
  approval:"var(--info, #2563eb)",
}

const DECISION_BG: Record<string, string> = {
  blocked: "#fef2f2",
  warned:  "#fffbeb",
  allowed: "#f0fdf4",
  approval:"#eff6ff",
}

function DecisionPill({ decision }: { decision: string }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "2px 7px", borderRadius: 99,
      color: DECISION_COLOR[decision] ?? "var(--text-3)",
      background: DECISION_BG[decision] ?? "var(--surface-3)",
      textTransform: "uppercase", letterSpacing: ".04em",
    }}>
      {decision}
    </span>
  )
}

function StatCard({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: string }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 160, borderTop: `2.5px solid ${tone ?? "var(--border)"}` }}>
      <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function GuardInsightsPage() {
  const { getToken } = useAuth()
  const { teamId, loading: teamLoading, error: teamError } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const { savings, loading: savingsLoading } = useGuardSavings(teamId)

  const [events, setEvents]     = useState<AuditEvent[]>([])
  const [devTools, setDevTools] = useState<DeveloperTool[]>([])
  const [loading, setLoading]   = useState(true)
  const [period, setPeriod]     = useState<"7d" | "30d">("7d")

  const load = useCallback(async () => {
    if (!teamId) return
    setLoading(true)
    try {
      const token = await getToken()
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""

      const days = period === "7d" ? 7 : 30
      const since = new Date(Date.now() - days * 86400_000).toISOString()

      const [evRes, dtRes] = await Promise.all([
        fetch(`${base}/guard/events?workspace_id=${teamId}&limit=50&since=${since}`, { headers }),
        fetch(`${base}/guard/developer-tools?workspace_id=${teamId}`, { headers }),
      ])

      if (evRes.ok) setEvents(await evRes.json())
      if (dtRes.ok) setDevTools(await dtRes.json())
    } finally {
      setLoading(false)
    }
  }, [getToken, teamId, period])

  useEffect(() => { load() }, [load])

  // ── Derived stats ────────────────────────────────────────────────────────────
  const totalCalls   = events.length
  const blocks       = events.filter(e => e.decision === "blocked")
  const blockCount   = blocks.length
  const activeDevs   = new Set(events.map(e => e.user_email).filter(Boolean)).size
  const totalSaved   = savings
    ? (savings.team_total.rtk_saved_usd + savings.team_total.booster_saved_usd)
    : 0
  const totalSavedTok = savings
    ? (savings.team_total.rtk_saved_tokens + savings.team_total.booster_saved_tokens)
    : 0

  const coveredCount = devTools.filter(d => d.hook_registered?.length > 0).length
  const uncovered    = devTools.filter(d => !d.hook_registered?.length)

  return (
    <AppShell>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 24px 48px" }}>
        <GuardNav />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "24px 0 20px" }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, color: "var(--text)" }}>Insights</h1>
            <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-3)" }}>
              Guard activity, developer coverage, and token savings
            </p>
          </div>
          <select
            value={period}
            onChange={e => setPeriod(e.target.value as "7d" | "30d")}
            style={{ fontSize: 12, padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </div>

        {/* ── Not installed ──────────────────────────────────────────────── */}
        {!teamLoading && (teamError || !teamId) && (
          <div style={{ marginTop: 40, textAlign: "center", color: "var(--text-3)", fontSize: 14 }}>
            Guard not set up for this workspace.
          </div>
        )}

        {/* ── Section 1: KPIs ────────────────────────────────────────────── */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 28 }}>
          <StatCard label="Tool calls" value={fmtK(totalCalls)} tone="var(--info, #2563eb)" />
          <StatCard
            label="Blocks"
            value={blockCount}
            sub={totalCalls > 0 ? `${((blockCount / totalCalls) * 100).toFixed(1)}% block rate` : undefined}
            tone={blockCount > 0 ? "var(--err, #dc2626)" : "var(--ok, #16a34a)"}
          />
          <StatCard label="Active developers" value={activeDevs} tone="var(--border)" />
          <StatCard
            label="Est. savings"
            value={savingsLoading ? "…" : `$${fmt(totalSaved)}`}
            sub={savingsLoading ? undefined : `${fmtK(totalSavedTok)} tokens`}
            tone="var(--ok, #16a34a)"
          />
        </div>

        {/* ── Section 2: Activity feed ────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 28 }}>

          {/* Blocks */}
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Recent blocks</span>
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>{blockCount} in period</span>
            </div>
            {loading ? (
              <div style={{ padding: 24, color: "var(--text-3)", fontSize: 13 }}>Loading…</div>
            ) : blocks.length === 0 ? (
              <div style={{ padding: 24, color: "var(--text-3)", fontSize: 13 }}>No blocks in this period</div>
            ) : (
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {blocks.slice(0, 20).map(e => (
                  <div key={e.id} style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 3 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", fontFamily: "monospace" }}>{e.tool_call}</span>
                      <span style={{ fontSize: 10, color: "var(--text-3)" }}>{new Date(e.ts).toLocaleTimeString()}</span>
                    </div>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <DecisionPill decision={e.decision} />
                      {e.rule_id && <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "monospace" }}>{e.rule_id}</span>}
                    </div>
                    {e.input_summary && (
                      <div style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.input_summary}</div>
                    )}
                    {e.user_email && (
                      <div style={{ fontSize: 10, color: "var(--text-3)" }}>{e.user_email}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* All events by decision breakdown */}
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>All activity</span>
            </div>
            {loading ? (
              <div style={{ padding: 24, color: "var(--text-3)", fontSize: 13 }}>Loading…</div>
            ) : events.length === 0 ? (
              <div style={{ padding: 24, color: "var(--text-3)", fontSize: 13 }}>No activity in this period</div>
            ) : (
              <div style={{ maxHeight: 320, overflowY: "auto" }}>
                {events.slice(0, 20).map(e => (
                  <div key={e.id} style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 3, borderRadius: 2, alignSelf: "stretch", background: DECISION_COLOR[e.decision] ?? "var(--border)", flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", fontFamily: "monospace" }}>{e.tool_call}</span>
                        <DecisionPill decision={e.decision} />
                      </div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 2 }}>
                        {e.user_email ?? "—"} · {new Date(e.ts).toLocaleString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Section 3: Developer coverage ───────────────────────────────── */}
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Developer coverage</span>
            <span style={{ fontSize: 11, color: coveredCount === devTools.length ? "var(--ok)" : "var(--warn)" }}>
              {coveredCount}/{devTools.length} covered
            </span>
          </div>
          {devTools.length === 0 ? (
            <div style={{ padding: 24, color: "var(--text-3)", fontSize: 13 }}>No developer data yet</div>
          ) : (
            <>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    {["Developer", "AI tools detected", "Hook installed", "MCP registered"].map(h => (
                      <th key={h} style={{ padding: "8px 16px", textAlign: "left", fontWeight: 600, color: "var(--text-3)", fontSize: 11 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {devTools.map(d => {
                    const hookOk = d.hook_registered?.length > 0
                    const mcpOk  = d.mcp_registered?.length > 0
                    return (
                      <tr key={d.user_email} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "10px 16px", color: "var(--text)", fontWeight: 500 }}>{d.user_email}</td>
                        <td style={{ padding: "10px 16px", color: "var(--text-3)" }}>{d.detected_tools?.join(", ") || "—"}</td>
                        <td style={{ padding: "10px 16px" }}>
                          <span style={{ color: hookOk ? "var(--ok)" : "var(--err)", fontWeight: 600 }}>{hookOk ? "✓" : "✗"}</span>
                          {!hookOk && <span style={{ color: "var(--text-3)", fontSize: 10, marginLeft: 6 }}>run conductguard sync</span>}
                        </td>
                        <td style={{ padding: "10px 16px" }}>
                          <span style={{ color: mcpOk ? "var(--ok)" : "var(--text-3)", fontWeight: 600 }}>{mcpOk ? "✓" : "—"}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {uncovered.length > 0 && (
                <div style={{ padding: "10px 16px", background: "var(--warn-bg, #fffbeb)", borderTop: "1px solid var(--warn-bd, #fde68a)", fontSize: 12, color: "var(--warn, #d97706)" }}>
                  {uncovered.length} developer{uncovered.length > 1 ? "s" : ""} without Guard hook — ask them to run: <code style={{ fontFamily: "monospace" }}>conductguard sync</code>
                </div>
              )}
            </>
          )}
        </div>

      </div>
    </AppShell>
  )
}
