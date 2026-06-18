"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { statusStyle as _statusStyle, formatTrigger, timeAgo } from "@/lib/runUtils"

// #10 #15: statusStyle imported with alias to suppress unused-var; timeAgo from runUtils (removed local duplicate)
void _statusStyle

interface OutcomeStats {
  prs_opened: number
  issues_triaged: number
  reviews_completed: number
  incidents_investigated: number
  successful_automations: number
  failed_automations: number
  // optional prev-period deltas from API
  prev_prs_opened?: number
  prev_issues_triaged?: number
  prev_reviews_completed?: number
  prev_incidents_investigated?: number
  prev_successful_automations?: number
  prev_failed_automations?: number
}

interface AgentHealth {
  workflow_id: string
  name: string
  playbook_slug: string | null
  run_count: number
  succeeded_count: number
  failed_count: number
  success_rate: number
  last_run_status: string | null
  last_run_at: string | null
}

interface AttentionRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  trigger_summary: string | null
  created_at: string
  repo: string | null
}

interface RecentRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  started_at: string | null
  created_at: string
  repo: string | null
}

interface AgentTokenUsage {
  workflow_id: string
  name: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost_usd: number
}

interface TokenUsage {
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  estimated_cost_usd: number
  by_agent: AgentTokenUsage[]
}

interface PolicyHit {
  policy_name: string
  count: number
  severity?: string
}

interface DeveloperSpend {
  name: string
  spent_usd: number
  limit_usd: number | null
}

interface GuardSnapshot {
  policy_blocks_today?: number
  top_policy_hits?: PolicyHit[]
  developer_near_limit?: DeveloperSpend[]
}

interface DashboardData {
  outcomes: OutcomeStats
  needs_attention: AttentionRun[]
  agent_health: AgentHealth[]
  recent_activity: RecentRun[]
  token_usage: TokenUsage
  guard_snapshot?: GuardSnapshot
}

// #15: removed fmtTokens (never called)
// #15: removed local timeAgo (duplicated runUtils export — using runUtils version above)

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

/* ── SpendArc donut ── */

function SpendArc({ pct, warn }: { pct: number, warn: boolean }) {
  const r = 30, cx = 38, cy = 38, sw = 7
  const circ = 2 * Math.PI * r
  const arc = circ * Math.min(pct / 100, 1)
  const col = warn ? "var(--warn)" : "var(--accent)"
  return (
    <svg width={76} height={76} viewBox="0 0 76 76" style={{ flexShrink: 0 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={sw} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={col} strokeWidth={sw}
        strokeDasharray={`${arc.toFixed(1)} ${circ.toFixed(1)}`}
        strokeLinecap="round" transform={`rotate(-90 ${cx} ${cy})`} />
      <text x={cx} y={cy - 3} textAnchor="middle" fontSize="13" fontWeight="700"
        fill="var(--text)" fontFamily="inherit">{pct}%</text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize="9" fill="var(--text-muted)"
        fontFamily="inherit">used</text>
    </svg>
  )
}

export default function DashboardPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <DashboardWithAuth />
  return <DashboardContent getToken={null} />
}

function DashboardWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
  if (!isLoaded) return null
  return <DashboardContent getToken={getToken} />
}

/* ── Helpers ── */

function SectionLabel({
  children,
  action,
  href,
}: {
  children: React.ReactNode
  action?: string
  href?: string
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 13 }}>
      <span className="eyebrow" style={{ fontSize: 10 }}>{children}</span>
      {action && href && (
        // #11: use Link instead of bare <a>
        <Link
          href={href}
          style={{
            marginLeft: "auto",
            fontSize: 12,
            color: "var(--accent-text)",
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          {action} →
        </Link>
      )}
    </div>
  )
}

