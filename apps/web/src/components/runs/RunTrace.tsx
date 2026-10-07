"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { duration as formatDuration } from "@/lib/runUtils"
import { API } from "@/lib/api"
import { useRunEventStream } from "@/hooks/useRunEventStream"
import { useWorkspace } from "@/lib/WorkspaceContext"
import type { RunEvent, FailureSummary, RunMeta, FileChanged, ToolCall, BlockRow } from "./run-trace/types"
import { fmt, isTimeoutError, statusBadgeStyle } from "./run-trace/helpers"
import { BlockRowView } from "./run-trace/BlockRowView"
import { RunTerminalRow } from "./run-trace/RunTerminalRow"

interface Props {
  workflowId: string
  runId: string
  initialStatus: string
  initialMeta: RunMeta
  maxTurns?: number | null
  getToken?: (() => Promise<string | null>) | null
  onSseConnected?: () => void
  onSseEnded?: () => void
  // #1512 followup — Lens embed lives inside a scrollable chat container.
  // Auto-scroll on every SSE event yanks the container around and reads as
  // flicker to the user. Canvas page still uses the auto-scroll default.
  embedded?: boolean
}

// ── Main component ────────────────────────────────────────────────────────────

async function buildHeaders(getToken?: (() => Promise<string | null>) | null, workspaceId?: string | null): Promise<Record<string, string>> {
  const h: Record<string, string> = {}
  if (getToken) {
    const token = await getToken()
    if (token) h["Authorization"] = `Bearer ${token}`
  }
  if (workspaceId) h["X-Workspace-Id"] = workspaceId
  return h
}

