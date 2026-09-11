"use client"
import { API } from "@/lib/api"

import { useEffect, useRef, useState } from "react"
import { useRouter, usePathname, useSearchParams } from "next/navigation"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useLensEvent } from "@/hooks/useLensEvent"
import { useLensSessionStream, type LensSessionStream } from "@/hooks/useLensSessionStream"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"
import { GlensPageBubble } from "@/components/glens/GlensPageBubble"
import { GenericTableBubble } from "@/components/glens/GenericTableBubble"
import { BlocksBubble } from "@/components/glens/BlocksBubble"
import RunDetailPanel, { type RunMeta } from "@/components/runs/RunDetailPanel"
import type { GLensSession, PolicyMapping, MessageBody, Message, RunBlockState } from "@/components/glens/glensTypes"
import { withId, replaceLast, replaceById } from "@/components/glens/glensTypes"
import { DEFAULT_SUGGESTIONS, PAGE_SUGGESTIONS, SKILL_LABELS, SKILL_APPLY_URL, _applyBody } from "@/components/glens/glensConstants"
import { Sidebar } from "@/components/glens/Sidebar"
import { ChatInput } from "@/components/glens/ChatInput"
import { LiveElapsed } from "@/components/glens/LiveElapsed"
import { CopyButton } from "@/components/glens/CopyButton"
import { MessageFooter } from "@/components/glens/MessageFooter"
import { UserBubble } from "@/components/glens/bubbles/UserBubble"
import { AnswerBubble } from "@/components/glens/bubbles/AnswerBubble"
import { LoadingBubble } from "@/components/glens/bubbles/LoadingBubble"
import { DashboardBubble } from "@/components/glens/bubbles/DashboardBubble"


// ─── Message bubbles ──────────────────────────────────────────────────────────

function PolicyConfirmBubble({
  answer,
  action,
  skill,
  draft,
  mapping,
  targetRuleId,
  sessionId,
  authFetch,
  onResult,
  warning,
}: {
  answer: string
  action: string
  skill: string
  draft: Record<string, unknown>
  mapping: PolicyMapping[]
  targetRuleId?: string
  sessionId: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onResult: (text: string) => void
  warning?: string
}) {
  const [status, setStatus] = useState<"pending" | "loading" | "done">("pending")

  async function confirm() {
    setStatus("loading")
    const url = `${API}${SKILL_APPLY_URL[skill] ?? "/glens/policy/apply"}`
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_applyBody(skill, action, draft, targetRuleId)),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        onResult(`Failed to apply: ${err.detail ?? res.status}`)
      } else {
        const data = await res.json()
        const label = data.rule_id ? `Rule "${data.rule_id}"` : data.scope ? `Budget (${data.scope})` : "Guard config"
        onResult(`${label} ${data.action} successfully.`)
      }
    } catch {
      onResult("Network error. Please try again.")
    }
    setStatus("done")
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Policy</div>
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 16, lineHeight: 1.5 }}>{answer}</div>

        {/* Field → Column mapping table */}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 16 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Field</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Value</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Column</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Description</th>
            </tr>
          </thead>
          <tbody>
            {mapping.map(m => (
              <tr key={m.field} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--accent-text)" }}>{m.field}</td>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text)" }}>{String(draft[m.field] ?? "—")}</td>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text-2)", fontSize: 11 }}>{m.column}</td>
                <td style={{ padding: "6px 8px", color: "var(--text-muted)" }}>{m.description}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {warning && (
          <div style={{ fontSize: 12, color: "var(--warn, #f59e0b)", marginBottom: 12, padding: "8px 12px", background: "var(--warn-bg, #fef3c7)", borderRadius: 6 }}>
            {warning}
          </div>
        )}

        {status === "pending" && (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button
              onClick={confirm}
              style={{
                padding: "8px 20px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer",
                background: action === "delete" ? "var(--err, #ef4444)" : "var(--accent)",
                color: "#fff",
              }}
            >
              {action === "delete" ? "Delete" : "Confirm"}
            </button>
            <button
              onClick={() => onResult(`Policy ${action} cancelled.`)}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer" }}
            >
              Cancel
            </button>
            {action === "delete" && (
              <span style={{ fontSize: 11, color: "var(--err, #ef4444)" }}>This cannot be undone.</span>
            )}
          </div>
        )}
        {status === "loading" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Applying…</div>}
      </div>
    </div>
  )
}