// #2: KPI no longer takes sparkData / delta / up — just label, value, tone, sub, onClick
function KPI({
  label,
  value,
  tone,
  sub,
  onClick,
}: {
  label: string
  value: string | number
  tone?: "ok" | "warn" | "err" | "info" | "plain"
  sub?: string
  onClick?: () => void
}) {
  const toneColor =
    tone === "info" ? "var(--info)"
    : tone === "warn" ? "var(--warn)"
    : tone === "err" ? "var(--err)"
    : "var(--border-2)"

  const valueColor =
    tone === "ok" ? "var(--ok)"
    : tone === "warn" ? "var(--warn)"
    : tone === "err" ? "var(--err)"
    : tone === "info" ? "var(--info)"
    : "var(--text)"

  return (
    <div
      className="card"
      // #20: minWidth so cards wrap on narrow viewports
      // #6: only apply cursor: pointer when onClick is present
      style={{
        padding: "18px 20px 15px",
        flex: 1,
        minWidth: 160,
        borderTop: `2.5px solid ${toneColor}`,
        cursor: onClick ? "pointer" : "default",
      }}
      onClick={onClick}
      onMouseEnter={e => { if (onClick) (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)" }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = "" }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 8 }}>{label}</div>
          <div style={{ fontSize: 28, fontWeight: 750, letterSpacing: "-.03em", lineHeight: 1, color: valueColor }}>{value}</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 11, minHeight: 18 }}>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)", flex: 1 }}>{sub}</span>
      </div>
    </div>
  )
}

