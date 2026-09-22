"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import {
  GuardBadge,
  GuardFilterBar,
  GuardPageHeader,
  GuardSectionHeader,
  timeAgo,
  type FilterPill,
} from "@/components/guard/common"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { AgentAvatar } from "@/components/guard/AgentAvatar"
import { guard, guardInbox } from "@/lib/api"
import { API } from "@/lib/api/client"
import type {
  InboxRow,
  InboxEvent,
  InboxStatus,
  InboxSeverity,
  InboxSource,
  ResolvedReason,
} from "@/lib/api"

// ── Awaiting Approval — pending HITL requests from guard_approval_requests
// Reuses the existing /guard/approvals API (perm: platform.approvals.decide,
// enforced server-side — inbox resolve perms are NOT reused). Each row is
// individually actionable; no dedup / alert merge (per reviewer P2).
interface PendingApproval {
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
interface ApprovalListOut {
  workspace_id: string
  items: PendingApproval[]
}

const REASON_LABEL: Record<ResolvedReason, string> = {
  expected:         "Expected — working as intended",
  escalated:        "Escalated to security team",
  exception_added:  "Exception added to policy",
  false_positive:   "False positive — rule too broad",
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function GuardInboxPage() {
  const { authFetch, workspaceId } = useAuthFetch()
  const [rows, setRows] = useState<InboxRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)

  const [statusFilter, setStatusFilter] = useState<InboxStatus | "all">("open")
  const [severityFilter, setSeverityFilter] = useState<InboxSeverity | "all">("all")
  const [sourceFilter, setSourceFilter] = useState<InboxSource | "all">("all")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [events, setEvents] = useState<Record<string, InboxEvent[]>>({})
  const [busyId, setBusyId] = useState<string | null>(null)

  // Resolve form state — one row can be open at a time so a flat map is fine.
  const [reasonMap, setReasonMap] = useState<Record<string, ResolvedReason>>({})
  const [noteMap, setNoteMap] = useState<Record<string, string>>({})

  // Extend-backfill state
  const [backfillDays, setBackfillDays] = useState<number>(60)
  const [backfillBusy, setBackfillBusy] = useState(false)
  const [backfillMsg, setBackfillMsg] = useState<string | null>(null)

  // Auto-close config state — persisted server-side on guard_config.
  // null = still loading / not applicable.
  const [autoCloseDays, setAutoCloseDays] = useState<number | null>(null)
  const [autoCloseSaving, setAutoCloseSaving] = useState(false)
  const [autoCloseMsg, setAutoCloseMsg] = useState<string | null>(null)

  // #2170-follow-up Inbox correctness — race protection for polling.
  // Reviewer P2 (round 2): earlier version bailed early if a fetch was
  // in flight, so a workspace/filter switch DURING an in-flight
  // response left the epoch un-advanced and the stale response
  // clobbered the new view. Same trap applied to approvals.
  //
  // Correct pattern (both fetches):
  //   - ALWAYS advance the epoch on load(). Never early-return.
  //   - Late responses drop themselves on the OUTPUT side by
  //     comparing myEpoch to the current epoch after await.
  //   - Overlapping requests are cheap; only the most recent one
  //     commits state.
  //   - Workspace change hard-resets workspace-scoped state via the
  //     effect below; any in-flight response can't repopulate.

  // ── Awaiting Approval fetch + decide (PR 2, race protection round 2) ──
  const [approvals, setApprovals] = useState<PendingApproval[]>([])
  const [approvalsError, setApprovalsError] = useState<string | null>(null)
  const [decidingId, setDecidingId] = useState<string | null>(null)
  // Per-row rejection reason input. Reviewer P1 (round 2): the API
  // requires a non-empty reason on reject; the previous "send
  // undefined" always 400'd. Keep the input inline, one row's worth
  // of state at a time.
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState<string>("")
  const approvalsEpochRef = useRef(0)

  const loadApprovals = useCallback(async (opts?: { background?: boolean }) => {
    const myEpoch = ++approvalsEpochRef.current
    if (!opts?.background) setApprovalsError(null)
    try {
      const res = await authFetch(`${API}/guard/approvals?status=pending&limit=50`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `HTTP ${res.status}`)
      }
      const data: ApprovalListOut = await res.json()
      if (myEpoch !== approvalsEpochRef.current) return
      // Reviewer P2 (round 2): the list endpoint sweeps pending rows to
      // timed_out and RETURNS them. Filter here so we don't render
      // Approve/Reject buttons for something the backend will 409 on.
      // Empty status defaults to "pending" (backend contract) so
      // rows without a status shouldn't happen, but be defensive.
      const stillActionable = (data.items || []).filter(a =>
        !("status" in a) || (a as { status?: string }).status === "pending",
      )
      setApprovals(stillActionable)
    } catch (e) {
      if (myEpoch !== approvalsEpochRef.current) return
      setApprovalsError(e instanceof Error ? e.message : "approvals load failed")
    }
  }, [authFetch])

