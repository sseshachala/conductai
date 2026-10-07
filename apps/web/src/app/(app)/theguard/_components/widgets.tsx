"use client"

import { useEffect, useState, useMemo } from "react"
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts"
import { API } from "@/lib/api/client"
import type { GuardSavingsSummary } from "@/hooks/useGuardSavings"
import { ByAiToolTable, type ByAiToolRow } from "@/components/guard/ByAiToolTable"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface GuardEvent {
  id: string
  user_email: string | null
  ai_tool: string
  tool_call: string | null
  source?: string | null
  provider?: string | null
  model?: string | null
  conductai_run_id?: string | null
  conductai_workflow?: string | null
  conductai_workflow_id?: string | null
  input_summary: string | null
  decision: "allowed" | "blocked" | "warned" | "approval"
  rule_id: string | null
  rule_message: string | null
  tokens_before: number | null
  tokens_after: number | null
  tokens_saved: number | null
  tokens_input: number | null
  tokens_output: number | null
  cost_usd_after: number | null
  execution_status?: "success" | "error" | "timeout" | null
  result_summary?: string | null
  ts: string
}

export interface SpendStats {
  active_developers: number
  events_today: number
  blocked_today: number
  tokens_saved_today: number
  sessions: number
  hook_sessions: number
}

export interface ToolCoverageRow {
  email: string
  detected_tools: string[]
  mcp_registered: string[]
  hook_registered: string[]
  reported_at: string
}

export interface GuardSessionRow {
  id: string
  user_email: string | null
  ai_tool: string
  started_at: string | null
  event_count: number
  violations_count: number
  client_ip: string | null
  os_info: string | null
  hostname: string | null
}

// ─── Constants ────────────────────────────────────────────────────────────────

export const AI_TOOL_BADGES: Record<string, { label: string; bg: string; color: string }> = {
  claude_code:    { label: "Claude Code",    bg: "var(--accent-weak)",           color: "var(--accent-text)"  },
  claude_chat:    { label: "Claude.ai",      bg: "var(--accent-weak)",           color: "var(--accent-text)"  },
  claude_desktop: { label: "Claude Desktop", bg: "var(--accent-weak)",           color: "var(--accent-text)"  },
  claude_work:    { label: "Claude Work",    bg: "var(--accent-weak)",           color: "var(--accent-text)"  },
  codex:          { label: "Codex",          bg: "var(--ok-bg)",                 color: "var(--ok)"           },
  codex_cli:      { label: "Codex CLI",      bg: "var(--ok-bg)",                 color: "var(--ok)"           },
  codex_chat:     { label: "Codex Chat",     bg: "var(--ok-bg)",                 color: "var(--ok)"           },
  cursor:         { label: "Cursor",         bg: "rgba(147,51,234,0.10)",        color: "rgb(126,34,206)"     },
  windsurf:       { label: "Windsurf",       bg: "rgba(14,165,233,0.10)",        color: "rgb(2,132,199)"      },
  copilot:        { label: "Copilot",        bg: "rgba(36,41,47,0.08)",          color: "rgb(36,41,47)"       },
  gemini:         { label: "Gemini",         bg: "rgba(249,115,22,0.10)",        color: "rgb(234,88,12)"      },
}

const ALL_TOOLS     = ["claude_code", "claude_chat", "claude_desktop", "claude_work", "codex", "codex_cli", "cursor", "windsurf", "copilot", "gemini"]
export const ALL_DECISIONS = ["allowed", "blocked", "warned", "audited", "approval"]

// ─── Helper components ────────────────────────────────────────────────────────

const normTool = (t: string) => t.replace(/-/g, "_")

export const canonicalTool = (t: string): string => {
  const n = normTool(t ?? "").toLowerCase()
  if (n === "claude_chat" || n === "claude-chat")       return "claude_chat"
  if (n === "claude_desktop" || n === "claude-desktop") return "claude_desktop"
  if (n === "claude_work" || n === "claude-work")       return "claude_work"
  if (n.includes("claude"))                             return "claude_code"
  if (n === "codex_cli" || n === "codex-cli")           return "codex_cli"
  if (n.includes("codex"))                              return "codex"
  if (n.includes("cursor"))                             return "cursor"
  if (n.includes("windsurf"))                           return "windsurf"
  if (n.includes("copilot"))                            return "copilot"
  if (n.includes("gemini"))                             return "gemini"
  return n
}

