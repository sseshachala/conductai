"use client"

import { GuardSectionHeader, timeAgo } from "@/components/guard/common"

// ── Awaiting Approval — pending HITL requests from guard_approval_requests
// Reuses the existing /guard/approvals API (perm: platform.approvals.decide,
// enforced server-side — inbox resolve perms are NOT reused). Each row is
// individually actionable; no dedup / alert merge (per reviewer P2).
export interface PendingApproval {
  id: string
  rule_id: string
  rule_pack: string | null
  rule_message: string | null
  tool_name: string | null
  requester_email: string | null
  source_run_id: string | null
  created_at: string
  timeout_at: string
  approval_type: string
}
export interface ApprovalListOut {
  workspace_id: string
  items: PendingApproval[]
}

export function AwaitingApprovals({
  approvals, approvalsError, decidingId, rejectingId, rejectReason, setRejectReason,
  submitDecision, beginReject, confirmReject, cancelReject,
}: {
  approvals: PendingApproval[]
  approvalsError: string | null
  decidingId: string | null
  rejectingId: string | null
  rejectReason: string
  setRejectReason: (v: string) => void
  submitDecision: (id: string, decision: "approved" | "rejected", reason?: string) => Promise<void>
  beginReject: (id: string) => void
  confirmReject: (id: string) => Promise<void>
  cancelReject: () => void
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <GuardSectionHeader title="Awaiting approval" subtitle={`${approvals.length} pending`} />
      {approvalsError && (
        <div style={{
          padding: "10px 12px",
          marginTop: 8,
          borderRadius: 6,
          background: "var(--err-bg)",
          color: "var(--err)",
          fontSize: 12,
        }}>
          {approvalsError}
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
        {approvals.map(a => {
          const busy = decidingId === a.id
          const timeoutIn = (() => {
            const t = new Date(a.timeout_at).getTime() - Date.now()
            if (Number.isNaN(t)) return null
            const mins = Math.max(0, Math.round(t / 60000))
            return mins < 60
              ? `${mins}m left`
              : `${Math.round(mins / 60)}h left`
          })()
          const rejecting = rejectingId === a.id
          return (
            <div
              key={a.id}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 8,
                padding: "10px 12px",
                border: "1px solid var(--border)",
                borderRadius: 8,
                background: "var(--surface)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                    <span style={{
                      fontFamily: "var(--font-mono, monospace)",
                      color: "var(--text)",
                    }}>{a.rule_id}</span>
                    {a.rule_pack && (
                      <span style={{ color: "var(--text-muted)" }}>({a.rule_pack})</span>
                    )}
                    {a.approval_type === "peer" && (
                      <span style={{
                        fontSize: 10,
                        padding: "1px 5px",
                        background: "var(--info-bg)",
                        color: "var(--info)",
                        borderRadius: 3,
                        fontWeight: 700,
                      }}>PEER</span>
                    )}
                    {timeoutIn && (
                      <span style={{ color: "var(--text-muted)", marginLeft: "auto" }}>
                        {timeoutIn}
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize: 13,
                    color: "var(--text)",
                    marginTop: 3,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {a.rule_message || "Guard rule requires approval."}
                  </div>
                  <div style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    marginTop: 3,
                  }}>
                    {a.requester_email || "unknown"}
                    {a.tool_name ? ` · ${a.tool_name}` : ""}
                    {" · "}{timeAgo(new Date(a.created_at))}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <button
                    onClick={() => void submitDecision(a.id, "approved")}
                    disabled={busy || rejecting}
                    style={{
                      padding: "6px 12px",
                      fontSize: 12,
                      fontWeight: 600,
                      border: "1px solid var(--ok-bd, #16a34a)",
                      borderRadius: 6,
                      background: "var(--ok-bg, #dcfce7)",
                      color: "var(--ok, #15803d)",
                      cursor: busy ? "wait" : "pointer",
                      opacity: (busy || rejecting) ? 0.5 : 1,
                    }}
                  >
                    Approve
                  </button>
                  {!rejecting && (
                    <button
                      onClick={() => beginReject(a.id)}
                      disabled={busy}
                      style={{
                        padding: "6px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        border: "1px solid var(--err-bd, #dc2626)",
                        borderRadius: 6,
                        background: "var(--err-bg, #fee2e2)",
                        color: "var(--err, #b91c1c)",
                        cursor: busy ? "wait" : "pointer",
                        opacity: busy ? 0.6 : 1,
                      }}
                    >
                      Reject
                    </button>
                  )}
                  {a.source_run_id && (
                    <a
                      href={`/runs/${a.source_run_id}`}
                      style={{
                        padding: "6px 10px",
                        fontSize: 12,
                        color: "var(--text-muted)",
                        textDecoration: "none",
                        alignSelf: "center",
                      }}
                    >
                      Run ↗
                    </a>
                  )}
                </div>
              </div>
              {rejecting && (
                // Reviewer P1 (round 2): API requires a non-empty
                // reason on reject. Inline input; Submit hits the
                // server, Cancel dismisses without a request.
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="text"
                    autoFocus
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && rejectReason.trim()) {
                        void confirmReject(a.id)
                      } else if (e.key === "Escape") {
                        cancelReject()
                      }
                    }}
                    placeholder="Why are you rejecting? (required)"
                    disabled={busy}
                    style={{
                      flex: 1,
                      padding: "6px 10px",
                      fontSize: 12,
                      border: "1px solid var(--err-bd, #dc2626)",
                      borderRadius: 6,
                      background: "var(--surface)",
                      color: "var(--text)",
                      outline: "none",
                    }}
                  />
                  <button
                    onClick={() => void confirmReject(a.id)}
                    disabled={busy || !rejectReason.trim()}
                    style={{
                      padding: "6px 12px",
                      fontSize: 12,
                      fontWeight: 600,
                      border: "1px solid var(--err-bd, #dc2626)",
                      borderRadius: 6,
                      background: "var(--err, #dc2626)",
                      color: "#fff",
                      cursor: (busy || !rejectReason.trim()) ? "not-allowed" : "pointer",
                      opacity: (busy || !rejectReason.trim()) ? 0.5 : 1,
                    }}
                  >
                    Submit reject
                  </button>
                  <button
                    onClick={cancelReject}
                    disabled={busy}
                    style={{
                      padding: "6px 10px",
                      fontSize: 12,
                      color: "var(--text-muted)",
                      background: "transparent",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      cursor: busy ? "wait" : "pointer",
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
