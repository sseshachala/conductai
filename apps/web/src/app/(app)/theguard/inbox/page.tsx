"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import {
  GuardFilterBar,
  GuardPageHeader,
  type FilterPill,
} from "@/components/guard/common"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { usePolledFetch } from "@/hooks/usePolledFetch"
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
import { AwaitingApprovals, type PendingApproval, type ApprovalListOut } from "./_components/AwaitingApprovals"
import { InboxRowList } from "./_components/InboxRowList"

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

  // 15s polling while the tab is visible (pauses while hidden, refreshes on
  // return). Ticks BOTH inbox findings and pending approvals.
  usePolledFetch(() => {
    void load({ background: true })
    void loadApprovals({ background: true })
  }, 15_000)

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
          <AwaitingApprovals
            approvals={approvals}
            approvalsError={approvalsError}
            decidingId={decidingId}
            rejectingId={rejectingId}
            rejectReason={rejectReason}
            setRejectReason={setRejectReason}
            submitDecision={submitDecision}
            beginReject={beginReject}
            confirmReject={confirmReject}
            cancelReject={cancelReject}
          />
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
          <InboxRowList
            rows={rows}
            expandedId={expandedId}
            events={events}
            toggleExpand={toggleExpand}
            reasonMap={reasonMap}
            setReasonMap={setReasonMap}
            noteMap={noteMap}
            setNoteMap={setNoteMap}
            busyId={busyId}
            applyStatus={applyStatus}
          />
        )}
      </GuardShell>
    </AppShell>
  )
}
