"use client"

import { authEnabled } from "@/lib/auth/runtime"


import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import AppShell from "@/components/AppShell"
import { statusStyle as _statusStyle, formatTrigger, timeAgo } from "@/lib/runUtils"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API, guard } from "@/lib/api"
import type { DashboardData } from "./_components/types"
import { KPI, PriorityItem, SectionLabel } from "./_components/widgets"
import { GuardSnapshotPanel } from "./_components/GuardSnapshotPanel"
import { AgentHealthRow, EmptyChecklist } from "./_components/AgentHealthRow"

// #10 #15: statusStyle imported with alias to suppress unused-var; timeAgo from runUtils (removed local duplicate)
void _statusStyle


// #15: removed fmtTokens (never called)
// #15: removed local timeAgo (duplicated runUtils export — using runUtils version above)



export default function DashboardPage() {
  const clerkEnabled = authEnabled()
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


/* ── Main content ── */

function DashboardContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const [data, setData] = useState<DashboardData | null>(null)
  // Per-section loading: dashLoading gates KPIs/activity/agents; guardLoading gates Guard snapshot + nudges
  const [dashLoading, setDashLoading] = useState(true)
  const [guardLoading, setGuardLoading] = useState(true)
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

  const { authFetch } = useAuthFetch()

  function buildWorkspaceId(): string | null {
    return activeWorkspace?.id ?? null
  }

  async function loadDash() {
    try {
      setError(null)
      const res = await authFetch(`${API}/dashboard`)
      if (res.ok) {
        setData(await res.json())
        setLastUpdated(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))
      } else {
        setError(`Failed to load dashboard (${res.status})`)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Network error")
    } finally {
      setDashLoading(false)
    }
  }

  async function loadGuard() {
    const workspaceId = buildWorkspaceId()
    if (!workspaceId) { setGuardLoading(false); return }
    try {
      const [toolsRes, meRes, guardConfig] = await Promise.all([
        authFetch(`${API}/guard/developer-tools`),
        authFetch(`${API}/guard/developer-tools/me`),
        // #4: fetch Guard config for spend cap
        guard.config.get(authFetch, workspaceId).catch(() => null),
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
      if (guardConfig) setSpendCapUsd(guardConfig.spend_limit_usd ?? null)
    } catch {
      // non-fatal — keep last known state
    } finally {
      setGuardLoading(false)
    }
  }

  // Fire both fetches in parallel — sections render as soon as their data arrives
  function loadAll() {
    loadDash()
    loadGuard()
  }

  useEffect(() => {
    loadAll()

    // #16: re-fetch every 30 seconds; pause when tab is hidden
    const interval = setInterval(() => {
      if (document.visibilityState === "hidden") return
      loadAll()
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

  const policyBlocksToday = data?.guard_blocks_today

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
            <button
              className="btn btn-ghost"
              onClick={() => loadAll()}
            >
              Refresh
            </button>
            <Link href="/workflows/new" className="btn btn-primary">
              <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} style={{ display: "inline", verticalAlign: "middle", marginRight: 5 }}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
              </svg>
              New agent
            </Link>
          </div>
        </div>

        {/* #14: Personal sync nudge — shown once guardLoading resolves */}
        {!guardLoading && !dismissedPersonalNudge && mySynced === false && guardSynced === true && (
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

        {/* #14: Guard sync nudge — shown once guardLoading resolves */}
        {!guardLoading && !dismissedGuardNudge && guardSynced === false && (
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
            <Link href="/theguard" style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}>
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

        {error && !data ? (
          // #13: error card with retry — only shown when no prior data exists
          <div className="card" role="alert" style={{ padding: "24px 28px", maxWidth: 480 }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--err)", marginBottom: 8 }}>
              Could not load dashboard
            </div>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>{error}</p>
            <button
              className="btn btn-primary"
              onClick={() => loadDash()}
            >
              Retry
            </button>
          </div>
        ) : dashLoading && !data ? (
          // Initial skeleton — only shown before any data has arrived
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <style>{`@keyframes dash-pulse { 0%,100% { opacity: 0.4 } 50% { opacity: 0.2 } }`}</style>
            {/* KPI skeleton */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="card" style={{ flex: 1, minWidth: 160, height: 80, animation: "dash-pulse 1.5s ease-in-out infinite" }} />
              ))}
            </div>
            {/* 2-column skeleton */}
            <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 22 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <div className="card" style={{ height: 200, animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                <div className="card" style={{ height: 160, animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                <div className="card" style={{ height: 220, animation: "dash-pulse 1.5s ease-in-out infinite" }} />
              </div>
              <div>
                <div className="card" style={{ height: 320, animation: "dash-pulse 1.5s ease-in-out infinite" }} />
              </div>
            </div>
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
                onClick={() => router.push("/theguard/spend")}
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
                <SectionLabel action="View all →" href="/workflows">Agent Health</SectionLabel>
                <div className="card" style={{ overflow: "hidden", padding: 0 }}>
                  {/* Table header: 4-col grid — Agent | Status | Success rate | Grade */}
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
                  {/* Pulse rows visible during polling refresh — data stays mounted */}
                  {dashLoading ? (
                    <>
                      <style>{`@keyframes dash-pulse { 0%,100% { opacity: 0.4 } 50% { opacity: 0.2 } }`}</style>
                      {[1, 2, 3].map(i => (
                        <div key={i} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 0.9fr", gap: 12, padding: "13px 16px", borderBottom: "1px solid var(--border)" }}>
                          <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                          <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                          <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                          <div style={{ height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                        </div>
                      ))}
                    </>
                  ) : (
                    data.agent_health.slice(0, 5).map(agent => (
                      <AgentHealthRow key={agent.workflow_id} agent={agent} />
                    ))
                  )}
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
                  <SectionLabel action="View all →" href="/runs?filter=waiting">
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
                      {data.needs_attention.slice(0, 5).map(run => (
                        <PriorityItem key={run.run_id} run={run} getToken={getToken} />
                      ))}
                    </div>
                  )}
                </div>

                {/* Outcomes */}
                <div>
                  {/* #18: "View all" link in Outcomes header */}
                  <SectionLabel action="View all →" href="/runs">
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
                  <SectionLabel action="View all →" href="/runs">Recent activity</SectionLabel>
                  {dashLoading ? (
                    <div className="card" style={{ overflow: "hidden", padding: 0 }}>
                      {[1, 2, 3].map(i => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
                          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                            <div style={{ height: 13, width: "55%", borderRadius: 4, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                            <div style={{ height: 11, width: "35%", borderRadius: 4, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                          </div>
                          <div style={{ height: 19, width: 70, borderRadius: 10, background: "var(--surface-3)", animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                        </div>
                      ))}
                    </div>
                  ) : data.recent_activity.length === 0 ? (
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
                            onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLElement).style.background = "var(--surface-2)" }}
                            onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLElement).style.background = "" }}
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

                {/* Guard snapshot — independent loading state */}
                <div>
                  <SectionLabel>Guard</SectionLabel>
                  {guardLoading ? (
                    <div className="card" style={{ height: 200, animation: "dash-pulse 1.5s ease-in-out infinite" }} />
                  ) : (
                    <GuardSnapshotPanel
                      tokenUsage={data.token_usage.total_tokens > 0 ? data.token_usage : null}
                      spendCapUsd={spendCapUsd}
                      guardSnapshot={data.guard_snapshot}
                    />
                  )}
                </div>

              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}