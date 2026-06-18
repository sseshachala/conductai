"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { statusStyle, formatTrigger } from "@/lib/runUtils"

interface OutcomeStats {
  prs_opened: number
  issues_triaged: number
  reviews_completed: number
  incidents_investigated: number
  successful_automations: number
  failed_automations: number
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

interface DashboardData {
  outcomes: OutcomeStats
  needs_attention: AttentionRun[]
  agent_health: AgentHealth[]
  recent_activity: RecentRun[]
  token_usage: TokenUsage
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

/* ── Spark component ── */

function Spark({ data, color, h = 34, w = 72 }: { data: number[], color: string, h?: number, w?: number }) {
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1
  const pad = 3
  const pts = data.map((v, i) => [
    pad + (i / (data.length - 1)) * (w - pad * 2),
    (h - pad) - ((v - min) / range) * (h - pad * 2),
  ])
  const d = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ")
  const [lx, ly] = pts[pts.length - 1]
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} fill="none" style={{ display: "block" }}>
      <path d={d} stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r="2.5" fill={color} />
    </svg>
  )
}

/* ── Static sparkline data ── */

const SPARKS = {
  runs:      [1, 2, 2, 3, 2, 4, 3, 4, 5, 4, 3, 5, 4, 6, 3],
  attention: [3, 4, 3, 5, 4, 5, 6, 5, 4, 5],
  spend:     [80, 110, 95, 130, 145, 160, 180, 190, 214],
  blocks:    [10, 14, 12, 18, 16, 20, 22, 19, 23],
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
        <a
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
        </a>
      )}
    </div>
  )
}

function KPI({
  label,
  value,
  tone,
  sub,
  sparkData,
  delta,
  up,
  onClick,
}: {
  label: string
  value: string | number
  tone?: "ok" | "warn" | "err" | "info" | "plain"
  sub?: string
  sparkData: number[]
  delta: number
  up: boolean
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
      style={{ padding: "18px 20px 15px", flex: 1, borderTop: `2.5px solid ${toneColor}`, cursor: "pointer" }}
      onClick={onClick}
      onMouseEnter={e => { if (onClick) (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)" }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = "" }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 8 }}>{label}</div>
          <div style={{ fontSize: 28, fontWeight: 750, letterSpacing: "-.03em", lineHeight: 1, color: valueColor }}>{value}</div>
        </div>
        <div style={{ flexShrink: 0, marginTop: 2, opacity: 0.72 }}>
          <Spark data={sparkData} color={toneColor} />
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 11, minHeight: 18 }}>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)", flex: 1 }}>{sub}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: up ? "var(--ok)" : "var(--err)" }}>
          {up ? "↑" : "↓"} {delta}%
        </span>
      </div>
    </div>
  )
}

function PriorityItem({ run }: { run: AttentionRun }) {
  const [acted, setAct] = useState<string | null>(null)

  const isWaiting = run.status === "waiting_approval" || run.status === "waiting"
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
        <span className={badgeClass} style={{ marginTop: 7, height: 18, fontSize: 9.5, display: "inline-flex" }}>
          {badgeLabel}
        </span>
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
          <button
            className="btn btn-sm btn-accent"
            onClick={() => setAct("Approve")}
          >
            Approve
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setAct("Reject")}
            style={{ color: "var(--err)", borderColor: "var(--err-bd)" }}
          >
            Reject
          </button>
          <a
            href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
            className="btn btn-ghost btn-sm btn-icon"
            title="View run"
            style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" />
            </svg>
          </a>
        </div>
      ) : (
        <a
          href={`/workflows/${run.workflow_id}/runs/${run.run_id}`}
          className="btn btn-ghost btn-sm btn-icon"
          title="View run"
          style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}
        >
          <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" />
          </svg>
        </a>
      )}
    </div>
  )
}

