"use client"
import { useEffect, useRef, useState } from "react"
import { API } from "@/lib/api"
import { useLensEvent } from "@/hooks/useLensEvent"
import type { LensSessionStream } from "@/hooks/useLensSessionStream"
import RunDetailPanel, { type RunMeta } from "@/components/runs/RunDetailPanel"

export function ActionConfirmBubble({
  toolName,
  approvalRequestId,
  summary,
  warnings,
  expiresAt,
  authFetch,
  stream,
  onResult,
  onRunStarted,
  onRetry,
}: {
  toolName: string
  approvalRequestId: string
  summary: string
  warnings?: string[]
  expiresAt?: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  stream: LensSessionStream | null
  onResult: (text: string) => void
  onRunStarted?: (runId: string, workflowName: string, initialStatus: string) => void
  // Regression 4 fix — invoked when the user retries a failed run from the
  // decided-approved bubble. Parent spawns a new RunBubble for the new run id.
  onRetry?: (newRunId: string, workflowName: string) => void
}) {
  const [status, setStatus] = useState<"pending" | "loading" | "done">("pending")
  const [idCopied, setIdCopied] = useState(false)
  // Server-side status snapshot fetched on mount so a restored bubble for
  // an already-decided action renders in the resolved state instead of
  // showing active Confirm/Cancel buttons for something that already ran.
  const [serverStatus, setServerStatus] = useState<"pending" | "approved" | "rejected" | "timed_out" | null>(null)
  const [serverResult, setServerResult] = useState<Record<string, unknown> | null>(null)
  // #1511 — expand toggle + fetched workflow_id so we can embed <RunDetailPanel>
  // when the action resolved into a run. localStorage keeps expand state across
  // refresh, keyed by approvalRequestId (per-bubble).
  const [panelOpen, setPanelOpen] = useState(() => {
    try { return typeof window !== "undefined" && window.localStorage.getItem(`lens:actionPanelOpen:${approvalRequestId}`) === "1" }
    catch { return false }
  })
  const [runData, setRunData] = useState<RunMeta | null>(null)
  // Dedupe: whichever source (POST response or SSE event) reports resolution
  // first wins. Race is fine because the payload shape is identical.
  const handledRef = useRef(false)
  // #1480 Gap 4 — action controls for the run this bubble kicked off, shown
  // in the decided-approved state so the user doesn't have to hunt for the
  // sibling RunBubble to cancel or retry.
  const [runBusy, setRunBusy] = useState(false)
  const [runActionErr, setRunActionErr] = useState<string | null>(null)

  // #1511 — mirror panelOpen to localStorage so refresh restores expand state.
  useEffect(() => {
    try { window.localStorage.setItem(`lens:actionPanelOpen:${approvalRequestId}`, panelOpen ? "1" : "0") }
    catch { /* best-effort */ }
  }, [panelOpen, approvalRequestId])

  // #1511 — once we know the run_id (via server snapshot or dispatch), fetch
  // /runs/{id} to grab workflow_id + a full run seed. RunDetailPanel needs
  // workflowId, and passing runData as initialRun skips its own initial fetch.
  const resolvedRunId = (serverResult?.run_id as string | undefined) ?? null
  useEffect(() => {
    if (!resolvedRunId) return
    let cancelled = false
    authFetch(`${API}/runs/${resolvedRunId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (!cancelled && data) setRunData(data as RunMeta) })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedRunId])

  // Regression 3 fix — subscribe to run events for this bubble's run so
  // Cancel/Retry/Approve/Reject buttons reflect current run status instead of
  // the stale snapshot from mount. Refetches runData on any run.* event.
  useLensEvent(stream, "run", resolvedRunId ?? "", (_evt) => {
    if (!resolvedRunId) return
    authFetch(`${API}/runs/${resolvedRunId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) setRunData(data as RunMeta) })
      .catch(() => {})
  })

  // #1511 — auto-open the panel when a decided-approved bubble with a run
  // becomes visible, so the demo flow drops straight into the run detail.
  useEffect(() => {
    if (serverStatus === "approved" && resolvedRunId) setPanelOpen(true)
  }, [serverStatus, resolvedRunId])

  // On mount, fetch the current status from the server. Skip when a
  // decision has already been dispatched in this render (handledRef set).
  useEffect(() => {
    let cancelled = false
    authFetch(`${API}/glens/actions/${approvalRequestId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data?.status) return
        setServerStatus(data.status as typeof serverStatus)
        if (data.result) setServerResult(data.result as Record<string, unknown>)
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approvalRequestId])

  const finishText = (text: string) => {
    if (handledRef.current) return
    handledRef.current = true
    setStatus("done")
    onResult(text)
  }

  const finishRun = (runId: string, workflowName: string, initialStatus: string) => {
    if (handledRef.current) return
    handledRef.current = true
    setStatus("done")
    if (onRunStarted) {
      onRunStarted(runId, workflowName, initialStatus)
    } else {
      // Flag OFF or no run-bubble callback wired — fall back to text link.
      onResult(`Run started for **${workflowName}**. [View run →](/runs/${runId})`)
    }
  }

  const dispatchConfirmed = (payload: Record<string, unknown> | undefined, fallbackTool: string) => {
    const result = (payload?.result ?? {}) as Record<string, unknown>
    const label = (payload?.tool_name as string | undefined) ?? fallbackTool
    const runId = result.run_id as string | undefined
    if (runId) {
      const wfName = (result.workflow_name as string | undefined) ?? label
      // Initial status from the run row when we have it; "pending" otherwise
      // (the worker will emit run.status_changed within seconds).
      const initialStatus = (result.status as string | undefined) ?? "pending"
      finishRun(runId, wfName, initialStatus)
    } else {
      finishText(`${label} executed successfully.`)
    }
  }

  // #1480 PR 4 — react to action.confirmed / action.cancelled events on the
  // session stream. Fires for cross-tab confirms, Slack-side approvals, or
  // any decide path that touches this row. `stream` is null when the SSE
  // feature flag is off — subscription is a silent no-op then.
  useLensEvent(stream, "approval", approvalRequestId, (evt) => {
    if (evt.type === "action.confirmed") {
      dispatchConfirmed(evt.payload, toolName)
    } else if (evt.type === "action.cancelled") {
      finishText("Action cancelled.")
    }
  })

  async function post(action: "confirm" | "cancel") {
    setStatus("loading")
    try {
      const res = await authFetch(`${API}/glens/actions/${approvalRequestId}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        finishText(`Failed to ${action}: ${err.detail ?? res.status}`)
        return
      }
      // When the SSE stream is live, it will call `finish*` with the
      // event-derived message; the POST body is redundant then. When SSE
      // is off (flag disabled) or subscribed too late, fall through and
      // use the response body directly. `handledRef` deduplicates either way.
      const data = await res.json()
      if (action === "confirm") {
        dispatchConfirmed(data as Record<string, unknown>, toolName)
      } else {
        finishText("Action cancelled.")
      }
    } catch {
      finishText("Network error. Please try again.")
    }
  }

  const isMutation = toolName !== "decide_approval"  // heuristic — decide is itself an approve/reject

  async function _postRunAction(url: string, body?: unknown, onOk?: (data: Record<string, unknown>) => void, onError?: () => void) {
    if (runBusy || !runData?.workflow_id || !resolvedRunId) return
    setRunBusy(true); setRunActionErr(null)
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setRunActionErr((err as { detail?: string }).detail ?? `Request failed (${res.status})`)
        onError?.()
        return
      }
      const data = await res.json().catch(() => ({}))
      onOk?.(data as Record<string, unknown>)
    } catch {
      setRunActionErr("Network error")
      onError?.()
    } finally {
      setRunBusy(false)
    }
  }

  const runStatus = runData?.status ?? null
  const runCancel = () => _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs/${resolvedRunId}/cancel`)
  // Optimistic — flip status locally so approve/reject buttons vanish and the
  // panel updates instantly. If the POST fails _postRunAction surfaces the
  // error via runActionErr and we revert; SSE otherwise confirms the transition.
  const runDecide = (decision: "approved" | "rejected") => {
    if (!runData || !resolvedRunId) return
    const prevStatus = runData.status
    setRunData(prev => prev ? { ...prev, status: decision === "approved" ? "running" : "cancelled" } : prev)
    _postRunAction(
      `${API}/workflows/${runData.workflow_id}/runs/${resolvedRunId}/approve`,
      { decision },
      undefined,
      () => setRunData(prev => prev ? { ...prev, status: prevStatus } : prev),
    )
  }
  const runRetry = () => {
    // #1480 Gap 3 parity — reuse original inputs, strip block outputs + system keys.
    const runStateRec = (runData?.state ?? {}) as Record<string, unknown>
    const initial_state: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(runStateRec)) {
      if (k.startsWith("__")) continue
      // Same heuristic as RunBubble's retry: keep single-underscore meta keys
      // (_trigger) and scalars; drop object-typed non-underscore keys (likely
      // block outputs). Server-side validate_run_start_inputs is the backstop.
      if (typeof v === "object" && v !== null && !k.startsWith("_")) continue
      initial_state[k] = v
    }
    _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs`, { initial_state }, (data) => {
      // Regression 4 fix — spawn a new RunBubble instead of leaving the new
      // run orphaned. Without this the Retry button stays visible and the
      // user might spam-click it, spawning a run per click.
      const newId = data.id as string | undefined
      if (newId && onRetry) onRetry(newId, (runData?.workflow_id as string | undefined) ?? "workflow")
    })
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Action · {toolName}</div>
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 10, lineHeight: 1.5 }}>{summary}</div>

        {/* Approval request identifier (#1468) — visible so the user knows which pending
             action a natural-language "yes" is confirming when multiple are outstanding. */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, fontSize: 11, color: "var(--text-muted)" }}>
          <span style={{ textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>ID</span>
          <code style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", color: "var(--text-2)", fontSize: 11 }}>
            {approvalRequestId.slice(0, 8)}…{approvalRequestId.slice(-4)}
          </code>
          <button
            type="button"
            title={idCopied ? "Copied" : "Copy full ID"}
            onClick={() => {
              navigator.clipboard.writeText(approvalRequestId).then(
                () => { setIdCopied(true); setTimeout(() => setIdCopied(false), 1200) },
                () => {},
              )
            }}
            style={{
              padding: "2px 6px", borderRadius: 4, border: "none",
              background: idCopied ? "var(--accent-weak, rgba(59,130,246,0.12))" : "transparent",
              color: idCopied ? "var(--accent-text, #2563eb)" : "var(--text-muted)",
              cursor: "pointer", fontSize: 11, lineHeight: 1,
            }}
          >
            {idCopied ? "✓" : "⧉"}
          </button>
        </div>

        {warnings && warnings.length > 0 && (
          <div style={{ fontSize: 12, color: "var(--warn, #f59e0b)", marginBottom: 12, padding: "8px 12px", background: "var(--warn-bg, #fef3c7)", borderRadius: 6 }}>
            {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
          </div>
        )}

        {(serverStatus === "approved" || serverStatus === "rejected" || serverStatus === "timed_out") && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
            <span style={{
              fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 999,
              background:
                serverStatus === "approved" ? "var(--ok-bg, #dcfce7)" :
                serverStatus === "rejected" ? "var(--err-bg, #fee2e2)" :
                "var(--surface-3, #f3f4f6)",
              color:
                serverStatus === "approved" ? "var(--ok-text, #166534)" :
                serverStatus === "rejected" ? "var(--err-text, #991b1b)" :
                "var(--text-muted)",
              textTransform: "capitalize",
            }}>{serverStatus === "timed_out" ? "Expired" : serverStatus}</span>
            {serverStatus === "approved" && (serverResult?.run_id as string | undefined) && (
              <a href={`/runs/${serverResult!.run_id}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                View run →
              </a>
            )}
            {/* #1450 PR 5 follow-up: surface the report URL after propose_report confirm. */}
            {serverStatus === "approved" && (serverResult?.url as string | undefined) && (
              <a href={String(serverResult!.url)} style={{ color: "var(--accent)", textDecoration: "none" }}>
                View report →
              </a>
            )}
          </div>
        )}
        {serverStatus === "approved" && runData?.workflow_id && resolvedRunId &&
         (runStatus === "pending" || runStatus === "running" || runStatus === "paused" || runStatus === "failed") && (
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            {(runStatus === "pending" || runStatus === "running") && (
              <button onClick={runCancel} disabled={runBusy}
                style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                         background: "transparent", color: "var(--text-2)",
                         fontSize: 12, cursor: runBusy ? "wait" : "pointer" }}>
                Cancel run
              </button>
            )}
            {runStatus === "paused" && (
              <>
                <button onClick={() => runDecide("approved")} disabled={runBusy}
                  style={{ padding: "6px 14px", borderRadius: 6, border: "none",
                           background: "var(--accent)", color: "#fff",
                           fontSize: 12, fontWeight: 600, cursor: runBusy ? "wait" : "pointer" }}>
                  Approve run
                </button>
                <button onClick={() => runDecide("rejected")} disabled={runBusy}
                  style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                           background: "transparent", color: "var(--text-2)",
                           fontSize: 12, cursor: runBusy ? "wait" : "pointer" }}>
                  Reject run
                </button>
              </>
            )}
            {runStatus === "failed" && (
              <button onClick={runRetry} disabled={runBusy}
                style={{ padding: "6px 14px", borderRadius: 6, border: "none",
                         background: "var(--accent)", color: "#fff",
                         fontSize: 12, fontWeight: 600, cursor: runBusy ? "wait" : "pointer" }}>
                Retry run
              </button>
            )}
          </div>
        )}
        {runActionErr && (
          <div style={{ fontSize: 12, color: "var(--err-text, #991b1b)", background: "var(--err-bg, #fee2e2)",
                        padding: "6px 10px", borderRadius: 6, marginTop: 8 }}>
            {runActionErr}
          </div>
        )}
        {panelOpen && serverStatus === "approved" && runData?.workflow_id && resolvedRunId && (
          <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
            <RunDetailPanel
              workflowId={runData.workflow_id as string}
              runId={resolvedRunId}
              embedded
              initialRun={runData}
            />
          </div>
        )}
        {status === "pending" && (serverStatus === null || serverStatus === "pending") && (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button
              onClick={() => post("confirm")}
              style={{
                padding: "8px 20px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer",
                background: "var(--accent)", color: "#fff",
              }}
            >
              Confirm
            </button>
            <button
              onClick={() => post("cancel")}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer" }}
            >
              Cancel
            </button>
            {expiresAt && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Expires {new Date(expiresAt).toLocaleTimeString()}
              </span>
            )}
          </div>
        )}
        {status === "loading" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Working…</div>}
      </div>
    </div>
  )
}
