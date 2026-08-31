"use client"

import { formatTrigger, isAwaiting } from "@/lib/runUtils"
import type { RunMeta } from "@/components/runs/RunDetailPanel"

export interface RunSummaryTabProps {
  run: RunMeta
  projectName: string | null
}

export default function RunSummaryTab({ run, projectName }: RunSummaryTabProps) {
  const triggerCtx = run.state as Record<string, unknown> | null | undefined
  const t = ((triggerCtx?._trigger ?? triggerCtx?.github_issue) ?? {}) as Record<string, unknown>
  const issueNum = t.issue_number as number | undefined
  const issueTitle = (t.title ?? t.issue_title) as string | undefined
  const prUrl = triggerCtx?.pr_url as string | undefined
  const prNum = (t.pull_request as Record<string, unknown>)?.number as number | undefined

  return (
    <div>
      {/* 2-col meta grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 40px", maxWidth: 720 }}>
        {([
          ["Triggered by", formatTrigger(run.triggered_by), true],
          ["Started",      run.started_at ? new Date(run.started_at).toLocaleString() : "—", false],
          ["Completed",    run.completed_at ? new Date(run.completed_at).toLocaleString() : "—", false],
          ["Version",      run.workflow_version_id?.slice(0, 8) ?? "—", true],
          ["Project",      projectName ?? "—", false],
          ["Repository",   run.repo ?? "—", true],
        ] as [string, string, boolean][]).map(([label, value, mono]) => (
          <div key={label} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
            <div className={mono ? "mono" : ""} style={{ fontSize: 13.5, fontWeight: 550 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Approval notice */}
      {isAwaiting(run.status) && (
        <div className="card" style={{ marginTop: 24, padding: "16px 18px", display: "flex", gap: 13, alignItems: "flex-start", maxWidth: 720 }}>
          <span style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--warn-bg)", color: "var(--warn)" }}>
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx={12} cy={12} r={10} /><polyline points="12 6 12 12 16 14" />
            </svg>
          </span>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 2 }}>Paused on approval</div>
            <div style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.5 }}>This run is waiting on a human decision in the <b>Approvals</b> tab before the run continues.</div>
          </div>
        </div>
      )}

      {/* PR links */}
      {(issueNum || (prNum && prUrl)) && (
        <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 10 }}>
          {issueNum && <span className="chip">{`Issue #${issueNum}${issueTitle ? ` — ${issueTitle}` : ""}`}</span>}
          {prNum && prUrl && <a href={prUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}>PR #{prNum} →</a>}
        </div>
      )}
    </div>
  )
}