function GuardSnapshot({ tokenUsage }: { tokenUsage: TokenUsage | null }) {
  const spent = tokenUsage?.estimated_cost_usd ?? null
  const cap = 500
  const pct = spent !== null ? Math.round((spent / cap) * 100) : null

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
        <a
          href="/guard"
          className="btn btn-ghost btn-sm"
          style={{ textDecoration: "none" }}
        >
          Full dashboard →
        </a>
      </div>

      {/* Spend vs cap — donut row */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
        <SpendArc pct={pct ?? 0} warn={(pct ?? 0) > 80} />
        <div>
          <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 5 }}>Spend vs cap · this month</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginBottom: 6 }}>
            <span style={{ fontSize: 24, fontWeight: 750, letterSpacing: "-.03em" }}>
              {spent !== null ? `$${spent.toFixed(0)}` : "—"}
            </span>
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>of $500</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className={"sbadge " + ((pct ?? 0) > 80 ? "warn" : "ok")} style={{ height: 18, fontSize: 10.5 }}>
              {(pct ?? 0) > 80 ? "Near cap" : "On track"}
            </span>
            {spent !== null && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>${(500 - spent).toFixed(0)} left</span>}
          </div>
        </div>
      </div>

      {/* Top policy hits */}
      <div style={{ padding: "13px 16px", borderBottom: "1px solid var(--border)" }}>
        <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 9 }}>Top policy hits (30d)</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="mono" style={{ fontSize: 11.5, fontWeight: 600, flex: 1, color: "var(--text-muted)" }}>—</span>
              <span className="sbadge run" style={{ height: 17, fontSize: 9, padding: "0 6px" }}>—</span>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)", minWidth: 22, textAlign: "right" }}>—</span>
            </div>
          ))}
        </div>
      </div>

      {/* Developer near limit */}
      <div style={{ padding: "13px 16px" }}>
        <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 9 }}>Developer near limit</div>
        <span style={{ fontSize: 12, color: "var(--ok)" }}>All developers within limits</span>
      </div>
    </div>
  )
}

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

  const spendText = "—"

  return (
    <a
      href={`/workflows/${agent.workflow_id}`}
      style={{
        display: "grid",
        gridTemplateColumns: "2fr 1fr 1fr 0.9fr 0.8fr",
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
      {/* Agent name + slug */}
      <div>
        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{agent.name}</div>
        <div
          className="mono"
          style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 2 }}
        >
          {agent.playbook_slug ?? agent.workflow_id.slice(0, 8)}
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

      {/* Spend */}
      <div
        className="mono"
        style={{ fontSize: 12, color: "var(--text-3)", textAlign: "right" }}
      >
        {spendText}
      </div>
    </a>
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
            <a
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
            </a>
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
  const [guardSynced, setGuardSynced] = useState<boolean | null>(null)
  const [mySynced, setMySynced] = useState<boolean | null>(null)

  useEffect(() => {
    async function load() {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const workspaceId = getCookie("delegator_project_id")
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/dashboard`, { headers })
        if (res.ok) setData(await res.json())
      } finally {
        setLoading(false)
      }

      // Load security + guard coverage in parallel (non-blocking)
      if (workspaceId) {
        try {
          const base = process.env.NEXT_PUBLIC_API_URL ?? ""
          const wsHeaders = { ...headers, "X-Workspace-Id": workspaceId }
          const [toolsRes, meRes] = await Promise.all([
            fetch(`${base}/guard/developer-tools`, { headers: wsHeaders }),
            fetch(`${base}/guard/developer-tools/me`, { headers: wsHeaders }),
          ])
          if (toolsRes.ok) {
            const tools = await toolsRes.json()
            setGuardSynced(Array.isArray(tools) && tools.length > 0)
          }
          if (meRes.ok) {
            const me = await meRes.json()
            setMySynced(me.synced === true)
          }
        } catch {}
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const lastUpdated = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })

  const activeRunCount = data
    ? data.recent_activity.filter(r => r.status === "running").length
    : 0

  const spendDisplay = data && data.token_usage.estimated_cost_usd > 0
    ? `$${data.token_usage.estimated_cost_usd.toFixed(2)}`
    : "—"

  return (
    <AppShell>
      <div className="page fade-in" style={{ maxWidth: 1080 }}>
        {/* Page header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-end" }}>
          <div>
            <h1 className="page-title">Dashboard</h1>
            <p className="page-sub">Runs, Guard, and spend — the whole picture at a glance. Last 7 days.</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 7,
              background: "var(--ok-bg)", border: "1px solid var(--ok-bd)",
              borderRadius: 20, padding: "4px 11px",
            }}>
              <span className="dot pulse" style={{ background: "var(--ok)", width: 6, height: 6 }} />
              <span style={{ fontSize: 11.5, color: "var(--ok)", fontWeight: 600 }}>{activeRunCount} active</span>
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>· {lastUpdated}</span>
            </div>
            <Link href="/workflows/new" className="btn btn-primary">
              <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} style={{ display: "inline", verticalAlign: "middle", marginRight: 5 }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
              </svg>
              New agent
            </Link>
          </div>
        </div>

        {/* Personal sync nudge — shown to invited users until they run conduct guard sync */}
        {mySynced === false && guardSynced === true && (
          <div style={{
            display: "flex", alignItems: "center", gap: 12,
            background: "var(--surface-2)", border: "1px solid var(--border)",
            borderRadius: 10, padding: "10px 16px", marginBottom: 16,
          }}>
            <span style={{ fontSize: 18 }}>💻</span>
            <div style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>
              Your teammates are on Guard. Connect your machine by running{" "}
              <code style={{ background: "var(--surface-3)", padding: "1px 5px", borderRadius: 4, fontSize: 12 }}>conduct guard sync</code>{" "}
              in your terminal.
            </div>
            <a href="https://docs.conductai.ai/guard/sync" target="_blank" rel="noreferrer" style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}>
              How to sync →
            </a>
          </div>
        )}

        {/* Guard sync nudge — shown once until at least one developer syncs the CLI */}
        {guardSynced === false && (
          <div style={{
            display: "flex", alignItems: "center", gap: 12,
            background: "var(--warn-bg)", border: "1px solid var(--warn-bd)",
            borderRadius: 10, padding: "10px 16px", marginBottom: 16,
          }}>
            <span style={{ fontSize: 18 }}>🛡️</span>
            <div style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>
              <strong>Guard is active</strong> — but no team members have synced the CLI yet.
              Run <code style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4, fontSize: 12 }}>conduct guard sync</code> on each developer machine to start capturing activity.
            </div>
            <a href="/guard" style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}>
              Go to Guard →
            </a>
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* KPI skeleton */}
            <div style={{ display: "flex", gap: 12 }}>
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="card" style={{ flex: 1, height: 80, opacity: 0.4 }} />
              ))}
            </div>
            <div
              className="card"
              style={{ height: 200, opacity: 0.4 }}
            />
            <div
              className="card"
              style={{ height: 280, opacity: 0.4 }}
            />
          </div>
        ) : !data ? (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Could not load dashboard.</p>
        ) : data.agent_health.length === 0 ? (
          <EmptyChecklist />
        ) : (
          <>
            {/* KPI strip */}
            <div style={{ display: "flex", gap: 12, marginBottom: 26 }}>
              <KPI
                label="Active runs"
                value={activeRunCount}
                tone="info"
                sub="across agents"
                sparkData={SPARKS.runs}
                delta={12}
                up={true}
                onClick={() => window.location.assign("/runs")}
              />
              <KPI
                label="Needs attention"
                value={data.needs_attention.length}
                tone="warn"
                sub="approvals + failures"
                sparkData={SPARKS.attention}
                delta={8}
                up={false}
                onClick={() => {
                  const el = document.querySelector("#priority-feed")
                  if (el) el.scrollIntoView({ behavior: "smooth" })
                }}
              />
              <KPI
                label="Spend today"
                value={spendDisplay}
                tone="plain"
                sub="est. Claude tokens"
                sparkData={SPARKS.spend}
                delta={6}
                up={false}
                onClick={() => window.location.assign("/guard/spend")}
              />
              <KPI
                label="Policy blocks today"
                value="—"
                tone="err"
                sub="no Guard data"
                sparkData={SPARKS.blocks}
                delta={15}
                up={false}
              />
            </div>

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

                {/* Priority feed */}
                <div id="priority-feed">
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
                        <PriorityItem key={run.run_id} run={run} />
                      ))}
                    </div>
                  )}
                </div>

                {/* Outcomes */}
                <div>
                  <SectionLabel>Outcomes · last 7 days</SectionLabel>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(3, 1fr)",
                      gap: 11,
                    }}
                  >
                    {[
                      { k: "PRs opened",              v: data.outcomes.prs_opened,              tone: "plain" },
                      { k: "Issues triaged",          v: data.outcomes.issues_triaged,          tone: "plain" },
                      { k: "Reviews completed",       v: data.outcomes.reviews_completed,       tone: "plain" },
                      { k: "Incidents investigated",  v: data.outcomes.incidents_investigated,  tone: "plain" },
                      { k: "Successful automations",  v: data.outcomes.successful_automations,  tone: "ok" },
                      { k: "Failed automations",      v: data.outcomes.failed_automations,      tone: data.outcomes.failed_automations > 0 ? "err" : "plain" },
                    ].map(o => (
                      <div key={o.k} className="card" style={{ padding: "14px 15px" }}>
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
                        <div className="eyebrow" style={{ marginTop: 6, fontSize: 9 }}>{o.k}</div>
                      </div>
                    ))}
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
                      <a href="/workflows" style={{ color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}>
                        open an agent
                      </a>{" "}
                      and hit Run.
                    </div>
                  ) : (
                    <div className="card" style={{ overflow: "hidden", padding: 0 }}>
                      {data.recent_activity.slice(0, 5).map(run => {
                        const statusBadge =
                          run.status === "succeeded" ? "sbadge ok"
                          : run.status === "failed" ? "sbadge err"
                          : run.status === "running" ? "sbadge run"
                          : run.status === "waiting_approval" || run.status === "waiting" ? "sbadge warn"
                          : "sbadge idle"

                        const statusLabel =
                          run.status === "succeeded" ? "Succeeded"
                          : run.status === "failed" ? "Failed"
                          : run.status === "running" ? "Running"
                          : run.status === "waiting_approval" || run.status === "waiting" ? "Awaiting"
                          : run.status

                        const runBorderColor =
                          run.status === "succeeded" ? "var(--ok)"
                          : run.status === "failed" ? "var(--err)"
                          : run.status === "running" ? "var(--info)"
                          : "var(--warn)"

                        return (
                          <a
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
                          </a>
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
                  <GuardSnapshot
                    tokenUsage={data.token_usage.total_tokens > 0 ? data.token_usage : null}
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
