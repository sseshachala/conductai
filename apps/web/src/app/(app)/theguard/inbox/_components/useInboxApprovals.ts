"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api/client"
import type { PendingApproval, ApprovalListOut } from "./AwaitingApprovals"

/**
 * Awaiting-approval fetch + decide for the Inbox. Race protection: always advance
 * the epoch on load (never early-return); late responses drop themselves on return.
 * A workspace change hard-resets state so a stale response can't repopulate it.
 */
export function useInboxApprovals(workspaceId: string | null | undefined) {
  const { authFetch } = useAuthFetch()
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

  useEffect(() => {
    approvalsEpochRef.current += 1
    setApprovals([])
    setApprovalsError(null)
    setRejectingId(null)
    setRejectReason("")
  }, [workspaceId])

  useEffect(() => { void loadApprovals() }, [loadApprovals])

  return {
    approvals, approvalsError, decidingId, rejectingId, rejectReason, setRejectReason,
    loadApprovals, submitDecision, beginReject, confirmReject, cancelReject,
  }
}