// #1 #9: PriorityItem wired to PATCH /runs/{id}/approve
function PriorityItem({
  run,
  getToken,
}: {
  run: AttentionRun
  getToken: (() => Promise<string | null>) | null
}) {
  const [acted, setAct] = useState<string | null>(null)
  const [approveError, setApproveError] = useState<string | null>(null)

  // #9: added "paused" alongside "waiting_approval" and "waiting"
  const isWaiting = run.status === "waiting_approval" || run.status === "waiting" || run.status === "paused"
  const isFailed = run.status === "failed"

  const tone =
    isFailed ? "var(--err)"
    : isWaiting ? "var(--warn)"
    : "var(--info)"

  const toneBg =
    isFailed ? "var(--err-bg)"
    : isWaiting ? "var(--warn-bg)"
    : "var(--info-bg)"

  const badgeClass =
    isFailed ? "sbadge err"
    : isWaiting ? "sbadge warn"
    : "sbadge run"

  const badgeLabel =
    isFailed ? "failed"
    : isWaiting ? "awaiting"
    : run.status

  async function handleApproval(approved: boolean) {
    setApproveError(null)
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const workspaceId = getCookie("delegator_project_id")
    if (workspaceId) headers["X-Workspace-Id"] = workspaceId
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/runs/${run.run_id}/approve`,
        { method: "POST", headers, body: JSON.stringify({ decision: approved ? "approved" : "rejected" }) }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setApproveError(body?.detail ?? `Request failed (${res.status})`)
        return
      }
      setAct(approved ? "Approve" : "Reject")
    } catch (err: unknown) {
      setApproveError(err instanceof Error ? err.message : "Network error")
    }
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        padding: "12px 16px",
        borderBottom: "1px solid var(--border)",
        borderLeft: `3px solid ${tone}`,
      }}
    >
      <div style={{
        width: 28,
        height: 28,
        borderRadius: 8,
        flexShrink: 0,
        background: toneBg,
        display: "grid",
        placeItems: "center",
      }}>
        <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke={tone} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          {isWaiting
            ? <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
            : isFailed
            ? <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            : <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />}
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.2 }}>{run.workflow_name}</div>
        <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 3, lineHeight: 1.4 }}>
          {run.trigger_summary ?? formatTrigger(run.triggered_by)}
          {run.repo && ` · ${run.repo}`}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 7 }}>
          <span className={badgeClass} style={{ height: 18, fontSize: 9.5, display: "inline-flex" }}>
            {badgeLabel}
          </span>
          <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
            {timeAgo(run.created_at)}
          </span>
        </div>
        {/* #1: inline error message */}
        {approveError && (
          <div style={{ fontSize: 11.5, color: "var(--err)", marginTop: 5 }}>{approveError}</div>
        )}
      </div>
      {acted ? (
        <span
          className={"sbadge " + (acted === "Approve" ? "ok" : "err")}
          style={{ flexShrink: 0, fontSize: 11.5 }}
        >
          {acted === "Approve" ? "Approved" : "Rejected"}
        </span>
      ) : isWaiting ? (
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {/* #1: wired to API */}
          <button
            className="btn btn-sm btn-accent"
            onClick={() => handleApproval(true)}
          >
            Approve
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => handleApproval(false)}
            style={{ color: "var(--err)", borderColor: "var(--err-bd)" }}
          >
            Reject
          </button>
          {/* #11: Link instead of bare <a> */}
          <Link
            href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
            className="btn btn-ghost btn-sm btn-icon"
            title="View run"
            style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" />
            </svg>
          </Link>
        </div>
      ) : (
        <Link
          href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
          className="btn btn-ghost btn-sm btn-icon"
          title="View run"
          style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}
        >
          <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" />
          </svg>
        </Link>
      )}
    </div>
  )
}

// #4: accepts spendCapUsd from Guard config API; #5: accepts guardSnapshot from API
function GuardSnapshotPanel({
  tokenUsage,
  spendCapUsd,
  guardSnapshot,
}: {
  tokenUsage: TokenUsage | null
  spendCapUsd: number | null
  guardSnapshot: GuardSnapshot | undefined
}) {
  const spent = tokenUsage?.estimated_cost_usd ?? null
  // #4: use API cap, fall back to null (no hardcoded 500)
  const cap = spendCapUsd
  const pct = spent !== null && cap !== null ? Math.round((spent / cap) * 100) : null

  // #5: real guard data
  const policyBlocksToday = guardSnapshot?.policy_blocks_today
  const topPolicyHits = guardSnapshot?.top_policy_hits ?? []
  const developerNearLimit = guardSnapshot?.developer_near_limit ?? []

  // Burn rate: project days until cap based on spend so far this month
  const dayOfMonth = new Date().getDate()
  const daysInMonth = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate()
  const dailyRate = spent !== null && dayOfMonth > 0 ? spent / dayOfMonth : null
  const daysUntilCap = dailyRate && dailyRate > 0 && cap !== null && spent !== null
    ? Math.max(0, Math.round((cap - spent) / dailyRate))
    : null
  const onPaceToHitCap = daysUntilCap !== null && daysUntilCap < (daysInMonth - dayOfMonth)

  // Priority alert: most urgent item to surface at the top
  const priorityAlert =
    (pct ?? 0) >= 90 ? { tone: "err" as const, msg: `Spend at ${pct}% of cap — action needed` }
    : onPaceToHitCap ? { tone: "warn" as const, msg: `On pace to hit cap in ~${daysUntilCap}d` }
    : developerNearLimit.length > 0 ? { tone: "warn" as const, msg: `${developerNearLimit.length} developer${developerNearLimit.length > 1 ? "s" : ""} near spend limit` }
    : (policyBlocksToday ?? 0) > 5 ? { tone: "warn" as const, msg: `${policyBlocksToday} policy blocks today` }
    : null

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {/* Header */}
      <div
        style={{
          padding: "13px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <svg
          width={16}
          height={16}
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--accent-text)"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <span style={{ fontWeight: 650, fontSize: 14 }}>ConductGuard</span>
        <span className="sbadge ok" style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span className="dot pulse" style={{ background: "var(--ok)" }} />
          live
        </span>
        {/* #11: Link instead of bare <a> */}
        <Link
          href="/guard"
          className="btn btn-ghost btn-sm"
          style={{ textDecoration: "none" }}
        >
          Full dashboard →
        </Link>
      </div>

      {/* Priority alert */}
      {priorityAlert && (
        <div style={{
          padding: "9px 16px",
          borderBottom: "1px solid var(--border)",
          background: priorityAlert.tone === "err" ? "var(--err-bg)" : "var(--warn-bg)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ fontSize: 12, color: priorityAlert.tone === "err" ? "var(--err)" : "var(--warn)", fontWeight: 600 }}>
            {priorityAlert.tone === "err" ? "⚠ " : "↑ "}{priorityAlert.msg}
          </span>
        </div>
      )}

      {/* Spend vs cap — donut row */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
        <SpendArc pct={pct ?? 0} warn={(pct ?? 0) > 80} />
        <div>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 5 }}>Spend vs cap · this month</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginBottom: 6 }}>
            <span style={{ fontSize: 24, fontWeight: 750, letterSpacing: "-.03em" }}>
              {spent !== null ? `$${spent.toFixed(0)}` : "—"}
            </span>
            {/* #4: show cap from API or "No cap set" */}
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {cap !== null ? `of $${cap}` : "No cap set"}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className={"sbadge " + ((pct ?? 0) > 80 ? "warn" : "ok")} style={{ height: 18, fontSize: 10.5 }}>
              {(pct ?? 0) > 80 ? "Near cap" : "On track"}
            </span>
            {spent !== null && cap !== null && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>${(cap - spent).toFixed(0)} left</span>
            )}
          </div>
          {daysUntilCap !== null && (
            <div style={{ fontSize: 11, color: onPaceToHitCap ? "var(--warn)" : "var(--text-muted)", marginTop: 5 }}>
              {onPaceToHitCap
                ? `↑ On pace to hit cap in ~${daysUntilCap}d`
                : `At this rate, cap lasts the month`}
            </div>
          )}
        </div>
      </div>

      {/* Top policy hits — #5: real data or empty state */}
      <div style={{ padding: "13px 16px", borderBottom: "1px solid var(--border)" }}>
        <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 9 }}>Top policy hits (30d)</div>
        {topPolicyHits.length === 0 ? (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No policy blocks today</span>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {topPolicyHits.slice(0, 3).map((hit, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="mono" style={{ fontSize: 11.5, fontWeight: 600, flex: 1, color: "var(--text)" }}>
                  {hit.policy_name}
                </span>
                {hit.severity && (
                  <span className="sbadge run" style={{ height: 17, fontSize: 9, padding: "0 6px" }}>
                    {hit.severity}
                  </span>
                )}
                <span className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)", minWidth: 22, textAlign: "right" }}>
                  {hit.count}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Developer near limit — #5: real data or empty state */}
      <div style={{ padding: "13px 16px" }}>
        <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 9 }}>Developer near limit</div>
        {developerNearLimit.length === 0 ? (
          <span style={{ fontSize: 12, color: "var(--ok)" }}>All developers within limits</span>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {developerNearLimit.map((dev, i) => {
              const devPct = dev.limit_usd ? Math.min(100, Math.round((dev.spent_usd / dev.limit_usd) * 100)) : null
              const devColor = (devPct ?? 0) >= 90 ? "var(--err)" : "var(--warn)"
              return (
                <div key={i}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <span style={{ fontSize: 12, flex: 1, color: "var(--text)", fontWeight: 500 }}>{dev.name}</span>
                    <span style={{ fontSize: 11, color: devColor, fontWeight: 600 }}>
                      {devPct !== null ? `${devPct}%` : `$${dev.spent_usd.toFixed(0)}`}
                    </span>
                  </div>
                  {devPct !== null && (
                    <div style={{ height: 4, borderRadius: 4, background: "var(--surface-3)", overflow: "hidden" }}>
                      <div style={{ width: `${devPct}%`, height: "100%", borderRadius: 4, background: devColor }} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// #3: AgentHealthRow rendered in Agent Health section below KPI strip
function AgentHealthRow({ agent }: { agent: AgentHealth }) {
  const healthLabel =
    agent.last_run_status === null ? "Idle"
    : agent.run_count === 0 ? "Idle"
    : agent.success_rate >= 80 ? "Healthy"
    : agent.success_rate >= 50 ? "Degraded"
    : "Stale"

  const healthColor =
    healthLabel === "Healthy" ? "var(--ok)"
    : healthLabel === "Degraded" ? "var(--warn)"
    : healthLabel === "Stale" ? "var(--err)"
    : "var(--text-3)"

  const healthBg =
    healthLabel === "Healthy" ? "var(--ok-bg)"
    : healthLabel === "Degraded" ? "var(--warn-bg)"
    : healthLabel === "Stale" ? "var(--err-bg)"
    : "var(--surface-3)"

  const successRate = agent.run_count === 0 ? null : agent.success_rate / 100
  const barColor =
    successRate === null ? "var(--surface-3)"
    : successRate >= 0.8 ? "var(--ok)"
    : successRate >= 0.5 ? "var(--warn)"
    : "var(--err)"

  return (
    <Link
      href={`/workflows/${agent.workflow_id}`}
      style={{
        display: "grid",
        gridTemplateColumns: "2fr 1fr 1fr 0.9fr",
        gap: 12,
        padding: "11px 16px",
        borderBottom: "1px solid var(--border)",
        alignItems: "center",
        cursor: "pointer",
        textDecoration: "none",
        color: "inherit",
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--surface-2)" }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "" }}
    >
      {/* Agent name + last run time */}
      <div>
        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{agent.name}</div>
        <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 2 }}>
          {agent.last_run_at ? `last run ${timeAgo(agent.last_run_at)}` : "never run"}
        </div>
      </div>

      {/* Status badge */}
      <div>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            height: 21,
            padding: "0 8px",
            borderRadius: 20,
            fontSize: 11,
            fontWeight: 600,
            color: healthColor,
            background: healthBg,
          }}
        >
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: healthColor }} />
          {healthLabel}
        </span>
      </div>

      {/* Success rate bar + % */}
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <div
          style={{
            width: 52,
            height: 5,
            borderRadius: 5,
            background: "var(--surface-3)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: successRate !== null ? `${Math.round(successRate * 100)}%` : "0%",
              height: "100%",
              borderRadius: 5,
              background: barColor,
            }}
          />
        </div>
        <span
          className="mono"
          style={{
            fontSize: 12,
            color: successRate === null ? "var(--text-muted)" : barColor,
          }}
        >
          {successRate !== null ? `${Math.round(successRate * 100)}%` : "—"}
        </span>
      </div>

      {/* Quality grade placeholder */}
      <div>
        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>—</span>
      </div>
    </Link>
  )
}

function EmptyChecklist() {
  const steps = [
    { label: "Install a starter playbook", href: "/marketplace", cta: "Browse playbooks →" },
    { label: "Add credentials (GitHub token, Slack)", href: "/settings/integrations", cta: "Open integrations →" },
    { label: "Run a test trigger", href: "/runs", cta: "Go to Runs →" },
    { label: "Review the AI trace", href: "/runs", cta: "Open a run →" },
  ]
  return (
    <div
      className="card"
      style={{ padding: "32px 36px", maxWidth: 480, margin: "32px auto 0" }}
    >
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>Get started with Conduct</div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 22 }}>
        No agents yet. Follow these steps to automate your first engineering task.
      </div>
      <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 16 }}>
        {steps.map((s, i) => (
          <li key={i} style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: "50%",
                background: "var(--surface-2)",
                color: "var(--text-muted)",
                fontSize: 11,
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {i + 1}
            </span>
            <div style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>{s.label}</div>
            {/* #11: Link instead of bare <a> */}
            <Link
              href={s.href}
              style={{
                fontSize: 12,
                color: "var(--accent-text)",
                fontWeight: 600,
                textDecoration: "none",
                flexShrink: 0,
              }}
            >
              {s.cta}
            </Link>
          </li>
        ))}
      </ol>
    </div>
  )
}

/* ── Main content ── */

function DashboardContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardSynced, setGuardSynced] = useState<boolean | null>(null)
  const [mySynced, setMySynced] = useState<boolean | null>(null)
  // #4: spend cap from Guard config API
  const [spendCapUsd, setSpendCapUsd] = useState<number | null>(null)
  // #7: ref for scroll-to instead of document.querySelector
  const priorityFeedRef = useRef<HTMLDivElement>(null)
  // #16: track last updated time for polling display
  const [lastUpdated, setLastUpdated] = useState<string>("")
  // #14: dismiss state for nudge banners
  const [dismissedPersonalNudge, setDismissedPersonalNudge] = useState(false)
  const [dismissedGuardNudge, setDismissedGuardNudge] = useState(false)
  const router = useRouter()

  async function loadData() {
    const headers: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const workspaceId = getCookie("delegator_project_id")
    if (workspaceId) headers["X-Workspace-Id"] = workspaceId
    try {
      setError(null)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/dashboard`, { headers })
      if (res.ok) {
        setData(await res.json())
        setLastUpdated(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))
      } else {
        setError(`Failed to load dashboard (${res.status})`)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Network error")
    } finally {
      setLoading(false)
    }

    // Load security + guard coverage in parallel (non-blocking)
    if (workspaceId) {
      try {
        const base = process.env.NEXT_PUBLIC_API_URL ?? ""
        const wsHeaders = { ...headers, "X-Workspace-Id": workspaceId }
        const [toolsRes, meRes, guardConfigRes] = await Promise.all([
          fetch(`${base}/guard/developer-tools`, { headers: wsHeaders }),
          fetch(`${base}/guard/developer-tools/me`, { headers: wsHeaders }),
          // #4: fetch Guard config for spend cap
          fetch(`${base}/guard/config?workspace_id=${workspaceId}`, { headers: wsHeaders }),
        ])
        if (toolsRes.ok) {
          const tools = await toolsRes.json()
          setGuardSynced(Array.isArray(tools) && tools.length > 0)
        }
        if (meRes.ok) {
          const me = await meRes.json()
          setMySynced(me.synced === true)
        }
        // #4: read spend_limit_usd from Guard config
        if (guardConfigRes.ok) {
          const guardConfig = await guardConfigRes.json()
          setSpendCapUsd(guardConfig?.spend_limit_usd ?? null)
        }
      } catch {}
    }
  }

  useEffect(() => {
    loadData()

    // #16: re-fetch every 30 seconds; clear on unmount
    const interval = setInterval(() => {
      loadData()
    }, 30_000)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // #8: count active runs from full list (not sliced), status === "running"
  const activeRunCount = data
    ? data.recent_activity.filter(r => r.status === "running").length
    : 0

  const spendDisplay = data && data.token_usage.estimated_cost_usd > 0
    ? `$${data.token_usage.estimated_cost_usd.toFixed(2)}`
    : "—"

  // #5: policy blocks today from guard_snapshot
  const policyBlocksToday = data?.guard_snapshot?.policy_blocks_today

  return (
    <AppShell>
      <div className="page fade-in" style={{ maxWidth: 1080 }}>
        {/* Page header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-end" }}>
          <div>
            <h1 className="page-title">Dashboard</h1>
            {/* #19: removed misleading "Last 7 days" subtitle */}
            <p className="page-sub">Spend is monthly · Activity is real-time</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 7,
              background: "var(--ok-bg)", border: "1px solid var(--ok-bd)",
              borderRadius: 20, padding: "4px 11px",
            }}>
              <span className="dot pulse" style={{ background: "var(--ok)", width: 6, height: 6 }} />
              <span style={{ fontSize: 11.5, color: "var(--ok)", fontWeight: 600 }}>{activeRunCount} active</span>
              {lastUpdated && <span style={{ fontSize: 11, color: "var(--text-3)" }}>· {lastUpdated}</span>}
            </div>
            <Link href="/workflows/new" className="btn btn-primary">
              <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} style={{ display: "inline", verticalAlign: "middle", marginRight: 5 }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
              </svg>
              New agent
            </Link>
          </div>
        </div>

        {/* #14: Personal sync nudge with dismiss button, no emoji, role="status" */}
        {!dismissedPersonalNudge && mySynced === false && guardSynced === true && (
          <div
            role="status"
            style={{
              display: "flex", alignItems: "center", gap: 12,
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "10px 16px", marginBottom: 16,
            }}
          >
            <div style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>
              Your teammates are on Guard. Connect your machine by running{" "}
              <code style={{ background: "var(--surface-3)", padding: "1px 5px", borderRadius: 4, fontSize: 12 }}>conduct guard sync</code>{" "}
              in your terminal.
            </div>
            <a href="https://docs.conductai.ai/guard/sync" target="_blank" rel="noreferrer" style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}>
              How to sync →
            </a>
            <button
              onClick={() => setDismissedPersonalNudge(true)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "var(--text-muted)", padding: "0 4px", lineHeight: 1 }}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}

        {/* #14: Guard sync nudge with dismiss button, no emoji, role="status" */}
        {!dismissedGuardNudge && guardSynced === false && (
          <div
            role="status"
            style={{
              display: "flex", alignItems: "center", gap: 12,
              background: "var(--warn-bg)", border: "1px solid var(--warn-bd)",
              borderRadius: 10, padding: "10px 16px", marginBottom: 16,
            }}
          >
            <div style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>
              <strong>Guard is active</strong> — but no team members have synced the CLI yet.
              Run <code style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4, fontSize: 12 }}>conduct guard sync</code> on each developer machine to start capturing activity.
            </div>
            <Link href="/guard" style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}>
              Go to Guard →
            </Link>
            <button
              onClick={() => setDismissedGuardNudge(true)}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "var(--text-muted)", padding: "0 4px", lineHeight: 1 }}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}

        {loading ? (
          // #12: skeleton matches real 2-column layout + Guard column
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* KPI skeleton */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="card" style={{ flex: 1, minWidth: 160, height: 80, opacity: 0.4 }} />
              ))}
            </div>
            {/* 2-column skeleton */}
            <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 22 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <div className="card" style={{ height: 200, opacity: 0.4 }} />
                <div className="card" style={{ height: 160, opacity: 0.4 }} />
                <div className="card" style={{ height: 220, opacity: 0.4 }} />
              </div>
              <div>
                {/* Guard snapshot skeleton */}
                <div className="card" style={{ height: 320, opacity: 0.4 }} />
              </div>
            </div>
          </div>
        ) : error ? (
          // #13: proper error card with retry button and role="alert"
          <div className="card" role="alert" style={{ padding: "24px 28px", maxWidth: 480 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--err)", marginBottom: 8 }}>
              Could not load dashboard
            </div>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>{error}</p>
            <button
              className="btn btn-primary"
              onClick={() => {
                setLoading(true)
                loadData()
              }}
            >
              Retry
            </button>
          </div>
        ) : !data ? (
          <div className="card" role="alert" style={{ padding: "24px 28px", maxWidth: 480 }}>
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No dashboard data available.</p>
          </div>
        ) : data.agent_health.length === 0 ? (
          <EmptyChecklist />
        ) : (
          <>
            {/* KPI strip — #20: flexWrap + minWidth */}
            <div style={{ display: "flex", gap: 12, marginBottom: 26, flexWrap: "wrap" }}>
              {/* #2: no sparklines, no hardcoded deltas */}
              {/* #8: active run count from full recent_activity list */}
              <KPI
                label="Active runs"
                value={activeRunCount}
                tone="info"
                sub="across agents"
                // #11: router.push instead of window.location.assign
                onClick={() => router.push("/runs")}
              />
              <KPI
                label="Needs attention"
                value={data.needs_attention.length}
                tone="warn"
                sub="approvals + failures"
                // #7: scroll via ref instead of document.querySelector
                onClick={() => priorityFeedRef.current?.scrollIntoView({ behavior: "smooth" })}
              />
              <KPI
                label="Spend today"
                value={spendDisplay}
                tone="plain"
                sub="est. Claude tokens"
                // #11: router.push instead of window.location.assign
                onClick={() => router.push("/guard/spend")}
              />
              {/* #6: no onClick → no cursor: pointer (handled in KPI component) */}
              {/* #5: real policy block count or "—" with no-data sub */}
              <KPI
                label="Policy blocks today"
                value={policyBlocksToday !== undefined ? policyBlocksToday : "—"}
                tone="err"
                sub={policyBlocksToday !== undefined ? "Guard blocks" : "no Guard data"}
              />
            </div>

            {/* #3: Agent Health section — rendered when data.agent_health.length > 0 */}
            {data.agent_health.length > 0 && (
              <div style={{ marginBottom: 26 }}>
                <SectionLabel>Agent Health</SectionLabel>
                <div className="card" style={{ overflow: "hidden", padding: 0 }}>
                  {/* Table header */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "2fr 1fr 1fr 0.9fr",
                      gap: 12,
                      padding: "8px 16px",
                      background: "var(--surface-2)",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    {["Agent", "Status", "Success rate", "Grade"].map(h => (
                      <div key={h} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
                    ))}
                  </div>
                  {data.agent_health.map(agent => (
                    <AgentHealthRow key={agent.workflow_id} agent={agent} />
                  ))}
                </div>
              </div>
            )}

            {/* 2-column grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.6fr 1fr",
                gap: 22,
                alignItems: "start",
              }}
            >
              {/* LEFT column */}
              <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>

                {/* Priority feed — #7: ref instead of document.querySelector */}
                <div ref={priorityFeedRef}>
                  <SectionLabel action="View all runs" href="/runs">
                    Needs attention · {data.needs_attention.length}
                  </SectionLabel>
                  {data.needs_attention.length === 0 ? (
                    <div
                      className="card"
                      style={{ padding: "20px 18px", color: "var(--ok)", fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}
                    >
                      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="var(--ok)" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      All clear — no runs need attention.
                    </div>
                  ) : (
                    <div className="card" style={{ overflow: "hidden", padding: 0 }}>
                      {data.needs_attention.map(run => (
                        <PriorityItem key={run.run_id} run={run} getToken={getToken} />
                      ))}
                    </div>
                  )}
                </div>

                {/* Outcomes */}
                <div>
                  {/* #18: "View all" link in Outcomes header */}
                  <SectionLabel action="View all" href="/runs">
                    Outcomes · last 7 days
                  </SectionLabel>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(3, 1fr)",
                      gap: 11,
                    }}
                  >
                    {[
                      { k: "PRs opened",              v: data.outcomes.prs_opened,              prev: data.outcomes.prev_prs_opened,              tone: "plain" },
                      { k: "Issues triaged",          v: data.outcomes.issues_triaged,          prev: data.outcomes.prev_issues_triaged,          tone: "plain" },
                      { k: "Reviews completed",       v: data.outcomes.reviews_completed,       prev: data.outcomes.prev_reviews_completed,       tone: "plain" },
                      { k: "Incidents investigated",  v: data.outcomes.incidents_investigated,  prev: data.outcomes.prev_incidents_investigated,  tone: "plain" },
                      { k: "Successful automations",  v: data.outcomes.successful_automations,  prev: data.outcomes.prev_successful_automations,  tone: "ok" },
                      { k: "Failed automations",      v: data.outcomes.failed_automations,      prev: data.outcomes.prev_failed_automations,      tone: data.outcomes.failed_automations > 0 ? "err" : "plain" },
                    ].map(o => {
                      const delta = o.prev !== undefined ? o.v - o.prev : null
                      const deltaUp = delta !== null && delta > 0
                      const deltaDown = delta !== null && delta < 0
                      const isBadUp = o.tone === "err" // failed automations: up is bad
                      return (
                        <div key={o.k} className="card" style={{ padding: "14px 15px" }}>
                          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 4 }}>
                            <div
                              style={{
                                fontSize: 22,
                                fontWeight: 700,
                                color: o.tone === "ok" ? "var(--ok)" : o.tone === "err" ? "var(--err)" : "var(--text)",
                                letterSpacing: "-.015em",
                              }}
                            >
                              {o.v}
                            </div>
                            {delta !== null && delta !== 0 && (
                              <span style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: "2px 5px",
                                borderRadius: 4,
                                color: (deltaUp && !isBadUp) || (deltaDown && isBadUp) ? "var(--ok)" : "var(--err)",
                                background: (deltaUp && !isBadUp) || (deltaDown && isBadUp) ? "var(--ok-bg)" : "var(--err-bg)",
                              }}>
                                {deltaUp ? "+" : ""}{delta}
                              </span>
                            )}
                          </div>
                          <div className="eyebrow" style={{ marginTop: 6, fontSize: 11 }}>{o.k}</div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Recent activity */}
                <div>
                  <SectionLabel action="All runs" href="/runs">Recent activity</SectionLabel>
                  {data.recent_activity.length === 0 ? (
                    <div
                      className="card"
                      style={{ padding: "20px 18px", fontSize: 13, color: "var(--text-muted)" }}
                    >
                      No runs yet —{" "}
                      {/* #11: Link instead of bare <a> */}
                      <Link href="/workflows" style={{ color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}>
                        open an agent
                      </Link>{" "}
                      and hit Run.
                    </div>
                  ) : (
                    <div className="card" style={{ overflow: "hidden", padding: 0 }}>
                      {data.recent_activity.slice(0, 5).map(run => {
                        const statusBadge =
                          run.status === "succeeded" ? "sbadge ok"
                          : run.status === "failed" ? "sbadge err"
                          : run.status === "running" ? "sbadge run"
                          : run.status === "waiting_approval" || run.status === "waiting" || run.status === "paused" ? "sbadge warn"
                          : "sbadge"

                        const statusLabel =
                          run.status === "succeeded" ? "Succeeded"
                          : run.status === "failed" ? "Failed"
                          : run.status === "running" ? "Running"
                          : run.status === "waiting_approval" || run.status === "waiting" || run.status === "paused" ? "Awaiting"
                          : run.status

                        const runBorderColor =
                          run.status === "succeeded" ? "var(--ok)"
                          : run.status === "failed" ? "var(--err)"
                          : run.status === "running" ? "var(--info)"
                          : "var(--warn)"

                        return (
                          // #11: Link instead of bare <a>
                          <Link
                            key={run.run_id}
                            href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 12,
                              padding: "10px 16px",
                              borderBottom: "1px solid var(--border)",
                              borderLeft: `3px solid ${runBorderColor}`,
                              cursor: "pointer",
                              textDecoration: "none",
                              color: "inherit",
                            }}
                            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--surface-2)" }}
                            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "" }}
                          >
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontWeight: 600, fontSize: 13 }}>{run.workflow_name}</div>
                              <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                {run.repo ? `${run.repo} · ` : ""}{formatTrigger(run.triggered_by)}
                              </div>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span className={statusBadge} style={{ height: 19, fontSize: 11 }}>
                                {statusLabel}
                              </span>
                              <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                                {timeAgo(run.started_at ?? run.created_at)}
                              </span>
                            </div>
                          </Link>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* RIGHT column */}
              <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>

                {/* Guard snapshot */}
                <div>
                  <SectionLabel>Guard</SectionLabel>
                  <GuardSnapshotPanel
                    tokenUsage={data.token_usage.total_tokens > 0 ? data.token_usage : null}
                    spendCapUsd={spendCapUsd}
                    guardSnapshot={data.guard_snapshot}
                  />
                </div>

              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}
