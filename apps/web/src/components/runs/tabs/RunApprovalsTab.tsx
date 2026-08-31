"use client"

import { isAwaiting } from "@/lib/runUtils"
import type { RunMeta } from "@/components/runs/RunDetailPanel"

export interface RunApprovalsTabProps {
  run: RunMeta
  approvalDecision: "approved" | "rejected" | null
  approvingRun: boolean
  onApproval: (decision: "approved" | "rejected") => void
}

export default function RunApprovalsTab({ run, approvalDecision, approvingRun, onApproval }: RunApprovalsTabProps) {
  if (isAwaiting(run.status)) return <AwaitingReview run={run} approvingRun={approvingRun} onApproval={onApproval} />
  if (approvalDecision) return <DecisionRecorded decision={approvalDecision} />
  return <PriorDecisions state={run.state as Record<string, unknown> | null} />
}

function AwaitingReview({ run, approvingRun, onApproval }: { run: RunMeta; approvingRun: boolean; onApproval: (d: "approved" | "rejected") => void }) {
  const st = run.state as Record<string, unknown> | null
  const g = st?.__pending_guard_approval as
    | { rule_id?: string; message?: string; approval_url?: string; approval_id?: string }
    | undefined

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <span className="chip bk-approval" style={{ height: 21, fontSize: 9.5, fontWeight: 800, letterSpacing: ".07em", textTransform: "uppercase" }}>Approval</span>
        <span style={{ fontWeight: 650, fontSize: 14 }}>Awaiting review</span>
      </div>
      <div style={{ padding: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 16 }}>
          <span className="dot pulse" style={{ background: "var(--warn)" }} />
          <span style={{ fontSize: 13.5, color: "var(--text-2)" }}>The run is paused and waiting for a human decision before it continues.</span>
        </div>
        {run.trigger_summary && (
          <div className="card" style={{ padding: "12px 14px", background: "var(--surface-2)", marginBottom: 16 }}>
            <div style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.5 }}>{run.trigger_summary}</div>
          </div>
        )}
        {g?.rule_id && (
          <div className="card" style={{ padding: "12px 14px", background: "var(--warn-bg)", marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--warn)", marginBottom: 4 }}>
              Triggered by Guard rule
            </div>
            <div style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "var(--text)" }}>{g.rule_id}</div>
            {g.message && (
              <div style={{ fontSize: 12.5, color: "var(--text-2)", marginTop: 4 }}>{g.message}</div>
            )}
            {g.approval_url && (
              <div style={{ marginTop: 8, fontSize: 12 }}>
                <a href={g.approval_url} style={{ color: "var(--accent)", textDecoration: "underline" }}>
                  Open in /theguard/approvals →
                </a>
              </div>
            )}
          </div>
        )}
        <div style={{ display: "flex", gap: 9 }}>
          <button
            className="btn btn-accent"
            disabled={approvingRun}
            onClick={() => onApproval("approved")}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}><polyline points="20 6 9 17 4 12"/></svg>
            Approve &amp; continue
          </button>
          <button
            className="btn btn-ghost"
            disabled={approvingRun}
            onClick={() => onApproval("rejected")}
            style={{ color: "var(--err)", borderColor: "var(--err-bd)", display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            Reject
          </button>
        </div>
      </div>
    </div>
  )
}

function DecisionRecorded({ decision }: { decision: "approved" | "rejected" }) {
  return (
    <div className="card" style={{ padding: "16px 18px", display: "flex", alignItems: "center", gap: 12 }}>
      <span style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, display: "grid", placeItems: "center", background: decision === "approved" ? "var(--ok-bg)" : "var(--err-bg)", color: decision === "approved" ? "var(--ok)" : "var(--err)" }}>
        {decision === "approved"
          ? <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}><polyline points="20 6 9 17 4 12"/></svg>
          : <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>}
      </span>
      <div>
        <div style={{ fontWeight: 600, fontSize: 13.5, textTransform: "capitalize" }}>{decision}</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>just now</div>
      </div>
    </div>
  )
}

function PriorDecisions({ state }: { state: Record<string, unknown> | null }) {
  const approvals = Object.entries(state ?? {})
    .filter(([k]) => k.startsWith("__approval_"))
    .map(([k, v]) => {
      const blockId = k.replace("__approval_", "")
      const blockState = (state ?? {})[blockId] as Record<string, unknown> | undefined
      const displayLabel = (blockState?.label ?? blockState?.name ?? blockId) as string
      return { blockId, displayLabel, decision: v as string }
    })

  if (approvals.length === 0) return (
    <div style={{ textAlign: "center", padding: "48px 0" }}>
      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No approval decisions recorded for this run.</p>
    </div>
  )

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {approvals.map(({ blockId, displayLabel, decision }, i) => (
        <div key={blockId} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
          <span style={{ fontSize: 12.5, color: "var(--text-2)" }}>{displayLabel}</span>
          <span className={`sbadge ${decision === "approved" ? "ok" : "err"}`}>{decision}</span>
        </div>
      ))}
    </div>
  )
}