export function AiToolBadge({ tool }: { tool: string }) {
  const cfg = AI_TOOL_BADGES[normTool(tool)]
  if (!cfg) {
    return (
      <span style={{
        display: "inline-flex",
        alignItems: "center",
        fontSize: 12,
        fontWeight: 500,
        padding: "2px 8px",
        borderRadius: 999,
        background: "var(--surface-3)",
        color: "var(--text-2)",
      }}>
        {tool}
      </span>
    )
  }
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      fontSize: 12,
      fontWeight: 500,
      padding: "2px 8px",
      borderRadius: 999,
      background: cfg.bg,
      color: cfg.color,
    }}>
      {cfg.label}
    </span>
  )
}


type TrendPeriod = "Daily" | "Weekly" | "Monthly"
interface TrendPoint { date: string; claude: number; codex: number; other: number }

export function CostTrendChart({
  workspaceId,
  token,
}: {
  workspaceId: string
  token: string | null
}) {
  const [scale, setScale] = useState<TrendPeriod>("Daily")
  const [data, setData] = useState<TrendPoint[]>([])
  const [loading, setLoading] = useState(true)

  const periodParam = scale.toLowerCase() as "daily" | "weekly" | "monthly"

  useEffect(() => {
    if (!workspaceId || !token) { setData([]); setLoading(false); return }
    setLoading(true)
    const tzOffset = new Date().getTimezoneOffset()
    fetch(
      `${API}/guard/events/cost-trend?period=${periodParam}&workspace_id=${workspaceId}&tz_offset=${tzOffset}`,
      { headers: { Authorization: `Bearer ${token}` } }
    )
      .then(r => r.ok ? r.json() : [])
      .then(d => setData(Array.isArray(d) ? d : []))
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [periodParam, workspaceId, token])

  const hasData = data.some(d => d.claude > 0 || d.codex > 0 || d.other > 0)

  return (
    <div className="card" style={{ padding: "20px 22px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 22 }}>
        <div style={{ fontWeight: 650, fontSize: 15 }}>Est. cost trend</div>
        <div style={{ marginLeft: "auto", display: "flex", background: "var(--surface-3)", borderRadius: 8, padding: 3 }}>
          {(["Daily", "Weekly", "Monthly"] as TrendPeriod[]).map(s => (
            <button
              key={s}
              onClick={() => setScale(s)}
              style={{
                border: "none",
                background: scale === s ? "var(--inverse)" : "transparent",
                color: scale === s ? "var(--on-inverse)" : "var(--text-3)",
                fontSize: 12,
                fontWeight: 600,
                padding: "5px 12px",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ height: 160, background: "var(--surface-2)", borderRadius: 8 }} />
      ) : !hasData ? (
        <div style={{ height: 160, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, color: "var(--text-muted)" }}>
          No cost data yet
        </div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => periodParam === "monthly" ? v.slice(0, 7) : v.slice(5)}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${v}`}
              />
              <Tooltip
                formatter={(val, name) => [`$${Number(val ?? 0).toFixed(4)}`, String(name)]}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid var(--border)" }}
              />
              <Bar dataKey="claude" name="Claude" stackId="a" fill="var(--chart-claude)" radius={[0, 0, 0, 0]} />
              <Bar dataKey="codex"  name="Codex"  stackId="a" fill="var(--chart-codex)"  radius={[3, 3, 0, 0]} />
              {data.some(d => d.other > 0) && (
                <Bar dataKey="other" name="Other" stackId="a" fill="var(--chart-other)" radius={[3, 3, 0, 0]} />
              )}
            </BarChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", gap: 18, justifyContent: "center", marginTop: 14, fontSize: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--chart-claude)", display: "inline-block" }} />
              <span style={{ color: "var(--text-2)" }}>Claude</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: "var(--chart-codex)", display: "inline-block" }} />
              <span style={{ color: "var(--text-2)" }}>Codex</span>
            </span>
          </div>
        </>
      )}
    </div>
  )
}

export function formatTokensSaved(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n === 0)   return "—"
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return `${n}`
}

export function formatTotalTokensSaved(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}k`
  return `${n}`
}


// ─── Stat card ────────────────────────────────────────────────────────────────

type StatTone = "ok" | "err" | "warn" | "accent" | "plain"

export function GuardStatCard({
  label,
  value,
  sub,
  tone = "plain",
  onClick,
  active,
}: {
  label: string
  value: number | string
  sub?: React.ReactNode
  tone?: StatTone
  onClick?: () => void
  active?: boolean
}) {
  const toneColor: Record<StatTone, string> = {
    accent: "var(--accent-text)",
    ok:     "var(--ok)",
    warn:   "var(--warn)",
    err:    "var(--err)",
    plain:  "var(--text)",
  }
  return (
    <div
      className="card card-pad"
      style={{
        cursor: onClick ? "pointer" : undefined,
        outline: active ? "2px solid var(--accent)" : undefined,
      }}
      onClick={onClick}
    >
      <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-.02em", color: toneColor[tone], lineHeight: 1.1 }}>
        {value}
      </div>
      <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>{label}</div>
      {sub && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

export function SavingsStatCard({
  savings,
  loading,
}: {
  savings: GuardSavingsSummary | null
  loading: boolean
}) {
  if (loading) {
    return <div className="card card-pad" style={{ height: 80 }} />
  }

  const hasSavings =
    savings !== null &&
    (savings.team_total.rtk_saved_tokens > 0 || savings.team_total.booster_saved_tokens > 0)

  if (hasSavings && savings !== null) {
    const totalTokens = savings.team_total.rtk_saved_tokens + savings.team_total.booster_saved_tokens
    const totalUsd    = savings.team_total.rtk_saved_usd + savings.team_total.booster_saved_usd
    return (
      <GuardStatCard
        label="Est. savings"
        value={formatTotalTokensSaved(totalTokens) + " tokens"}
        tone="accent"
        sub={<>${totalUsd.toFixed(2)} saved</>}
      />
    )
  }

  return (
    <div className="card card-pad">
      <div style={{ fontSize: 26, fontWeight: 700, color: "var(--text-muted)", lineHeight: 1.1 }}>—</div>
      <div className="eyebrow" style={{ marginTop: 8, fontSize: 9.5 }}>Est. savings</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
        <a href="https://pypi.org/project/rtk/" target="_blank" rel="noopener noreferrer"
           style={{ color: "var(--accent-text)", textDecoration: "underline" }}>RTK</a>
        {" + "}
        <a href="https://pypi.org/project/agent-booster/" target="_blank" rel="noopener noreferrer"
           style={{ color: "var(--accent-text)", textDecoration: "underline" }}>Agent Booster</a>
      </div>
    </div>
  )
}

// ─── By AI tool table ─────────────────────────────────────────────────────────
// Aggregates raw events client-side (respects the page's date filter) and
// passes normalized rows to the shared <ByAiToolTable /> component.

export function ByToolTable({ events }: { events: GuardEvent[] }) {
  const rows = useMemo<ByAiToolRow[]>(() => {
    const map = new Map<string, { tokens: number; cost: number; saved: number }>()
    for (const ev of events) {
      const key = canonicalTool(ev.ai_tool || "unknown")
      const prev = map.get(key) ?? { tokens: 0, cost: 0, saved: 0 }
      const tokensBefore = ev.tokens_before ?? 0
      const tokensAfter  = ev.tokens_after  ?? 0
      map.set(key, {
        tokens: prev.tokens + ((ev.tokens_after ?? ev.tokens_input ?? 0)),
        cost:   prev.cost   + (ev.cost_usd_after ?? 0),
        saved:  prev.saved  + Math.max(0, tokensBefore - tokensAfter),
      })
    }
    const total = Array.from(map.values()).reduce((s, v) => s + v.tokens, 0)
    return Array.from(map.entries())
      .map(([tool, { tokens, cost, saved }]) => ({
        tool,
        tokens,
        costLabel: `$${cost.toFixed(4)}`,
        saved,
        pct: total > 0 ? Math.round((tokens / total) * 100) : 0,
      }))
      .sort((a, b) => b.tokens - a.tokens)
  }, [events])

  return <ByAiToolTable rows={rows} />
}

// ─── Select style helper ──────────────────────────────────────────────────────

export const selectStyle: React.CSSProperties = {
  fontSize: 13,
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "6px 12px",
  background: "var(--surface)",
  color: "var(--text-2)",
  outline: "none",
}

// ─── Main page ────────────────────────────────────────────────────────────────
