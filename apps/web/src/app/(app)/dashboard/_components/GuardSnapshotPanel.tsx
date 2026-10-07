import Link from "next/link"
import { API } from "@/lib/api"
import type { GuardSnapshot, TokenUsage } from "./types"

/* ── SpendArc donut ── */

export function SpendArc({ pct, warn }: { pct: number, warn: boolean }) {
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


// #4: accepts spendCapUsd from Guard config API; #5: accepts guardSnapshot from API
export function GuardSnapshotPanel({
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
          href="/theguard"
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
        <div style={{ display: "flex", alignItems: "center", marginBottom: 9 }}>
          <span className="eyebrow" style={{ fontSize: 9.5 }}>Top policy hits · 30d</span>
          <Link href="/theguard/activity" style={{ marginLeft: "auto", fontSize: 11, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}>View all →</Link>
        </div>
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
        <div style={{ display: "flex", alignItems: "center", marginBottom: 9 }}>
          <span className="eyebrow" style={{ fontSize: 9.5 }}>Developer near limit</span>
          <Link href="/theguard/spend" style={{ marginLeft: "auto", fontSize: 11, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}>View all →</Link>
        </div>
        {developerNearLimit.length === 0 ? (
          <span style={{ fontSize: 12, color: "var(--ok)" }}>All developers within limits</span>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {developerNearLimit.slice(0, 5).map((dev, i) => {
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