  const submitDecision = useCallback(async (
    id: string,
    decision: "approved" | "rejected",
    reason?: string,
  ) => {
    setDecidingId(id)
    setApprovalsError(null)
    try {
      const res = await authFetch(`${API}/guard/approvals/${id}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason }),
      })
      if (res.status === 409) {
        const body = await res.json().catch(() => ({}))
        setApprovalsError(body?.detail || "Another approver already decided this request.")
      } else if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(body?.detail || `HTTP ${res.status}`)
      }
      // Refresh from the server so approved/rejected rows disappear
      // and any concurrent expiries show up.
      await loadApprovals({ background: true })
      // Reset any open reject-reason input.
      setRejectingId(null)
      setRejectReason("")
    } catch (e) {
      setApprovalsError(e instanceof Error ? e.message : "decide failed")
    } finally {
      setDecidingId(null)
    }
  }, [authFetch, loadApprovals])

  const beginReject = useCallback((id: string) => {
    // First click on Reject expands the reason input. Second click
    // (Submit) hits the server with a required non-empty reason.
    setRejectingId(id)
    setRejectReason("")
  }, [])

  const confirmReject = useCallback(async (id: string) => {
    const reason = rejectReason.trim()
    if (!reason) {
      setApprovalsError("A reason is required when rejecting an approval.")
      return
    }
    await submitDecision(id, "rejected", reason)
  }, [rejectReason, submitDecision])

  const cancelReject = useCallback(() => {
    setRejectingId(null)
    setRejectReason("")
  }, [])

  // ── Inbox findings fetch ──
  const epochRef = useRef(0)

  const load = useCallback(async (opts?: { background?: boolean }) => {
    const myEpoch = ++epochRef.current
    if (!opts?.background) setLoading(true)
    setError(null)
    try {
      const data = await guardInbox.list(authFetch, {
        status: statusFilter === "all" ? undefined : statusFilter,
        severity: severityFilter === "all" ? undefined : severityFilter,
        source: sourceFilter === "all" ? undefined : sourceFilter,
        limit: 200,
      })
      if (myEpoch !== epochRef.current) return  // stale — a newer fetch already ran
      setRows(data)
      setLastFetched(new Date())
    } catch (e) {
      if (myEpoch !== epochRef.current) return
      setError(e instanceof Error ? e.message : "load failed")
    } finally {
      // Only clear loading if we're still the most-recent fetch;
      // otherwise the newer fetch owns the spinner state.
      if (myEpoch === epochRef.current && !opts?.background) setLoading(false)
    }
  }, [authFetch, statusFilter, severityFilter, sourceFilter])

  // Workspace change: hard-reset workspace-scoped state so a late
  // response from the previous workspace can't repopulate either the
  // findings list or the approvals section. Both epoch refs bump so
  // any in-flight fetch fails its freshness check on return.
  useEffect(() => {
    epochRef.current += 1
    approvalsEpochRef.current += 1
    setRows([])
    setError(null)
    setExpandedId(null)
    setEvents({})
    setLastFetched(null)
    setApprovals([])
    setApprovalsError(null)
    setRejectingId(null)
    setRejectReason("")
  }, [workspaceId])

  useEffect(() => { void load() }, [load])
  useEffect(() => { void loadApprovals() }, [loadApprovals])

  // 15s polling while the tab is visible. Pauses while hidden; refreshes
  // immediately on becoming visible again. Cleans up on unmount and on
  // dep-change (filter switch cancels the previous interval). Ticks
  // BOTH inbox findings and pending approvals on the same cadence.
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null

    const tick = () => {
      void load({ background: true })
      void loadApprovals({ background: true })
    }
    const start = () => {
      if (intervalId !== null) return
      intervalId = setInterval(tick, 15_000)
    }
    const stop = () => {
      if (intervalId !== null) {
        clearInterval(intervalId)
        intervalId = null
      }
    }
    const onVis = () => {
      if (document.visibilityState === "visible") {
        tick()  // instant refresh on return
        start()
      } else {
        stop()
      }
    }

    if (document.visibilityState === "visible") start()
    document.addEventListener("visibilitychange", onVis)
    return () => {
      document.removeEventListener("visibilitychange", onVis)
      stop()
    }
  }, [load, loadApprovals])

  // Load auto-close config once we have a workspace.
  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    ;(async () => {
      try {
        const cfg = await guard.config.get(authFetch, workspaceId)
        if (!cancelled && cfg) {
          setAutoCloseDays(
            typeof cfg.inbox_auto_close_days === "number"
              ? cfg.inbox_auto_close_days
              : 30,
          )
        }
      } catch {
        // Non-fatal — settings row hides if we couldn't load.
      }
    })()
    return () => { cancelled = true }
  }, [authFetch, workspaceId])

  const saveAutoCloseDays = useCallback(async (next: number) => {
    if (!workspaceId) return
    setAutoCloseSaving(true)
    setAutoCloseMsg(null)
    try {
      await guard.config.patch(authFetch, workspaceId, { inbox_auto_close_days: next })
      setAutoCloseDays(next)
      setAutoCloseMsg(
        next === 0
          ? "Auto-close disabled — no rows will resolve automatically."
          : `Open rows auto-close after ${next} days without re-fire.`,
      )
    } catch (e) {
      setAutoCloseMsg(e instanceof Error ? e.message : "Save failed")
    } finally {
      setAutoCloseSaving(false)
    }
  }, [authFetch, workspaceId])

  const toggleExpand = useCallback(async (row: InboxRow) => {
    if (expandedId === row.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(row.id)
    if (!events[row.id]) {
      try {
        const ev = await guardInbox.events(authFetch, row.id, 20)
        setEvents(prev => ({ ...prev, [row.id]: ev }))
      } catch (e) {
        setError(e instanceof Error ? e.message : "events load failed")
      }
    }
  }, [authFetch, events, expandedId])

  const applyStatus = useCallback(async (row: InboxRow, next: InboxStatus) => {
    setBusyId(row.id)
    try {
      const reason = reasonMap[row.id]
      const note = noteMap[row.id]
      const updated = await guardInbox.patch(authFetch, row.id, {
        status: next,
        resolved_reason: next === "resolved" ? reason : undefined,
        resolved_note: next === "resolved" ? note : undefined,
      })
      setRows(prev => prev.map(r => (r.id === row.id ? updated : r)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "update failed")
    } finally {
      setBusyId(null)
    }
  }, [authFetch, reasonMap, noteMap])

  const runBackfill = useCallback(async () => {
    setBackfillBusy(true)
    setBackfillMsg(null)
    try {
      const r = await guardInbox.backfill(authFetch, backfillDays)
      // Backfill response is {days, inserted, reconciled} — inserted =
      // brand-new inbox rows created for dedup groups that didn't
      // exist yet; reconciled = existing rows whose occurrences /
      // severity / timestamps were repaired against the authoritative
      // audit history. Show both so operators can tell what actually
      // changed on a re-run vs an initial sync.
      setBackfillMsg(
        `Synced last ${r.days} days — ${r.inserted} new, ${r.reconciled} reconciled.`,
      )
      await load()
    } catch (e) {
      setBackfillMsg(e instanceof Error ? e.message : "backfill failed")
    } finally {
      setBackfillBusy(false)
    }
  }, [authFetch, backfillDays, load])

  const counts = useMemo(() => {
    const c = { open: 0, triaging: 0, resolved: 0 }
    for (const r of rows) {
      if (r.status === "open") c.open += 1
      else if (r.status === "triaging") c.triaging += 1
      else if (r.status === "resolved") c.resolved += 1
    }
    return c
  }, [rows])

  return (
    <AppShell>
      <GuardShell lastFetched={lastFetched}>
        <GuardPageHeader
          title="Inbox"
          description="Deduped triage of blocked, warned, and approved events. One row per rule × source × message."
          lastUpdated={lastFetched}
          right={
            <>
              <span>Sync last</span>
              <select
                value={backfillDays}
                onChange={e => setBackfillDays(Number(e.target.value))}
                disabled={backfillBusy}
                style={{
                  background: "var(--surface)",
                  color: "var(--text)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  padding: "4px 8px",
                  fontSize: 12,
                }}
              >
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
              </select>
              <button
                onClick={runBackfill}
                disabled={backfillBusy}
                style={{
                  background: "var(--surface)",
                  color: "var(--text)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  padding: "4px 12px",
                  fontSize: 12,
                  cursor: backfillBusy ? "wait" : "pointer",
                }}
              >
                {backfillBusy ? "Syncing…" : "Sync now"}
              </button>
            </>
          }
        />

        {backfillMsg && (
          <div style={{
            fontSize: 12, color: "var(--text-muted)", padding: "6px 10px",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 4, marginBottom: 12,
          }}>
            {backfillMsg}
          </div>
        )}

        {/* Auto-close settings row — persisted on guard_config. Hidden
            until the config request lands so we don't flash "30" and
            then jump to the real value. The backend caps this at 0-90
            to match /guard/inbox/backfill semantics. */}
        {autoCloseDays !== null && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            fontSize: 12, color: "var(--text-muted)",
            padding: "8px 12px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 4,
            marginBottom: 12,
          }}>
            <span>Auto-close open rows after</span>
            <select
              value={autoCloseDays}
              disabled={autoCloseSaving}
              onChange={e => saveAutoCloseDays(Number(e.target.value))}
              style={{
                background: "var(--surface)", color: "var(--text)",
                border: "1px solid var(--border)", borderRadius: 4,
                padding: "3px 8px", fontSize: 12,
              }}
            >
              <option value={0}>never</option>
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
            </select>
            <span>without re-fire</span>
            {autoCloseSaving && <span style={{ opacity: 0.6 }}>saving…</span>}
            {autoCloseMsg && !autoCloseSaving && (
              <span style={{ marginLeft: "auto", fontStyle: "italic" }}>{autoCloseMsg}</span>
            )}
          </div>
        )}

        {/* Awaiting Approval — pending HITL requests. Section stays
            visible while any pending approval exists; hides when the
            list drains. Each row is individually actionable; buttons
            call /guard/approvals/{id}/decide and refresh the list.
            Server-side auth via platform.approvals.decide — the inbox
            resolve permission is NOT reused. */}
        {(approvals.length > 0 || approvalsError) && (
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
        )}

        <GuardFilterBar<InboxStatus | "all">
          pills={([
            { value: "open",     label: "Open",     count: counts.open },
            { value: "triaging", label: "Triaging", count: counts.triaging },
            { value: "resolved", label: "Resolved", count: counts.resolved },
            { value: "all",      label: "All" },
          ] as const) as readonly FilterPill<InboxStatus | "all">[]}
          active={statusFilter}
          onChange={setStatusFilter}
        >
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value as InboxSeverity | "all")}
            style={{
              background: "var(--surface)", color: "var(--text)",
              border: "1px solid var(--border)", borderRadius: 4,
              padding: "6px 8px", fontSize: 12,
            }}
          >
            <option value="all">All severities</option>
            <option value="critical">Critical</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value as InboxSource | "all")}
            style={{
              background: "var(--surface)", color: "var(--text)",
              border: "1px solid var(--border)", borderRadius: 4,
              padding: "6px 8px", fontSize: 12,
            }}
          >
            <option value="all">All sources</option>
            <option value="gateway">Gateway</option>
            <option value="proxy">Proxy (legacy)</option>
            <option value="mcp">MCP</option>
            <option value="hook">Hook</option>
            <option value="runtime">Runtime</option>
          </select>
        </GuardFilterBar>

        {error && (
          <div style={{
            fontSize: 12, color: "var(--err)", padding: "8px 12px",
            background: "var(--err-bg)", borderRadius: 4, marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        {loading && rows.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", padding: 20, textAlign: "center" }}>
            Loading…
          </div>
        )}

        {!loading && rows.length === 0 && (
          <div style={{
            fontSize: 13, color: "var(--text-muted)", padding: 40, textAlign: "center",
            background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: 6,
          }}>
            No events in this view. Blocked, warned, and approved decisions land here as they happen.
          </div>
        )}

        {rows.length > 0 && (
          <div style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
            {rows.map((row, idx) => {
              const isExpanded = expandedId === row.id
              const rowEvents = events[row.id] ?? []
              return (
                <div key={row.id} style={{
                  borderTop: idx === 0 ? "none" : "1px solid var(--border)",
                  background: isExpanded ? "var(--surface-alt, var(--surface))" : "transparent",
                }}>
                  <div
                    onClick={() => toggleExpand(row)}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "80px 1fr 80px 32px 100px 100px 40px",
                      gap: 12,
                      padding: "12px 16px",
                      alignItems: "center",
                      cursor: "pointer",
                      fontSize: 13,
                    }}
                  >
                    <GuardBadge kind="severity" value={row.severity} />
                    <div style={{ overflow: "hidden" }}>
                      <div style={{ color: "var(--text)", fontWeight: 500, marginBottom: 2 }}>
                        {row.rule_id}
                      </div>
                      <div style={{
                        color: "var(--text-muted)", fontSize: 12,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {row.description ?? <em style={{ opacity: 0.6 }}>no description</em>}
                      </div>
                    </div>
                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                      {row.source}
                    </span>
                    <AgentAvatar agentId={row.agent_identity_id} size={22} />
                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                      {row.occurrences}× · {timeAgo(row.last_seen_at)}
                    </span>
                    <GuardBadge kind="status" value={row.status} />
                    <span style={{ color: "var(--text-muted)", textAlign: "right" }}>
                      {isExpanded ? "▾" : "▸"}
                    </span>
                  </div>

                  {isExpanded && (
                    <div style={{ padding: "0 16px 16px 16px", borderTop: "1px solid var(--border)" }}>
                      {/* Recent events */}
                      <div style={{ marginTop: 12, marginBottom: 16 }}>
                        <GuardSectionHeader title="Recent events" subtitle={`${rowEvents.length}`} />
                        {rowEvents.length === 0 && (
                          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No events loaded yet.</div>
                        )}
                        {rowEvents.length > 0 && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                            {rowEvents.map(e => (
                              <div key={e.id} style={{
                                display: "grid", gridTemplateColumns: "120px 80px 28px 1fr 1fr",
                                gap: 8, padding: "4px 8px",
                                background: "var(--surface)", borderRadius: 3, color: "var(--text-muted)",
                              }}>
                                <span>{timeAgo(e.ts)}</span>
                                <GuardBadge kind="decision" value={e.decision} />
                                <AgentAvatar agentId={e.agent_identity_id} size={20} />
                                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {e.ai_tool ?? "-"} {e.user_email ? `· ${e.user_email}` : ""}
                                </span>
                                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {e.provider ? `${e.provider}/${e.model}` : (e.input_summary ?? "")}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Resolve form */}
                      {row.status !== "resolved" && (
                        <div style={{
                          padding: 12, background: "var(--surface)", borderRadius: 6,
                          border: "1px solid var(--border)",
                        }}>
                          <GuardSectionHeader title="Resolve" />
                          <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                            {(Object.keys(REASON_LABEL) as ResolvedReason[]).map(r => (
                              <label key={r} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text)" }}>
                                <input
                                  type="radio"
                                  name={`reason-${row.id}`}
                                  value={r}
                                  checked={reasonMap[row.id] === r}
                                  onChange={() => setReasonMap(m => ({ ...m, [row.id]: r }))}
                                />
                                {REASON_LABEL[r]}
                              </label>
                            ))}
                          </div>
                          <textarea
                            placeholder="Optional note (500 char cap)"
                            value={noteMap[row.id] ?? ""}
                            onChange={e => setNoteMap(m => ({ ...m, [row.id]: e.target.value.slice(0, 500) }))}
                            style={{
                              width: "100%", minHeight: 60, padding: 8, fontSize: 12,
                              background: "var(--bg)", color: "var(--text)",
                              border: "1px solid var(--border)", borderRadius: 4, marginBottom: 8,
                              fontFamily: "inherit",
                            }}
                          />
                          <div style={{ display: "flex", gap: 8 }}>
                            <button
                              onClick={() => applyStatus(row, "resolved")}
                              disabled={busyId === row.id || !reasonMap[row.id]}
                              style={{
                                padding: "6px 14px", fontSize: 12, borderRadius: 4,
                                background: reasonMap[row.id] ? "var(--accent)" : "var(--surface)",
                                color: reasonMap[row.id] ? "var(--accent-fg, white)" : "var(--text-muted)",
                                border: "1px solid var(--border)",
                                cursor: busyId === row.id || !reasonMap[row.id] ? "not-allowed" : "pointer",
                                fontWeight: 500,
                              }}
                            >
                              {busyId === row.id ? "Saving…" : "Mark resolved"}
                            </button>
                            <button
                              onClick={() => applyStatus(row, "triaging")}
                              disabled={busyId === row.id || row.status === "triaging"}
                              style={{
                                padding: "6px 14px", fontSize: 12, borderRadius: 4,
                                background: "var(--surface)", color: "var(--text-muted)",
                                border: "1px solid var(--border)", cursor: "pointer",
                              }}
                            >
                              Move to triaging
                            </button>
                          </div>
                        </div>
                      )}

                      {row.status === "resolved" && (
                        <div style={{
                          padding: 12, background: "var(--surface)", borderRadius: 6,
                          border: "1px solid var(--border)", fontSize: 12, color: "var(--text-muted)",
                        }}>
                          <div style={{ marginBottom: 4 }}>
                            Resolved by <strong>{row.resolved_by ?? "unknown"}</strong>
                            {row.resolved_at && <> · {timeAgo(row.resolved_at)}</>}
                          </div>
                          {row.resolved_reason && (
                            <div style={{ marginBottom: 4 }}>
                              Reason: {REASON_LABEL[row.resolved_reason as ResolvedReason] ?? row.resolved_reason}
                            </div>
                          )}
                          {row.resolved_note && (
                            <div style={{ marginTop: 6, fontStyle: "italic" }}>&ldquo;{row.resolved_note}&rdquo;</div>
                          )}
                          <button
                            onClick={() => applyStatus(row, "open")}
                            disabled={busyId === row.id}
                            style={{
                              marginTop: 8, padding: "4px 10px", fontSize: 11, borderRadius: 4,
                              background: "var(--surface)", color: "var(--text-muted)",
                              border: "1px solid var(--border)", cursor: "pointer",
                            }}
                          >
                            Reopen
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </GuardShell>
    </AppShell>
  )
}