export default function RunTrace({ workflowId, runId, initialStatus, initialMeta, maxTurns, getToken, onSseConnected, onSseEnded, embedded = false }: Props) {
  const { activeWorkspace } = useWorkspace()
  const [events, setEvents] = useState<RunEvent[]>([])
  const [status, setStatus] = useState(initialStatus)
  const [meta, setMeta] = useState<RunMeta>(initialMeta)
  const [done, setDone] = useState(
    initialStatus === "succeeded" || initialStatus === "failed" || initialStatus === "paused"
  )
  const [approvalPending, setApprovalPending] = useState(initialStatus === "paused")
  const [approvalBlockId, setApprovalBlockId] = useState<string | null>(initialMeta.current_block_id)
  const [approvalSubmitting, setApprovalSubmitting] = useState(false)
  const [sseError, setSseError] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const refreshMeta = async () => {
    try {
      const headers = await buildHeaders(getToken, activeWorkspace?.id)
      const res = await fetch(`${API}/workflows/${workflowId}/runs/${runId}`, { headers })
      if (res.ok) {
        const run = await res.json()
        setMeta({
          triggered_by: run.triggered_by,
          started_at: run.started_at,
          completed_at: run.completed_at,
          paused_at: run.paused_at,
          current_block_id: run.current_block_id,
          workflow_version_id: run.workflow_version_id ?? null,
          explainability: run.explainability ?? null,
          governance: run.governance ?? null,
        })
        if (run.status === "paused") { setStatus("paused"); setApprovalPending(true); setApprovalBlockId(run.current_block_id) }
        else if (["succeeded", "failed", "cancelled"].includes(run.status)) { setStatus(run.status) }
      }
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!done) return
    buildHeaders(getToken, activeWorkspace?.id).then(headers =>
      fetch(`${API}/workflows/${workflowId}/runs/${runId}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(run => {
          if (!run) return
          if (run.events) setEvents(run.events)
          setMeta({
            triggered_by: run.triggered_by,
            started_at: run.started_at,
            completed_at: run.completed_at,
            paused_at: run.paused_at,
            current_block_id: run.current_block_id,
            workflow_version_id: run.workflow_version_id ?? null,
            explainability: run.explainability ?? null,
            governance: run.governance ?? null,
          })
        }).catch(() => {})
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useRunEventStream({
    workflowId,
    runId,
    getToken,
    workspaceId: activeWorkspace?.id,
    enabled: !done,
    onOpen: () => { setSseError(false); onSseConnected?.() },
    onError: () => setSseError(true),
    onDone: () => { setDone(true); onSseEnded?.(); refreshMeta() },
    onEvent: (raw) => {
      const event = raw as unknown as RunEvent
      setEvents(prev => prev.find(p => p.id === event.id) ? prev : [...prev, event])
      if (event.kind === "run_completed") setStatus("succeeded")
      if (event.kind === "run_failed") setStatus("failed")
      if (event.kind === "run_paused" || event.kind === "approval_requested") {
        setStatus("paused"); setApprovalPending(true); setApprovalBlockId(event.block_id)
      }
    },
  })

  // #1518 — safe on both surfaces. `block: "nearest"` only scrolls the closest
  // scrollable ancestor, and only if the target is off-screen. On the canvas
  // page that's the window; inside the embedded panel it's the panel's own
  // overflow container (#1518). Never touches the parent Lens chat.
  // #1519 — instant, no smooth animation. Each SSE event snapped the
  // container smoothly which read as constant motion / flicker inside the
  // embedded panel. Instant snap = new content visible, no perceived motion.
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "auto", block: "nearest" }) }, [events])

  // ── Build block rows from events ──────────────────────────────────────────
  // #1516 — memoize so blockRows references are stable across renders that
  // didn't change events (parent re-render, panel poll). Without this, every
  // render allocates new BlockRow objects and BlockRowView reruns even when
  // its content is identical — the CSS pulse animation restarts each time
  // and the Steps tab visibly flickers on every parent update.
  const blockRows: BlockRow[] = useMemo(() => {
    const rows: BlockRow[] = []
    const blockMap: Record<string, BlockRow> = {}

    for (const ev of events) {
    if (!ev.block_id) continue

    if (ev.kind === "block_started") {
      if (blockMap[ev.block_id]) continue
      const row: BlockRow = {
        blockId: ev.block_id,
        label: (ev.payload.label as string) || ev.block_id,
        type: (ev.payload.type as string) || "tool",
        status: "running",
        startedAt: ev.created_at,
      }
      blockMap[ev.block_id] = row
      rows.push(row)
    } else if (ev.kind === "block_completed" && blockMap[ev.block_id]) {
      const out = ev.payload.output as Record<string, unknown> | undefined
      blockMap[ev.block_id].status = "completed"
      blockMap[ev.block_id].completedAt = ev.created_at
      blockMap[ev.block_id].output = out
      if (out) {
        if (typeof out.cost_usd === "number") blockMap[ev.block_id].costUsd = out.cost_usd
        if (typeof out.input_tokens === "number") blockMap[ev.block_id].inputTokens = out.input_tokens
        if (typeof out.output_tokens === "number") blockMap[ev.block_id].outputTokens = out.output_tokens
        if (typeof out.provider === "string") blockMap[ev.block_id].provider = out.provider
        if (typeof out.model === "string") blockMap[ev.block_id].model = out.model
        if (typeof out.upstream_url === "string") blockMap[ev.block_id].upstreamUrl = out.upstream_url
        if (typeof out.llm_upstream === "string") blockMap[ev.block_id].llmUpstream = out.llm_upstream
        if (typeof out.routing_reason === "string") blockMap[ev.block_id].routingReason = out.routing_reason
        if (Array.isArray(out.files_changed)) blockMap[ev.block_id].filesChanged = out.files_changed as FileChanged[]
        if (typeof out.diff_stat === "string") blockMap[ev.block_id].diffStat = out.diff_stat
        // Brain blocks output pr_url as JSON on the last line of their text output.
        // Try to parse it from out.output so the "View PR →" link works.
        if (typeof out.output === "string" && !out.pr_url) {
          const lastLine = out.output.trim().split("\n").pop() ?? ""
          try {
            const parsed = JSON.parse(lastLine)
            if (typeof parsed?.pr_url === "string") {
              blockMap[ev.block_id].output = { ...out, pr_url: parsed.pr_url }
            }
          } catch { /* not JSON, ignore */ }
        }
      }
    } else if (ev.kind === "block_failed" && blockMap[ev.block_id]) {
      const errStr = ev.payload.error as string
      const failure = (ev.payload.failure as FailureSummary | undefined) ?? undefined
      const nextAction = (ev.payload.next_action as string | undefined) ?? failure?.next_action
      blockMap[ev.block_id].status = "failed"
      blockMap[ev.block_id].completedAt = ev.created_at
      blockMap[ev.block_id].error = errStr
      blockMap[ev.block_id].timedOut = isTimeoutError(errStr)
      blockMap[ev.block_id].failure = failure
      blockMap[ev.block_id].nextAction = nextAction
    } else if (ev.kind === "block_skipped") {
      if (blockMap[ev.block_id]) continue
      const row: BlockRow = {
        blockId: ev.block_id,
        label: (ev.payload.label as string) || ev.block_id,
        type: (ev.payload.type as string) || "tool",
        status: "skipped",
        output: { skipped: true, reason: ev.payload.reason },
      }
      blockMap[ev.block_id] = row
      rows.push(row)
    } else if (ev.kind === "brain_budget_exhausted" && blockMap[ev.block_id]) {
      blockMap[ev.block_id].budgetExhausted = {
        turns: ev.payload.turns as number,
        costUsd: ev.payload.cost_usd as number,
        reason: ev.payload.reason as string | undefined,
        stopReason: ev.payload.stop_reason as string | undefined,
        nextAction: ev.payload.next_action as string | undefined,
        maxTurns: ev.payload.max_turns as number | undefined,
        maxCostUsd: ev.payload.max_cost_usd as number | undefined,
      }
    } else if (ev.kind === "sandbox_routing" && blockMap[ev.block_id]) {
      blockMap[ev.block_id].sandboxProvider = (ev.payload.provider as string) || undefined
      blockMap[ev.block_id].sandboxDecision = ev.payload.decision as string
    } else if (ev.kind === "brain_tool_call" && blockMap[ev.block_id]) {
      const call: ToolCall = {
        tool:    ev.payload.tool as string,
        summary: ev.payload.summary as string,
        turn:    ev.payload.turn as number,
      }
      blockMap[ev.block_id].toolCalls = [...(blockMap[ev.block_id].toolCalls ?? []), call]
    } else if (ev.kind === "approval_requested" && blockMap[ev.block_id]) {
      blockMap[ev.block_id].status = "running"
      blockMap[ev.block_id].output = { status: "approval_required" }
    }
    }

    return rows
  }, [events])

  const runFailed = events.find(e => e.kind === "run_failed")
  const runCompleted = events.find(e => e.kind === "run_completed")
  const totalDurRaw = formatDuration(meta.started_at ?? null, meta.completed_at ?? null)
  const totalDur = totalDurRaw === "—" ? null : totalDurRaw

  const handleApproval = async (decision: "approved" | "rejected") => {
    setApprovalSubmitting(true)
    try {
      const headers = await buildHeaders(getToken, activeWorkspace?.id)
      headers["Content-Type"] = "application/json"
      const res = await fetch(`${API}/workflows/${workflowId}/runs/${runId}/approve`, {
        method: "POST", headers,
        body: JSON.stringify({ decision, approver: "canvas-user" }),
      })
      if (res.ok) { setApprovalPending(false); setStatus("pending"); setDone(false) }
    } catch { /* ignore */ } finally { setApprovalSubmitting(false) }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* SSE disconnect banner */}
      {sseError && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, borderRadius: 8, background: "var(--err-bg, #fef2f2)", border: "1px solid var(--err-bd, #fecaca)", padding: "8px 12px", fontSize: 12, color: "var(--err, #dc2626)", fontWeight: 500 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--err, #dc2626)", flexShrink: 0 }} />
          Stream disconnected — reconnecting…
        </div>
      )}

      {/* Dry run banner */}
      {events.some(e => e.payload?.output && (e.payload.output as Record<string,unknown>)?.dry_run) && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, borderRadius: 8, background: "var(--warn-bg, #fffbeb)", border: "1px solid var(--warn-bd, #fde68a)", padding: "8px 12px", fontSize: 12, color: "var(--warn, #d97706)", fontWeight: 500 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--warn, #d97706)", flexShrink: 0 }} />
          Dry run — no real API calls were made. Use <strong style={{ marginLeft: 4 }}>Run</strong> to execute for real.
        </div>
      )}

      {/* Status bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <span
          className="sbadge"
          style={{ fontSize: 12, fontWeight: 500, padding: "3px 10px", borderRadius: 999, ...statusBadgeStyle(status) }}
        >
          {status}
        </span>
        {totalDur && <span style={{ fontSize: 12, color: "var(--text-muted, #a8a29e)" }}>{totalDur}</span>}
        {!done && (
          <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-muted, #a8a29e)" }}>
            <span className="dot pulse" style={{ display: "inline-block" }} />
            Live
          </span>
        )}
      </div>

      {/* Approval gate */}
      {approvalPending && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {/* Header */}
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border, #e7e5e4)", display: "flex", alignItems: "center", gap: 10 }}>
            <span
              className="chip"
              style={{ height: 21, fontSize: 9.5, fontWeight: 800, letterSpacing: ".07em", textTransform: "uppercase", background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }}
            >
              APPROVAL
            </span>
            <span style={{ fontWeight: 650, fontSize: 14, color: "var(--text, #1c1917)" }}>Awaiting review</span>
          </div>
          {/* Body */}
          <div style={{ padding: 18 }}>
            {/* Pulse row */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span className="dot pulse" />
              <span style={{ fontSize: 13.5, color: "var(--text-2, #44403c)" }}>
                Block is paused waiting for sign-off.
              </span>
            </div>
            {/* Block ID info card */}
            <div className="card" style={{ padding: "12px 14px", background: "var(--surface-2, #fafaf9)", marginBottom: 16 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Block ID</span>
              <code className="mono" style={{ fontSize: 12.5, color: "var(--text, #1c1917)" }}>{approvalBlockId}</code>
            </div>
            {/* Buttons */}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => handleApproval("approved")}
                disabled={approvalSubmitting}
                className="btn btn-accent"
                style={{ opacity: approvalSubmitting ? 0.5 : 1 }}
              >
                {approvalSubmitting ? "…" : "Approve"}
              </button>
              <button
                onClick={() => handleApproval("rejected")}
                disabled={approvalSubmitting}
                className="btn btn-ghost"
                style={{ color: "var(--err, #dc2626)", borderColor: "var(--err-bd, #fecaca)", opacity: approvalSubmitting ? 0.5 : 1 }}
              >
                {approvalSubmitting ? "…" : "Reject"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Meta grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 32px", fontSize: 13, color: "var(--text-3, #78716c)", borderBottom: "1px solid var(--border, #e7e5e4)", paddingBottom: 16, marginBottom: 20 }}>
        <div>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Triggered by</span>
          <span style={{ color: "var(--text, #1c1917)" }}>{meta.triggered_by ?? "—"}</span>
        </div>
        <div>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Started</span>
          <span style={{ color: "var(--text, #1c1917)" }}>{fmt(meta.started_at)}</span>
        </div>
        <div>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Completed</span>
          <span style={{ color: "var(--text, #1c1917)" }}>{fmt(meta.completed_at)}</span>
        </div>
        <div>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Version</span>
          <span className="mono" style={{ color: "var(--text, #1c1917)", fontSize: 12 }}>{meta.workflow_version_id?.slice(0, 8) ?? "—"}</span>
        </div>
        <div>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Budget cap</span>
          <span style={{ color: "var(--text, #1c1917)" }}>
            {meta.explainability?.budget?.max_turns ?? maxTurns ?? "—"} turns · ${meta.explainability?.budget?.max_cost_usd?.toFixed?.(2) ?? "—"}
          </span>
        </div>
        <div>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)", display: "block", marginBottom: 2 }}>Governance</span>
          <span style={{ color: "var(--text, #1c1917)" }}>
            {meta.governance?.policy_surface ?? "—"}
            {meta.governance?.enforcement_mode ? ` · ${meta.governance.enforcement_mode}` : ""}
          </span>
        </div>
      </div>

      {/* Block timeline */}
      <div style={{ position: "relative" }}>
        {blockRows.length === 0 && !done && (
          <p style={{ fontSize: 13, color: "var(--text-muted, #a8a29e)", padding: "16px 0" }}>Waiting for blocks to start…</p>
        )}

        {blockRows.map((row, i) => (
          <BlockRowView key={row.blockId} row={row} runId={runId} isLast={i === blockRows.length - 1 && !runCompleted && !runFailed} />
        ))}

        {/* Run-level terminal event */}
        <RunTerminalRow runFailed={runFailed} runCompleted={runCompleted} />

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
