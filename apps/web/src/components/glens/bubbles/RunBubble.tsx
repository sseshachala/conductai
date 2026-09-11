"use client"
import { useEffect, useRef, useState } from "react"
import { API } from "@/lib/api"
import { useLensEvent } from "@/hooks/useLensEvent"
import type { LensSessionStream } from "@/hooks/useLensSessionStream"
import RunDetailPanel, { type RunMeta } from "@/components/runs/RunDetailPanel"
import type { RunBlockState } from "@/components/glens/glensTypes"
import { formatElapsed } from "@/components/glens/formatElapsed"
import { LiveElapsed } from "@/components/glens/LiveElapsed"

// ─── Run bubble ──────────────────────────────────────────────────────────────

// #1480 PR 5 — live run status inline in chat. Subscribes to run.status_changed
// events on the session stream and updates its pill in place. Always renders
// the "View run →" link so the user can jump to the run detail page.

export function RunBubble({
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

  async function _postAction(url: string, body?: unknown, onOk?: (data: Record<string, unknown>) => void, onError?: () => void) {
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
        onError?.()
        setBusy(false)
        return
      }
      const data = await res.json().catch(() => ({}))
      onOk?.(data as Record<string, unknown>)
    } catch {
      setActionErr("Network error")
      onError?.()
    } finally {
      setBusy(false)
    }
  }

  const cancelRun = () => _postAction(`${API}/workflows/${workflowId}/runs/${runId}/cancel`)
  // Optimistic — flip status locally so approve/reject buttons vanish and the
  // bubble/panel updates instantly. SSE run.status_changed confirms; if the
  // POST fails we revert and _postAction surfaces the error via actionErr.
  const decideRun = (decision: "approved" | "rejected") => {
    const prevStatus = status
    setStatus(decision === "approved" ? "running" : "cancelled")
    _postAction(
      `${API}/workflows/${workflowId}/runs/${runId}/approve`,
      { decision },
      undefined,
      () => setStatus(prevStatus),
    )
  }
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
