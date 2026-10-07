"use client"

import { useState, type MouseEvent as ReactMouseEvent } from "react"
import Link from "next/link"
import { formatTrigger, timeAgo } from "@/lib/runUtils"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import type { AttentionRun } from "./types"

/* ── Helpers ── */

export function SectionLabel({
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
export function KPI({
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
      onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { if (onClick) (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)" }}
      onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLElement).style.boxShadow = "" }}
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
export function PriorityItem({
  run,
  getToken,
}: {
  run: AttentionRun
  getToken: (() => Promise<string | null>) | null
}) {
  const { activeWorkspace } = useWorkspace()
  const { authFetch } = useAuthFetch()
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
    try {
      // The approve endpoint lives under the workflow-scoped router
      // (POST /workflows/{workflow_id}/runs/{run_id}/approve). AttentionRun
      // already carries workflow_id — using the workspace-scoped /runs prefix
      // 404s for every row, not just expired ones (#1672).
      const res = await authFetch(
        `${API}/workflows/${run.workflow_id}/runs/${run.run_id}/approve`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: approved ? "approved" : "rejected" }) }
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