function ActionConfirmBubble({
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

  async function _postRunAction(url: string, body?: unknown, onOk?: (data: Record<string, unknown>) => void) {
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
        return
      }
      const data = await res.json().catch(() => ({}))
      onOk?.(data as Record<string, unknown>)
    } catch {
      setRunActionErr("Network error")
    } finally {
      setRunBusy(false)
    }
  }

  const runStatus = runData?.status ?? null
  const runCancel = () => _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs/${resolvedRunId}/cancel`)
  const runDecide = (decision: "approved" | "rejected") =>
    _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs/${resolvedRunId}/approve`, { decision })
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

// ─── Run bubble ──────────────────────────────────────────────────────────────

// #1480 PR 5 — live run status inline in chat. Subscribes to run.status_changed
// events on the session stream and updates its pill in place. Always renders
// the "View run →" link so the user can jump to the run detail page.

function RunBubble({
  runId,
  workflowName,
  initialStatus,
  stream,
  authFetch,
  onRetry,
}: {
  runId: string
  workflowName: string
  initialStatus: string
  stream: LensSessionStream | null
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onRetry?: (newRunId: string, workflowName: string) => void
}) {
  const [status, setStatus] = useState(initialStatus)
  const [error, setError] = useState<string | null>(null)
  // Per-block timeline (#1480 PR 7). Order is insertion order (Map preserves
  // it), which matches the DAG execution order the worker publishes in.
  const [blocks, setBlocks] = useState<Map<string, RunBlockState>>(new Map())
  // Cached run.state from /runs/{id} — populated on mount, used to render
  // block outputs inline (#1480 PR 9). Refetch on demand if a block the
  // user expands isn't in the cache yet.
  const [runState, setRunState] = useState<Record<string, unknown> | null>(null)
  const [outcome, setOutcome] = useState<{ type?: string; artifact_url?: string } | null>(null)
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionErr, setActionErr] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [completedAt, setCompletedAt] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // #1506 — top-level expand toggle for the embedded RunDetailPanel
  const [panelOpen, setPanelOpen] = useState(() => {
    // #1508 follow-up — persist expand state across refresh, per runId.
    // localStorage (not sessionStorage) so re-opening the tab keeps context.
    try { return typeof window !== "undefined" && window.localStorage.getItem(`lens:panelOpen:${runId}`) === "1" }
    catch { return false }
  })
  // #1508 follow-up — cache the /runs/{id} response so the embedded
  // RunDetailPanel can skip its own initial fetch (initialRun prop).
  const [runData, setRunData] = useState<RunMeta | null>(null)
  // If an SSE update lands before the bootstrap fetch resolves, the fetch
  // result is stale — don't overwrite the fresher event.
  const gotUpdate = useRef(false)

  // Mount-race fix: the worker publishes run.status_changed as soon as it
  // picks up the run — often BEFORE this component mounts and subscribes.
  // On short runs both "running" and terminal events can fire before the
  // subscription attaches, leaving the pill stuck at "pending" forever.
  // Fetch current status once on mount so the pill catches up regardless
  // of when SSE events landed.
  useEffect(() => {
    let cancelled = false
    authFetch(`${API}/runs/${runId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled) return
        if (data) setRunData(data as RunMeta)
        if (data?.state) {
          const st = data.state as Record<string, unknown>
          setRunState(st)
          // #1480 PR 12 — seed the block timeline from persisted run.state
          // so a restored RunBubble shows completed blocks immediately
          // instead of waiting for new SSE events (which never come for
          // an already-completed run).
          if (gotUpdate.current === false) {
            const seeded = new Map<string, RunBlockState>()
            for (const [key, val] of Object.entries(st)) {
              // Regression 2 fix: skip system keys (__foo) AND meta keys
              // (_trigger, _workspace, etc.). Single-underscore prefix means
              // "run metadata, not a block output" by convention. Without
              // this, _trigger got treated as a block on restore and the
              // retry filter (#1547) then dropped it, losing webhook context.
              if (key.startsWith("_")) continue
              const failed = val && typeof val === "object" && "error" in (val as Record<string, unknown>)
              seeded.set(key, {
                id: key,
                status: failed ? "failed" : "succeeded",
                error: failed ? String((val as Record<string, unknown>).error) : undefined,
              })
            }
            if (seeded.size > 0) setBlocks(prev => prev.size === 0 ? seeded : prev)
          }
        }
        if (data?.workflow_id) setWorkflowId(data.workflow_id as string)
        if (data?.outcome) setOutcome(data.outcome as { type?: string; artifact_url?: string })
        if (data?.started_at) setStartedAt(new Date(data.started_at as string).getTime())
        if (data?.completed_at) setCompletedAt(new Date(data.completed_at as string).getTime())
        if (data?.status && !gotUpdate.current) setStatus(data.status)
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // Refetch state + outcome + timing when a block completes / status changes.
  // #1480 Gap 1 — deps include terminalCount so we refetch on EVERY block
  // completion, not just the first. That refreshes tokens/cost mid-run so the
  // embedded RunDetailPanel StatRow updates live (kills #1543 stopgap).
  const terminalCount = Array.from(blocks.values()).filter(b => b.status === "succeeded" || b.status === "failed").length
  useEffect(() => {
    if (terminalCount === 0 && status !== "succeeded" && status !== "failed") return
    let cancelled = false
    authFetch(`${API}/runs/${runId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data) return
        setRunData(data as RunMeta)
        if (data.state) setRunState(data.state as Record<string, unknown>)
        if (data.outcome) setOutcome(data.outcome as { type?: string; artifact_url?: string })
        if (data.completed_at) setCompletedAt(new Date(data.completed_at as string).getTime())
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, terminalCount])

  // Elapsed clock lives inside <LiveElapsed/> below — it owns its own 1s
  // tick so only that span re-renders each second, not the whole RunBubble
  // (which includes the embedded RunDetailPanel and would flicker at 1Hz).

  // #1506 — auto-open the full detail panel when the run pauses for approval,
  // so the Approvals tab is one click away without hunting for a chevron.
  useEffect(() => {
    if (status === "paused") setPanelOpen(true)
  }, [status])

  // #1508 follow-up — mirror panelOpen to localStorage so refresh restores it.
  useEffect(() => {
    try { window.localStorage.setItem(`lens:panelOpen:${runId}`, panelOpen ? "1" : "0") }
    catch { /* private-mode / quota — best-effort */ }
  }, [panelOpen, runId])

  useLensEvent(stream, "run", runId, (evt) => {
    gotUpdate.current = true
    if (evt.type === "run.status_changed") {
      const nextStatus = (evt.payload?.status as string | undefined) ?? status
      setStatus(nextStatus)
      const evtErr = evt.payload?.error as string | undefined
      if (evtErr) setError(evtErr)
      return
    }
    // Block-level events (#1480 PR 7 timeline)
    const blockId = evt.payload?.block_id as string | undefined
    if (!blockId) return
    const label = evt.payload?.label as string | undefined
    const errMsg = evt.payload?.error as string | undefined
    setBlocks(prev => {
      const next = new Map(prev)
      const cur = next.get(blockId) ?? { id: blockId, status: "pending" }
      if (evt.type === "run.block_started") {
        next.set(blockId, { ...cur, status: "running", label: label ?? cur.label })
      } else if (evt.type === "run.block_completed") {
        next.set(blockId, { ...cur, status: "succeeded" })
      } else if (evt.type === "run.block_failed") {
        next.set(blockId, { ...cur, status: "failed", error: errMsg ?? cur.error })
      }
      return next
    })
  })

  async function _postAction(url: string, body?: unknown, onOk?: (data: Record<string, unknown>) => void) {
    if (busy || !workflowId) return
    setBusy(true); setActionErr(null)
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setActionErr((err as { detail?: string }).detail ?? `Request failed (${res.status})`)
        setBusy(false)
        return
      }
      const data = await res.json().catch(() => ({}))
      onOk?.(data as Record<string, unknown>)
    } catch {
      setActionErr("Network error")
    } finally {
      setBusy(false)
    }
  }

  const cancelRun = () => _postAction(`${API}/workflows/${workflowId}/runs/${runId}/cancel`)
  const decideRun = (decision: "approved" | "rejected") =>
    _postAction(`${API}/workflows/${workflowId}/runs/${runId}/approve`, { decision })
  const retryRun = () => {
    // #1480 Gap 3 — reuse the original run's inputs. runState + blocks give
    // us enough to reconstruct: strip out per-block outputs (keys equal to
    // block IDs) and system-added keys (__foo). What remains is _trigger +
    // any top-level input fields the workflow was originally started with.
    const initial_state: Record<string, unknown> = {}
    if (runState) {
      for (const [k, v] of Object.entries(runState)) {
        if (k.startsWith("__")) continue        // system-added
        if (blocks.has(k)) continue             // block output
        initial_state[k] = v
      }
    }
    _postAction(`${API}/workflows/${workflowId}/runs`, { initial_state }, (data) => {
      const newId = data.id as string | undefined
      if (newId && onRetry) onRetry(newId, workflowName)
    })
  }

  const pillColor = (() => {
    switch (status) {
      case "succeeded": return { bg: "var(--ok-bg, #dcfce7)", fg: "var(--ok-text, #166534)" }
      case "failed":    return { bg: "var(--err-bg, #fee2e2)", fg: "var(--err-text, #991b1b)" }
      case "running":   return { bg: "var(--accent-weak, rgba(59,130,246,0.12))", fg: "var(--accent-text, #2563eb)" }
      case "paused":    return { bg: "var(--warn-bg, #fef3c7)", fg: "var(--warn, #f59e0b)" }
      case "cancelled": return { bg: "var(--surface-3, #f3f4f6)", fg: "var(--text-muted)" }
      default:          return { bg: "var(--surface-3, #f3f4f6)", fg: "var(--text-muted)" }
    }
  })()

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Run · {workflowName}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <span style={{
            fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 999,
            background: pillColor.bg, color: pillColor.fg, textTransform: "capitalize",
          }}>{status}</span>
          {startedAt && (
            <LiveElapsed startedAt={startedAt} completedAt={completedAt} status={status} />
          )}
          <button
            onClick={() => setPanelOpen(o => !o)}
            aria-label={panelOpen ? "Collapse run detail" : "Expand run detail"}
            aria-expanded={panelOpen}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              borderRadius: 6, padding: "2px 8px", fontSize: 11,
              color: "var(--text-2)", cursor: "pointer", lineHeight: 1.4,
            }}
          >
            {panelOpen ? "▾ Collapse" : "▸ Expand"}
          </button>
          <a href={`/runs/${runId}`} style={{ fontSize: 13, color: "var(--accent)", textDecoration: "none" }}>
            View run →
          </a>
        </div>
        {outcome?.artifact_url && (
          <div style={{ marginBottom: 10, padding: "8px 12px", background: "var(--ok-bg, #dcfce7)", borderRadius: 6, fontSize: 12 }}>
            <span style={{ color: "var(--ok-text, #166534)", fontWeight: 600 }}>
              {outcome.type ? outcome.type.replace(/_/g, " ") : "artifact"}:
            </span>{" "}
            <a href={outcome.artifact_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", textDecoration: "none", wordBreak: "break-all" }}>
              {outcome.artifact_url}
            </a>
          </div>
        )}
        {error && (
          <div style={{ fontSize: 12, color: "var(--err-text, #991b1b)", background: "var(--err-bg, #fee2e2)", padding: "8px 12px", borderRadius: 6 }}>
            {error}
          </div>
        )}
        {actionErr && (
          <div style={{ fontSize: 12, color: "var(--err-text, #991b1b)", background: "var(--err-bg, #fee2e2)", padding: "6px 10px", borderRadius: 6, marginBottom: 8 }}>
            {actionErr}
          </div>
        )}
        {!panelOpen && workflowId && (status === "pending" || status === "running" || status === "paused" || status === "failed") && (
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            {(status === "pending" || status === "running") && (
              <button
                onClick={cancelRun}
                disabled={busy}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                  background: "transparent", color: "var(--text-2)",
                  fontSize: 12, cursor: busy ? "wait" : "pointer",
                }}
              >
                Cancel
              </button>
            )}
            {status === "paused" && (
              <>
                <button
                  onClick={() => decideRun("approved")}
                  disabled={busy}
                  style={{
                    padding: "6px 14px", borderRadius: 6, border: "none",
                    background: "var(--accent)", color: "#fff",
                    fontSize: 12, fontWeight: 600, cursor: busy ? "wait" : "pointer",
                  }}
                >
                  Approve
                </button>
                <button
                  onClick={() => decideRun("rejected")}
                  disabled={busy}
                  style={{
                    padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                    background: "transparent", color: "var(--text-2)",
                    fontSize: 12, cursor: busy ? "wait" : "pointer",
                  }}
                >
                  Reject
                </button>
              </>
            )}
            {status === "failed" && onRetry && (
              <button
                onClick={retryRun}
                disabled={busy}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "none",
                  background: "var(--accent)", color: "#fff",
                  fontSize: 12, fontWeight: 600, cursor: busy ? "wait" : "pointer",
                }}
              >
                Retry
              </button>
            )}
          </div>
        )}
        {blocks.size > 0 && (
          <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
            {Array.from(blocks.values()).map(b => {
              const isExpanded = expanded.has(b.id)
              const blockOutput = runState?.[b.id]
              const hasOutput = blockOutput !== undefined && b.status !== "pending" && b.status !== "running"
              return (
                <div key={b.id} style={{ padding: "4px 0" }}>
                  <div
                    onClick={hasOutput ? () => setExpanded(prev => {
                      const next = new Set(prev)
                      if (next.has(b.id)) next.delete(b.id); else next.add(b.id)
                      return next
                    }) : undefined}
                    style={{
                      display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12,
                      color: "var(--text-2)", cursor: hasOutput ? "pointer" : "default",
                    }}
                  >
                    <span style={{
                      display: "inline-block", width: 14, textAlign: "center",
                      color: b.status === "succeeded" ? "var(--ok-text, #166534)"
                           : b.status === "failed"    ? "var(--err-text, #991b1b)"
                           : b.status === "running"   ? "var(--accent-text, #2563eb)"
                           : "var(--text-muted)",
                    }}>{b.status === "succeeded" ? "✓" : b.status === "failed" ? "✗" : b.status === "running" ? "●" : "○"}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500, color: "var(--text)" }}>
                        {b.label ?? b.id}
                        {hasOutput && (
                          <span style={{ marginLeft: 8, fontSize: 10, color: "var(--text-muted)" }}>
                            {isExpanded ? "▾" : "▸"}
                          </span>
                        )}
                      </div>
                      {b.error && (
                        <div style={{ fontSize: 11, color: "var(--err-text, #991b1b)", marginTop: 2 }}>
                          {b.error}
                        </div>
                      )}
                    </div>
                  </div>
                  {isExpanded && hasOutput && (
                    <pre style={{
                      margin: "6px 0 6px 22px", padding: "8px 10px",
                      background: "var(--surface-3, rgba(0,0,0,0.03))",
                      border: "1px solid var(--border)", borderRadius: 6,
                      fontSize: 11, overflow: "auto", maxHeight: 240,
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      color: "var(--text-2)",
                    }}>
                      {JSON.stringify(blockOutput, null, 2)}
                    </pre>
                  )}
                </div>
              )
            })}
          </div>
        )}
        {panelOpen && workflowId && (
          <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
            <RunDetailPanel workflowId={workflowId} runId={runId} embedded initialRun={runData ?? undefined} />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function GLensChatPage({ initialSessionId }: { initialSessionId?: string } = {}) {
  const { authFetch, workspaceId } = useAuthFetch()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const askedFromUrlRef = useRef<string | null>(null)

  // Auto-send when arriving with ?q=… from the global "Ask Lens" bar (#1333 #5).
  // Ref-guard so React Strict-mode double-mount doesn't fire twice, and clean
  // the query out of the URL after the send so refresh doesn't re-trigger.
  useEffect(() => {
    const q = searchParams?.get("q")
    if (!q) return
    if (askedFromUrlRef.current === q) return
    askedFromUrlRef.current = q
    void sendMessage(q)
    router.replace("/lens")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const [sessions, setSessions] = useState<GLensSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  // #1480 PR 4 — SSE session stream. Returns null when the feature flag
  // (NEXT_PUBLIC_LENS_SSE_SURFACE) is off or no active session yet; bubbles
  // that opt in via useLensEvent silently degrade to the existing REST flow.
  const lensStream = useLensSessionStream(activeId)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS)
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem("glens.sidebar.collapsed") === "1"
  })

  useEffect(() => {
    if (typeof window === "undefined") return
    window.localStorage.setItem("glens.sidebar.collapsed", sidebarCollapsed ? "1" : "0")
  }, [sidebarCollapsed])

  const threadRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load session list
  useEffect(() => {
    if (!workspaceId) return
    authFetch(`${API}/glens/sessions`)
      .then(r => r.ok ? r.json() : [])
      .then(setSessions)
      .catch(() => {})
  }, [workspaceId, authFetch])

  // Deep-link entry: if the page mounted with an initialSessionId (URL
  // /lens/{id}), load it once. selectSession updates the URL via
  // router.replace, which is a no-op when we already match — so no loop.
  const initialLoadedRef = useRef(false)
  useEffect(() => {
    if (initialSessionId && !initialLoadedRef.current && workspaceId) {
      initialLoadedRef.current = true
      selectSession(initialSessionId)
    }
    // selectSession is stable within the component closure; omitting from deps
    // avoids re-firing when Redis-driven state updates cascade.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId, workspaceId])

  // Load data-grounded opener chips — page-specific chips (#C2) win over
  // /glens/opener; opener wins over DEFAULT_SUGGESTIONS.
  useEffect(() => {
    const pageMatch = pathname ? PAGE_SUGGESTIONS.find(p => p.match.test(pathname)) : null
    if (pageMatch) {
      setSuggestions(pageMatch.chips)
      return
    }
    if (!workspaceId) return
    authFetch(`${API}/glens/opener`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.chips?.length) setSuggestions(d.chips) })
      .catch(() => {})
  }, [workspaceId, authFetch, pathname])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages])

  function startNew() {
    setActiveId(null)
    setMessages([])
    router.replace("/lens")
  }

  async function selectSession(id: string) {
    router.replace(`/lens/${id}`)
    setLoading(true)
    setActiveId(id)
    setMessages([])
    try {
      const res = await authFetch(`${API}/glens/sessions/${id}`)
      if (!res.ok) return
      const data = await res.json()
      const thread: MessageBody[] = []
      for (const m of (data.messages ?? [])) {
        if (m.role === "user") {
          thread.push({ role: "user", text: m.content })
        } else {
          try {
            const p = JSON.parse(m.content)
            const rendered = m.rendered ?? {}
            if (p.ready && p.spec) {
              thread.push({ role: "assistant", kind: "dashboard", spec: p.spec, sessionId: id })
            } else if (rendered.rows?.length) {
              thread.push({ role: "assistant", kind: "table", rows: rendered.rows, answer: p.answer ?? "", skill: p.skill ?? "governance", columns: p.columns })
            } else if (rendered.blocks?.length) {
              thread.push({ role: "assistant", kind: "blocks", blocks: rendered.blocks, answer: p.answer ?? "", skill: p.skill ?? "governance" })
            } else if (p.confirm_envelope?.approval_request_id) {
              // #1480 PR 12 — rehydrate ActionConfirmBubble from persisted envelope
              const ce = p.confirm_envelope
              thread.push({
                role: "assistant", kind: "action_confirm",
                toolName: ce.tool_name,
                approvalRequestId: ce.approval_request_id,
                summary: ce.summary ?? "Confirm this action?",
                warnings: ce.warnings ?? [],
                expiresAt: ce.expires_at,
              })
            } else if (p.run_started?.run_id) {
              // #1480 PR 12 — rehydrate RunBubble from persisted envelope
              const rs = p.run_started
              thread.push({
                role: "assistant", kind: "run",
                runId: rs.run_id,
                workflowName: rs.workflow_name ?? "workflow",
                initialStatus: rs.status ?? "pending",
              })
            } else {
              const text = p.answer || p.question
              if (text) thread.push({ role: "assistant", kind: "answer", text, skill: p.skill })
            }
          } catch {
            thread.push({ role: "assistant", kind: "answer", text: m.content })
          }
        }
      }
      try {
        if (data.spec && !thread.find(m => m.role === "assistant" && (m as {kind:string}).kind === "dashboard")) {
          thread.push({ role: "assistant", kind: "dashboard", spec: data.spec, sessionId: id })
        }
      } catch { /* malformed spec — skip dashboard bubble */ }
      setMessages(thread.map(withId))
    } finally {
      setLoading(false)
    }
  }

  async function deleteSession(id: string) {
    await authFetch(`${API}/glens/sessions/${id}`, { method: "DELETE" }).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== id))
    if (activeId === id) startNew()
  }

  async function renameSession(id: string, title: string) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, title } : s))
    await authFetch(`${API}/glens/sessions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).catch(() => {})
  }

  function _applyData(data: Record<string, unknown>, text: string) {
    if (!activeId && data.session_id) {
      setActiveId(data.session_id as string)
      setSessions(prev => [{ id: data.session_id as string, title: text.slice(0, 60), has_dashboard: !!data.spec, created_at: new Date().toISOString() }, ...prev])
    }
    if (data.clarification_required) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "answer",
        text: (data.answer as string) ?? "I need more detail to proceed.",
        skill: (data.skill as string) ?? "rules",
        followups: data.followups as string[] | undefined,
      }))
    } else if (data.run_started) {
      // Natural-language confirm path (#1480 PR 11): user typed "yes" and
      // the LLM called confirm_pending_action which returned a run_id.
      // Render <RunBubble> — same live surface the button-click path gets.
      const rs = data.run_started as { run_id: string; workflow_name: string; status: string }
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "run",
        runId: rs.run_id,
        workflowName: rs.workflow_name,
        initialStatus: rs.status ?? "pending",
      }))
    } else if (data.confirm_required && data.approval_request_id) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "action_confirm",
        toolName: data.tool_name as string,
        approvalRequestId: data.approval_request_id as string,
        summary: (data.summary as string) ?? "Confirm this action?",
        warnings: (data.warnings as string[] | undefined) ?? [],
        expiresAt: data.expires_at as string | undefined,
      }))
    } else if (data.confirm_required) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "policy_confirm",
        answer: (data.answer as string) ?? "Review the draft below:",
        action: data.action as string,
        draft: (data.draft as Record<string, unknown>) ?? {},
        mapping: (data.mapping as PolicyMapping[]) ?? [],
        targetRuleId: data.target_rule_id as string | undefined,
        sessionId: data.session_id as string,
        skill: (data.skill as string) ?? "rules",
        warning: data.warning as string | undefined,
      }))
    } else if (data.page_kind && data.page_data) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "page",
        answer: (data.answer as string) ?? "",
        pageKind: data.page_kind as string,
        pageData: data.page_data as Record<string, unknown>,
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
      }))
    } else if (data.blocks) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "blocks",
        answer: (data.answer as string) ?? "",
        blocks: data.blocks as unknown[],
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        understoodAs: data.query_understood_as as string | undefined,
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
      }))
    } else if (data.rows) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "table",
        answer: (data.answer as string) ?? "",
        columns: data.columns as unknown[] | undefined,
        rows: data.rows as unknown[],
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
        understoodAs: data.query_understood_as as string | undefined,
      }))
    } else if (data.ready && data.spec) {
      setMessages(prev => replaceLast(prev, { role: "assistant", kind: "dashboard", spec: data.spec as GlensDashboardSpec, sessionId: data.session_id as string, drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined }))
    } else {
      setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: (data.answer as string) ?? "No answer returned.", skill: data.skill as string | undefined, drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined, followups: data.followups as string[] | undefined, understoodAs: data.query_understood_as as string | undefined }))
    }
  }

  async function sendMessage(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, withId({ role: "user", text }), withId({ role: "assistant", kind: "loading" })])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (activeId) body.session_id = activeId
      if (pathname) body.page_context = pathname

      const res = await authFetch(`${API}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: `Request failed (${res.status}). Try again.` }))
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const evt = JSON.parse(line.slice(6)) as Record<string, unknown>
          if (evt.type === "thinking") {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last?.role === "assistant" && last.kind === "loading") {
                return replaceLast(prev, { ...last, label: evt.label as string })
              }
              return prev
            })
          } else if (evt.type === "token") {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last?.role === "assistant" && (last.kind === "loading" || last.kind === "streaming")) {
                const current = last.kind === "streaming" ? (last as { text: string }).text : ""
                return replaceLast(prev, { role: "assistant", kind: "streaming", text: current + (evt.text as string) })
              }
              return prev
            })
          } else if (evt.type === "done") {
            _applyData(evt, text)
          } else if (evt.type === "error") {
            setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: (evt.message as string) ?? "Something went wrong." }))
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: "Network error. Please try again." }))
    } finally {
      setLoading(false)
    }
  }

  const hasThread = messages.length > 0

  return (
    <div style={{ display: "flex", height: "calc(100vh - 60px)", overflow: "hidden" }}>

      {/* Sidebar */}
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={selectSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onNew={startNew}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(v => !v)}
      />

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--surface)" }}>

        {/* Thread */}
        <div
          ref={threadRef}
          style={{ flex: 1, overflowY: "auto", padding: hasThread ? "32px 48px" : "0", display: hasThread ? "block" : "flex", flexDirection: "column", justifyContent: "center" }}
        >
          {!hasThread && (
            <div style={{ maxWidth: 680, width: "100%", margin: "0 auto", padding: "32px 24px" }}>
              <div style={{ textAlign: "center", marginBottom: 28 }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: "var(--text)", marginBottom: 8, letterSpacing: "-0.01em" }}>
                  What do you want to see?
                </div>
                <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
                  Ask about blocks, spend, sessions, team memory.
                </div>
              </div>
              <div style={{ marginBottom: 20 }}>
                <ChatInput onSubmit={sendMessage} disabled={loading} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8 }}>
                {suggestions.map(s => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    style={{
                      fontSize: 13,
                      padding: "12px 14px",
                      borderRadius: 10,
                      border: "1px solid var(--border)",
                      background: "var(--surface-2)",
                      color: "var(--text-2)",
                      cursor: "pointer",
                      textAlign: "left",
                      lineHeight: 1.4,
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ maxWidth: 800, margin: "0 auto" }}>
            {messages.map((msg) => {
              if (msg.role === "user") return (
                <UserBubble
                  key={msg.id}
                  text={msg.text}
                  onEdit={newText => {
                    const cutId = msg.id
                    setMessages(prev => {
                      const cutIdx = prev.findIndex(m => m.id === cutId)
                      return cutIdx >= 0 ? prev.slice(0, cutIdx) : prev
                    })
                    sendMessage(newText)
                  }}
                />
              )
              if (msg.kind === "loading") return <LoadingBubble key={msg.id} label={msg.label} />
              if (msg.kind === "streaming") return <AnswerBubble key={msg.id} text={msg.text} skill="governance" />
              const copyText =
                msg.kind === "answer" ? msg.text :
                msg.kind === "blocks" ? msg.answer :
                msg.kind === "table"  ? msg.answer :
                msg.kind === "page"   ? msg.answer :
                msg.kind === "policy_confirm" ? msg.answer :
                        msg.kind === "action_confirm" ? msg.summary :
                undefined
              return (
                <div key={msg.id}>
                  {msg.kind === "answer" && <AnswerBubble text={msg.text} skill={msg.skill} drilldown={msg.drilldown} followups={msg.followups} onFollowup={sendMessage} understoodAs={msg.understoodAs} />}
                  {msg.kind === "dashboard" && <DashboardBubble spec={msg.spec} sessionId={msg.sessionId} authFetch={authFetch} drilldown={msg.drilldown} />}
                  {msg.kind === "blocks" && <BlocksBubble answer={msg.answer} blocks={msg.blocks as any} warning={msg.warning} skill={msg.skill} understoodAs={msg.understoodAs} drilldown={msg.drilldown} />}
                  {msg.kind === "table" && <GenericTableBubble answer={msg.answer} columns={msg.columns as any} rows={msg.rows as any} warning={msg.warning} skill={msg.skill} drilldown={msg.drilldown} understoodAs={msg.understoodAs} />}
                  {msg.kind === "page" && <GlensPageBubble answer={msg.answer} pageKind={msg.pageKind as any} data={msg.pageData} warning={msg.warning} drilldown={msg.drilldown} />}
                  {msg.kind === "action_confirm" && (
                    <ActionConfirmBubble
                      toolName={msg.toolName}
                      approvalRequestId={msg.approvalRequestId}
                      summary={msg.summary}
                      warnings={msg.warnings}
                      expiresAt={msg.expiresAt}
                      authFetch={authFetch}
                      stream={lensStream}
                      onResult={text => setMessages(prev => replaceById(prev, msg.id, { role: "assistant", kind: "answer", text }))}
                      onRunStarted={lensStream ? (runId, wfName, initialStatus) => setMessages(prev => replaceById(prev, msg.id, { role: "assistant", kind: "run", runId, workflowName: wfName, initialStatus })) : undefined}
                      onRetry={(newRunId, wfName) => setMessages(prev => [
                        ...prev,
                        withId({ role: "assistant", kind: "run", runId: newRunId, workflowName: wfName, initialStatus: "pending" }),
                      ])}
                    />
                  )}
                  {msg.kind === "run" && (
                    <RunBubble
                      runId={msg.runId}
                      workflowName={msg.workflowName}
                      initialStatus={msg.initialStatus}
                      stream={lensStream}
                      authFetch={authFetch}
                      onRetry={(newRunId, wfName) => setMessages(prev => [
                        ...prev,
                        withId({ role: "assistant", kind: "run", runId: newRunId, workflowName: wfName, initialStatus: "pending" }),
                      ])}
                    />
                  )}
                  {msg.kind === "policy_confirm" && (
                    <PolicyConfirmBubble
                      answer={msg.answer}
                      action={msg.action}
                      skill={msg.skill}
                      draft={msg.draft}
                      mapping={msg.mapping}
                      targetRuleId={msg.targetRuleId}
                      sessionId={msg.sessionId}
                      authFetch={authFetch}
                      warning={msg.warning}
                      onResult={text => setMessages(prev => replaceById(prev, msg.id, { role: "assistant", kind: "answer", text, skill: msg.skill }))}
                    />
                  )}
                  <MessageFooter text={copyText} sessionId={activeId} messageId={msg.id} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Input — bottom-anchored once the thread has content */}
        {hasThread && (
          <div style={{ borderTop: "1px solid var(--border)", background: "var(--surface)", padding: "12px 48px 16px" }}>
            <div style={{ maxWidth: 800, margin: "0 auto" }}>
              <ChatInput onSubmit={sendMessage} disabled={loading} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
