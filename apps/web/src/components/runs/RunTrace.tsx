"use client"

import { useEffect, useRef, useState } from "react"

interface RunEvent {
  id: string
  kind: string
  block_id: string | null
  payload: Record<string, unknown>
  created_at?: string
}

interface RunMeta {
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string | null
}

interface Props {
  workflowId: string
  runId: string
  initialStatus: string
  initialMeta: RunMeta
  maxTurns?: number | null
  getToken?: (() => Promise<string | null>) | null
}

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(ts: string | null) {
  return ts ? new Date(ts).toLocaleString() : "—"
}

function duration(startTs?: string, endTs?: string): string | null {
  if (!startTs || !endTs) return null
  const ms = new Date(endTs).getTime() - new Date(startTs).getTime()
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/** Pull a human-readable one-liner from a block output */
function summariseOutput(output: Record<string, unknown>, blockType?: string): string | null {
  if (!output) return null

  // Skipped
  if (output.skipped) return `Skipped — ${output.reason ?? "no integration configured"}`

  // Dry run
  if (output.dry_run) return output.note as string ?? `Dry run — ${output.integration ?? "block"} simulated`

  // Brain output
  if (typeof output.output === "string") {
    const text = output.output.slice(0, 120)
    return text + (output.output.length > 120 ? "…" : "")
  }

  // GitHub
  if (output.pr_url) return `PR opened → ${output.pr_url}`
  if (output.branch) return `Branch created: ${output.branch}`
  if (output.html_url && output.clone_url) return `Repo created: ${output.html_url}`
  if (output.full_name) return `Repo: ${output.full_name} (${output.default_branch})`
  if (output.pull_requests) return `${(output.pull_requests as unknown[]).length} pull request(s) found`

  // Output block (slack / email / both)
  if (output.sent === true && output.integration) {
    const parts: string[] = []
    const slack = output.slack as Record<string, unknown> | undefined
    const email = output.email as Record<string, unknown> | undefined
    if (slack?.channel) parts.push(`Slack → ${slack.channel}`)
    if (email?.to) parts.push(`Email → ${email.to}`)
    if (parts.length) return parts.join("  ·  ")
    return `Sent via ${output.integration}`
  }
  // Slack direct (legacy)
  if (output.ts && output.channel) return `Message sent to ${output.channel}`
  // Email direct (legacy)
  if (output.sent === true && output.to) return `Email sent to ${output.to} — "${output.subject}"`
  if (output.sent === false) return `Not sent — ${output.reason}`

  // Linear
  if (output.identifier && output.title) return `${output.identifier}: ${output.title}`
  if (output.issues) return `${(output.issues as unknown[]).length} issue(s) fetched`
  if (output.success === true && output.comment_id) return `Comment posted`

  // DigitalOcean
  if (output.droplet_id && output.status) return `Droplet ${output.droplet_id} — ${output.status}${output.ip_address ? ` (${output.ip_address})` : ""}`
  if (output.destroyed) return `Droplet ${output.droplet_id} destroyed`

  // Vercel
  if (output.state && output.url) return `Deployment ${output.state} → ${output.url}`
  if (output.deployments && Array.isArray(output.deployments) && output.url === undefined) {
    const count = (output.deployments as unknown[]).length
    return `${count} deployment(s) listed`
  }

  // Railway
  if (output.triggered && output.service_id) return `Railway service ${output.service_id} redeployment triggered`
  if (output.services && Array.isArray(output.services)) return `${(output.services as unknown[]).length} Railway service(s) found`
  if (output.id && output.status && !output.state) return `Railway deployment ${output.status}`

  // Logic
  if (output.route) return `Route: ${output.route}${output.exit_code !== undefined ? ` (exit code ${output.exit_code})` : ""}`

  // Approval
  if (output.decision) return `Decision: ${output.decision}`
  if (output.status === "approval_required") return "Waiting for human approval…"

  // Trigger
  if (output.triggered) return "Triggered successfully"

  return null
}

const STATUS_COLORS: Record<string, string> = {
  pending:   "bg-stone-100 text-stone-500",
  running:   "bg-blue-100 text-blue-700",
  succeeded: "bg-green-100 text-green-700",
  failed:    "bg-red-100 text-red-700",
  paused:    "bg-orange-100 text-orange-700",
}

const TYPE_BADGE: Record<string, string> = {
  trigger:  "bg-blue-50 text-blue-600",
  brain:    "bg-purple-50 text-purple-600",
  tool:     "bg-green-50 text-green-600",
  logic:    "bg-gray-100 text-gray-600",
  memory:   "bg-amber-50 text-amber-600",
  approval: "bg-orange-50 text-orange-600",
  output:   "bg-rose-50 text-rose-600",
  cleanup:  "bg-yellow-50 text-yellow-600",
}

// ── Block row component ───────────────────────────────────────────────────────

interface FileChanged {
  path: string
  action: "created" | "modified" | "deleted"
}

interface ToolCall {
  tool: string
  summary: string
  turn: number
}

interface BlockRow {
  blockId: string
  label: string
  type: string
  status: "running" | "completed" | "failed" | "skipped"
  startedAt?: string
  completedAt?: string
  output?: Record<string, unknown>
  error?: string
  costUsd?: number
  inputTokens?: number
  outputTokens?: number
  filesChanged?: FileChanged[]
  diffStat?: string
  toolCalls?: ToolCall[]
  budgetExhausted?: { turns: number; costUsd: number }
  model?: string
  routingReason?: string
}

const FILE_ACTION_COLOR: Record<string, string> = {
  created:  "text-emerald-600",
  modified: "text-blue-600",
  deleted:  "text-red-500",
}

function BlockRowView({ row, isLast }: { row: BlockRow; isLast: boolean }) {
  const [expanded, setExpanded] = useState(row.status === "failed")
  const [diffExpanded, setDiffExpanded] = useState(false)
  const dur = duration(row.startedAt, row.completedAt)
  const summary = row.output ? summariseOutput(row.output, row.type) : null
  const isSkipped = row.output?.skipped === true
  const prUrl = row.output?.pr_url as string | undefined

  const dot =
    row.status === "completed" && !isSkipped ? "bg-green-400" :
    row.status === "failed"    ? "bg-red-400" :
    row.status === "running"   ? "bg-blue-400 animate-pulse" :
    isSkipped                  ? "bg-stone-200" :
    "bg-stone-300"

  return (
    <div className="relative">
      {!isLast && <span className="absolute left-[-13px] top-4 w-px h-full bg-stone-100" />}
      <span className={`absolute left-[-17px] top-1.5 w-2.5 h-2.5 rounded-full border-2 border-white ${dot}`} />

      <div className={`pb-3 ${row.status === "failed" ? "rounded-lg bg-red-50 border border-red-100 px-3 py-2.5 -ml-1 mb-1" : ""}`}>
        {/* Header row */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-sm font-semibold ${row.status === "failed" ? "text-red-800" : isSkipped ? "text-stone-400" : "text-stone-800"}`}>
            {row.label}
          </span>
          <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${TYPE_BADGE[row.type] ?? "bg-stone-100 text-stone-500"}`}>
            {row.type}
          </span>
          {/* Cost badge for Brain blocks */}
          {row.type === "brain" && row.costUsd !== undefined && row.costUsd > 0 && (
            <span className="text-[9px] text-stone-400 font-mono bg-stone-50 border border-stone-200 px-1.5 py-0.5 rounded ml-1">
              {row.inputTokens?.toLocaleString()} tok · ${row.costUsd.toFixed(4)}
            </span>
          )}
          {/* Model badge */}
          {row.type === "brain" && row.model && (
            <span title={row.routingReason} className="text-[9px] text-violet-600 bg-violet-50 border border-violet-200 px-1.5 py-0.5 rounded font-medium cursor-default">
              {row.model.replace("claude-", "").replace(/-\d{8}$/, "")}
            </span>
          )}
          {dur && <span className="text-xs text-stone-400 ml-auto">{dur}</span>}
          {row.status === "running" && (
            <span className="text-xs text-blue-500 animate-pulse ml-auto">running…</span>
          )}
        </div>

        {/* Brain tool calls — live sub-steps */}
        {row.toolCalls && row.toolCalls.length > 0 && (
          <div className="mt-1.5 space-y-0.5 border-l-2 border-violet-200 pl-2">
            {row.toolCalls.map((tc, i) => (
              <p key={i} className="text-[10px] font-mono text-stone-500 truncate">
                {tc.summary}
              </p>
            ))}
          </div>
        )}

        {/* Budget exhausted warning */}
        {row.budgetExhausted && (
          <p className="mt-1.5 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 inline-block">
            ⚠ Turn budget exhausted ({row.budgetExhausted.turns} turns · ${row.budgetExhausted.costUsd.toFixed(4)})
          </p>
        )}

        {/* Error */}
        {row.status === "failed" && row.error && (
          <p className="mt-1 text-sm text-red-600 font-medium">{row.error}</p>
        )}

        {/* Summary line */}
        {summary && row.status !== "failed" && (
          <p className={`mt-0.5 text-xs ${isSkipped ? "text-stone-400 italic" : "text-stone-500"}`}>
            {summary}
          </p>
        )}

        {/* PR link — prominent */}
        {prUrl && (
          <a href={prUrl} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 mt-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
            View PR →
          </a>
        )}

        {/* Files changed (Brain block) */}
        {row.filesChanged && row.filesChanged.length > 0 && (
          <div className="mt-2 space-y-0.5">
            <p className="text-[9px] font-bold uppercase tracking-widest text-stone-400 mb-1">Files changed</p>
            {row.filesChanged.map((f, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className={`text-[9px] font-bold uppercase w-12 shrink-0 ${FILE_ACTION_COLOR[f.action]}`}>{f.action}</span>
                <span className="text-[10px] font-mono text-stone-600 truncate">{f.path}</span>
              </div>
            ))}
            {row.diffStat && (
              <>
                <button onClick={() => setDiffExpanded(d => !d)}
                  className="mt-1 text-[10px] text-stone-400 hover:text-stone-600">
                  {diffExpanded ? "▾ hide diff" : "▸ show diff"}
                </button>
                {diffExpanded && (
                  <div className="mt-1 rounded border border-stone-200 overflow-x-auto bg-stone-50">
                    {row.diffStat.split("\n").map((line, i) => {
                      const cls =
                        line.startsWith("+") && !line.startsWith("+++") ? "bg-emerald-50 text-emerald-700" :
                        line.startsWith("-") && !line.startsWith("---") ? "bg-red-50 text-red-600" :
                        line.startsWith("@@") ? "bg-blue-50 text-blue-600" :
                        "text-stone-500"
                      return (
                        <div key={i} className={`font-mono text-[10px] px-2 py-0.5 whitespace-pre ${cls}`}>
                          {line || " "}
                        </div>
                      )
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Expand/collapse raw output */}
        {row.output && !isSkipped && row.status === "completed" && (
          <button onClick={() => setExpanded(e => !e)}
            className="mt-1 text-[10px] text-stone-400 hover:text-stone-600">
            {expanded ? "▾ hide output" : "▸ raw output"}
          </button>
        )}
        {expanded && row.output && (
          <pre className="mt-1.5 text-[10px] text-stone-500 bg-stone-50 border border-stone-200 rounded-lg p-2.5 overflow-x-auto whitespace-pre-wrap max-h-48">
            {JSON.stringify(row.output, null, 2)}
          </pre>
        )}
        {expanded && row.error && row.status === "failed" && (
          <pre className="mt-1.5 text-[10px] text-red-400 bg-red-50 border border-red-100 rounded-lg p-2.5 overflow-x-auto whitespace-pre-wrap max-h-48">
            {row.error}
          </pre>
        )}
      </div>
    </div>
  )
}

// ── Run terminal row ─────────────────────────────────────────────────────────

function RunTerminalRow({ runFailed, runCompleted }: {
  runFailed: RunEvent | undefined
  runCompleted: RunEvent | undefined
}) {
  const isReaped = runFailed?.payload?.reaped === true
  const dotColor = runFailed
    ? (isReaped ? "bg-amber-400" : "bg-red-500")
    : "bg-green-500"

  return (
    <div className="relative pt-1">
      <span className={`absolute left-[-17px] top-2.5 w-2.5 h-2.5 rounded-full border-2 border-white ${dotColor}`} />

      {isReaped ? (
        <div>
          <p className="text-sm font-semibold text-amber-700 flex items-center gap-1.5">
            <span aria-hidden="true">⏱</span>
            Timed out
            <span className="text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
              reaped
            </span>
          </p>
          {typeof runFailed?.payload?.error === "string" && (
            <p className="mt-0.5 text-xs text-stone-400">{runFailed.payload.error}</p>
          )}
        </div>
      ) : runFailed ? (
        <p className="text-sm font-semibold text-red-700">
          {`Run failed — ${runFailed.payload?.error ?? ""}`}
        </p>
      ) : runCompleted ? (
        <p className="text-sm font-semibold text-green-700">Run completed successfully</p>
      ) : null}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

async function buildHeaders(getToken?: (() => Promise<string | null>) | null): Promise<Record<string, string>> {
  const h: Record<string, string> = {}
  if (getToken) {
    const token = await getToken()
    if (token) h["Authorization"] = `Bearer ${token}`
  }
  const ws = getCookie("delegator_project_id")
  if (ws) h["X-Workspace-Id"] = ws
  return h
}

export default function RunTrace({ workflowId, runId, initialStatus, initialMeta, maxTurns, getToken }: Props) {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [status, setStatus] = useState(initialStatus)
  const [meta, setMeta] = useState<RunMeta>(initialMeta)
  const [done, setDone] = useState(
    initialStatus === "succeeded" || initialStatus === "failed" || initialStatus === "paused"
  )
  const [approvalPending, setApprovalPending] = useState(initialStatus === "paused")
  const [approvalBlockId, setApprovalBlockId] = useState<string | null>(initialMeta.current_block_id)
  const [approvalSubmitting, setApprovalSubmitting] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const refreshMeta = async () => {
    try {
      const headers = await buildHeaders(getToken)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
      if (res.ok) {
        const run = await res.json()
        setMeta({ triggered_by: run.triggered_by, started_at: run.started_at, completed_at: run.completed_at, paused_at: run.paused_at, current_block_id: run.current_block_id, workflow_version_id: run.workflow_version_id ?? null })
        if (run.status === "paused") { setStatus("paused"); setApprovalPending(true); setApprovalBlockId(run.current_block_id) }
        else if (["succeeded", "failed", "cancelled"].includes(run.status)) { setStatus(run.status) }
      }
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!done) return
    buildHeaders(getToken).then(headers =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(run => {
          if (!run) return
          if (run.events) setEvents(run.events)
          setMeta({ triggered_by: run.triggered_by, started_at: run.started_at, completed_at: run.completed_at, paused_at: run.paused_at, current_block_id: run.current_block_id, workflow_version_id: run.workflow_version_id ?? null })
        }).catch(() => {})
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (done) return
    let es: EventSource | null = null
    let cancelled = false

    buildHeaders(getToken).then(headers => {
      if (cancelled) return
      const wsId = getCookie("delegator_project_id")
      const token = headers["Authorization"]?.replace("Bearer ", "") ?? ""
      const params = new URLSearchParams()
      if (token) params.set("token", token)
      if (wsId) params.set("workspace_id", wsId)
      const qs = params.toString() ? `?${params.toString()}` : ""
      es = new EventSource(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}/stream${qs}`)
      es.onmessage = (e) => {
        if (e.data === "[DONE]") { setDone(true); es?.close(); refreshMeta(); return }
        const event: RunEvent = JSON.parse(e.data)
        setEvents(prev => prev.find(p => p.id === event.id) ? prev : [...prev, event])
        if (event.kind === "run_completed") setStatus("succeeded")
        if (event.kind === "run_failed") setStatus("failed")
        if (event.kind === "run_paused" || event.kind === "approval_requested") {
          setStatus("paused"); setApprovalPending(true); setApprovalBlockId(event.block_id)
        }
      }
      es.onerror = () => { es?.close(); setDone(true); refreshMeta() }
    })

    return () => { cancelled = true; es?.close() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId, done])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [events])

  // ── Build block rows from events ──────────────────────────────────────────

  const blockRows: BlockRow[] = []
  const blockMap: Record<string, BlockRow> = {}

  for (const ev of events) {
    if (!ev.block_id) continue

    if (ev.kind === "block_started") {
      const row: BlockRow = {
        blockId: ev.block_id,
        label: (ev.payload.label as string) || ev.block_id,
        type: (ev.payload.type as string) || "tool",
        status: "running",
        startedAt: ev.created_at,
      }
      blockMap[ev.block_id] = row
      blockRows.push(row)
    } else if (ev.kind === "block_completed" && blockMap[ev.block_id]) {
      const out = ev.payload.output as Record<string, unknown> | undefined
      blockMap[ev.block_id].status = "completed"
      blockMap[ev.block_id].completedAt = ev.created_at
      blockMap[ev.block_id].output = out
      if (out) {
        if (typeof out.cost_usd === "number") blockMap[ev.block_id].costUsd = out.cost_usd
        if (typeof out.input_tokens === "number") blockMap[ev.block_id].inputTokens = out.input_tokens
        if (typeof out.output_tokens === "number") blockMap[ev.block_id].outputTokens = out.output_tokens
        if (typeof out.model === "string") blockMap[ev.block_id].model = out.model
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
      blockMap[ev.block_id].status = "failed"
      blockMap[ev.block_id].completedAt = ev.created_at
      blockMap[ev.block_id].error = ev.payload.error as string
    } else if (ev.kind === "block_skipped") {
      const row: BlockRow = {
        blockId: ev.block_id,
        label: (ev.payload.label as string) || ev.block_id,
        type: (ev.payload.type as string) || "tool",
        status: "skipped",
        output: { skipped: true, reason: ev.payload.reason },
      }
      blockMap[ev.block_id] = row
      blockRows.push(row)
    } else if (ev.kind === "brain_budget_exhausted" && blockMap[ev.block_id]) {
      blockMap[ev.block_id].budgetExhausted = {
        turns: ev.payload.turns as number,
        costUsd: ev.payload.cost_usd as number,
      }
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

  const runFailed = events.find(e => e.kind === "run_failed")
  const runCompleted = events.find(e => e.kind === "run_completed")
  const totalDur = duration(meta.started_at ?? undefined, meta.completed_at ?? undefined)

  // Aggregate tokens + cost from block_completed events
  const totalTokens = blockRows.reduce((acc, r) => acc + (r.inputTokens ?? 0) + (r.outputTokens ?? 0), 0)
  const totalCost   = blockRows.reduce((acc, r) => acc + (r.costUsd ?? 0), 0)

  // Actual turns = highest turn number seen across all brain_tool_call events
  const actualTurns = events
    .filter(e => e.kind === "brain_tool_call" && typeof e.payload?.turn === "number")
    .reduce((max, e) => Math.max(max, e.payload.turn as number), 0)

  const handleApproval = async (decision: "approved" | "rejected") => {
    setApprovalSubmitting(true)
    try {
      const headers = await buildHeaders(getToken)
      headers["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}/approve`, {
        method: "POST", headers,
        body: JSON.stringify({ decision, approver: "canvas-user" }),
      })
      if (res.ok) { setApprovalPending(false); setStatus("pending"); setDone(false) }
    } catch { /* ignore */ } finally { setApprovalSubmitting(false) }
  }

  return (
    <div className="space-y-5">

      {/* Dry run banner */}
      {events.some(e => e.payload?.output && (e.payload.output as Record<string,unknown>)?.dry_run) && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700 font-medium">
          <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
          Dry run — no real API calls were made. Use <strong>Run</strong> to execute for real.
        </div>
      )}

      {/* Summary stats grid */}
      <div className="grid grid-cols-5 gap-3 rounded-xl border border-stone-100 bg-stone-50 px-4 py-3">
        {(totalDur || !done) && (
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-0.5">Duration</p>
          <p className="text-sm font-semibold text-stone-800">{totalDur ?? "…"}</p>
        </div>
        )}
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-0.5">Turns</p>
          <p className="text-sm font-semibold text-stone-800">
            {actualTurns > 0 ? (
              maxTurns ? (
                <span>
                  {actualTurns}
                  <span className="text-stone-400 font-normal"> / {maxTurns} est.</span>
                </span>
              ) : actualTurns
            ) : "—"}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-0.5">Tokens</p>
          <p className="text-sm font-semibold text-stone-800">{totalTokens > 0 ? totalTokens.toLocaleString() : "—"}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-0.5">Est. cost</p>
          <p className="text-sm font-semibold text-stone-800">{totalCost > 0 ? `$${totalCost.toFixed(4)}` : "—"}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-0.5">Triggered by</p>
          <p className="text-sm font-semibold text-stone-800 truncate">{meta.triggered_by ?? "—"}</p>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3">
        <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${STATUS_COLORS[status] ?? STATUS_COLORS.pending}`}>
          {status}
        </span>
        {totalDur && <span className="text-xs text-stone-400">{totalDur}</span>}
        {!done && (
          <span className="flex items-center gap-1.5 text-xs text-stone-400">
            <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            Live
          </span>
        )}
      </div>

      {/* Approval gate */}
      {approvalPending && (
        <div className="rounded-xl border-2 border-orange-200 bg-orange-50 p-4">
          <p className="text-sm font-semibold text-orange-800 mb-1">Awaiting Approval</p>
          <p className="text-xs text-orange-600 mb-3">
            Block <code className="font-mono bg-orange-100 px-1 rounded">{approvalBlockId}</code> is paused waiting for sign-off.
          </p>
          <div className="flex gap-2">
            <button onClick={() => handleApproval("approved")} disabled={approvalSubmitting}
              className="px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50">
              {approvalSubmitting ? "…" : "Approve"}
            </button>
            <button onClick={() => handleApproval("rejected")} disabled={approvalSubmitting}
              className="px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50">
              {approvalSubmitting ? "…" : "Reject"}
            </button>
          </div>
        </div>
      )}

      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-3 text-sm text-stone-500 border-b border-stone-100 pb-4">
        <div><span className="text-xs text-stone-400 block mb-0.5">Triggered by</span>{meta.triggered_by ?? "—"}</div>
        <div><span className="text-xs text-stone-400 block mb-0.5">Started</span>{fmt(meta.started_at)}</div>
        <div><span className="text-xs text-stone-400 block mb-0.5">Completed</span>{fmt(meta.completed_at)}</div>
        <div><span className="text-xs text-stone-400 block mb-0.5">Version</span><span className="font-mono text-xs">{meta.workflow_version_id?.slice(0, 8) ?? "—"}</span></div>
      </div>

      {/* Block timeline */}
      <div className="relative pl-5 space-y-0">
        {blockRows.length === 0 && !done && (
          <p className="text-sm text-stone-400 py-4">Waiting for blocks to start…</p>
        )}

        {blockRows.map((row, i) => (
          <BlockRowView key={row.blockId} row={row} isLast={i === blockRows.length - 1 && !runCompleted && !runFailed} />
        ))}

        {/* Run-level terminal event */}
        {(runCompleted || runFailed) && (
          <RunTerminalRow runFailed={runFailed} runCompleted={runCompleted} />
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
