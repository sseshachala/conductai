"use client"

import { useEffect, useRef, useState } from "react"
import { duration as formatDuration } from "@/lib/runUtils"

interface RunEvent {
  id: string
  kind: string
  block_id: string | null
  payload: Record<string, unknown>
  created_at?: string
}

interface FailureSummary {
  code?: string
  category?: string
  stop_reason?: string
  message?: string
  block_id?: string | null
  next_action?: string
}

interface RunMeta {
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string | null
  explainability?: {
    version?: string
    source?: string
    trigger_provider?: string
    budget?: { max_turns?: number; max_cost_usd?: number }
  } | null
  governance?: {
    policy_surface?: string
    provider?: string
    enforcement_mode?: string
    version?: string
  } | null
}

interface Props {
  workflowId: string
  runId: string
  initialStatus: string
  initialMeta: RunMeta
  maxTurns?: number | null
  getToken?: (() => Promise<string | null>) | null
  onSseConnected?: () => void
  onSseEnded?: () => void
}

// ── helpers ───────────────────────────────────────────────────────────────────

function fmt(ts: string | null) {
  return ts ? new Date(ts).toLocaleString() : "—"
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

/** Returns true when an error string indicates a timeout rather than a logic failure */
function isTimeoutError(error: string | undefined): boolean {
  if (!error) return false
  const s = error.toLowerCase()
  return s.includes("timed out") || s.includes("timeouterror") || s.includes("did not become")
}

// ── Design-token inline style helpers ────────────────────────────────────────

function statusBadgeStyle(status: string): React.CSSProperties {
  switch (status) {
    case "running":   return { background: "var(--info-bg, #eff6ff)", color: "var(--info, #2563eb)" }
    case "succeeded": return { background: "var(--ok-bg, #f0fdf4)",   color: "var(--ok, #16a34a)" }
    case "failed":    return { background: "var(--err-bg, #fef2f2)",  color: "var(--err, #dc2626)" }
    case "paused":    return { background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }
    case "timed_out": return { background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }
    default:          return { background: "var(--surface-3, #f5f5f4)", color: "var(--text-3, #78716c)" }
  }
}

function typeChipStyle(type: string): React.CSSProperties {
  switch (type) {
    case "trigger":  return { background: "var(--blk-trigger-bg, #eff6ff)", color: "var(--blk-trigger-dot, #2563eb)" }
    case "brain":    return { background: "var(--blk-brain-bg, #f5f3ff)",   color: "#7c3aed" }
    case "tool":     return { background: "var(--blk-memory-bg, #fef9c3)",  color: "var(--warn, #d97706)" }
    case "logic":    return { background: "var(--surface-3, #f5f5f4)",      color: "var(--text-3, #78716c)" }
    case "approval": return { background: "var(--warn-bg, #fffbeb)",        color: "var(--warn, #d97706)" }
    case "output":   return { background: "var(--err-bg, #fef2f2)",         color: "var(--err, #dc2626)" }
    case "cleanup":  return { background: "var(--surface-2, #fafaf9)",      color: "var(--text-muted, #a8a29e)" }
    default:         return { background: "var(--surface-3, #f5f5f4)",      color: "var(--text-3, #78716c)" }
  }
}

const FILE_ACTION_COLOR: Record<string, string> = {
  created:  "var(--ok, #16a34a)",
  modified: "var(--info, #2563eb)",
  deleted:  "var(--err, #dc2626)",
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
  budgetExhausted?: {
    turns: number
    costUsd: number
    reason?: string
    stopReason?: string
    nextAction?: string
    maxTurns?: number
    maxCostUsd?: number
  }
  provider?: string
  model?: string
  routingReason?: string
  sandboxProvider?: string
  sandboxDecision?: string
  timedOut?: boolean
  failure?: FailureSummary
  nextAction?: string
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
}

function formatModelLabel(model: string): string {
  if (model === "claude-opus-4-7") return "Claude Opus 4.7"
  if (model === "claude-sonnet-4-6") return "Claude Sonnet 4.6"
  if (model === "claude-haiku-4-5-20251001") return "Claude Haiku 4.5"
  if (model === "gpt-4.1") return "GPT-4.1"
  if (model === "gpt-4.1-mini") return "GPT-4.1 Mini"
  return model
}

function dotStyle(row: BlockRow, isSkipped: boolean): React.CSSProperties {
  let borderColor: string
  let background: string
  let animation: string | undefined

  if (row.status === "completed" && !isSkipped) {
    borderColor = "var(--ok, #16a34a)"; background = "var(--ok, #16a34a)"
  } else if (row.status === "failed" && row.timedOut) {
    borderColor = "var(--warn, #d97706)"; background = "var(--warn, #d97706)"
  } else if (row.status === "failed") {
    borderColor = "var(--err, #dc2626)"; background = "var(--err, #dc2626)"
  } else if (row.status === "running") {
    borderColor = "var(--info, #2563eb)"; background = "var(--info, #2563eb)"; animation = "pulse 2s cubic-bezier(.4,0,.6,1) infinite"
  } else if (isSkipped) {
    borderColor = "var(--surface-3, #f5f5f4)"; background = "var(--surface-3, #f5f5f4)"
  } else {
    borderColor = "var(--surface-3, #f5f5f4)"; background = "var(--surface-3, #f5f5f4)"
  }

  return {
    width: 13,
    height: 13,
    borderRadius: "50%",
    border: `2px solid ${borderColor}`,
    background,
    display: "grid",
    placeItems: "center",
    boxShadow: "0 0 0 4px var(--bg, #fff)",
    ...(animation ? { animation } : {}),
  }
}

function cardStyle(row: BlockRow): React.CSSProperties {
  if (row.status === "failed" && row.timedOut) {
    return { flex: 1, padding: "12px 15px", background: "var(--warn-bg, #fffbeb)", borderColor: "var(--warn-bd, #fde68a)" }
  }
  if (row.status === "failed") {
    return { flex: 1, padding: "12px 15px", background: "var(--err-bg, #fef2f2)", borderColor: "var(--err-bd, #fecaca)" }
  }
  if (row.output?.status === "approval_required") {
    return { flex: 1, padding: "12px 15px", background: "var(--warn-bg, #fffbeb)", borderColor: "var(--warn-bd, #fde68a)" }
  }
  return { flex: 1, padding: "12px 15px" }
}

function BlockRowView({ row, isLast }: { row: BlockRow; isLast: boolean }) {
  const isTimedOut = row.timedOut === true
  const [expanded, setExpanded] = useState(row.status === "failed")
  const [diffExpanded, setDiffExpanded] = useState(false)
  const durRaw = formatDuration(row.startedAt ?? null, row.completedAt ?? null)
  const dur = durRaw === "—" ? null : durRaw
  const summary = row.output ? summariseOutput(row.output, row.type) : null
  const isSkipped = row.output?.skipped === true
  const prUrl = row.output?.pr_url as string | undefined

  const labelColor: string =
    row.status === "failed" && isTimedOut ? "var(--warn, #d97706)" :
    row.status === "failed"               ? "var(--err, #dc2626)" :
    isSkipped                             ? "var(--text-muted, #a8a29e)" :
    "var(--text, #1c1917)"

  const rawOutputPreStyle: React.CSSProperties = {
    fontFamily: "var(--font-mono, monospace)",
    margin: "8px 0 0",
    padding: "10px 12px",
    background: "var(--surface-3, #f5f5f4)",
    borderRadius: 8,
    fontSize: 11.5,
    overflowX: "auto",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    maxHeight: 192,
  }

  return (
    <div style={{ display: "flex", gap: 14, position: "relative", paddingBottom: 4 }}>
      {/* Vertical connector */}
      {!isLast && (
        <span style={{
          position: "absolute",
          left: 13,
          top: 10,
          bottom: 30,
          width: 2,
          background: "var(--border, #e7e5e4)",
          zIndex: 1,
        }} />
      )}

      {/* Dot column */}
      <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
        <span style={dotStyle(row, isSkipped)} />
      </div>

      {/* Card */}
      <div className="card" style={cardStyle(row)}>
        {/* Header row */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 650, fontSize: 13.5, color: labelColor }}>
            {isTimedOut && <span aria-hidden="true" style={{ marginRight: 4 }}>⏱</span>}
            {row.label}
          </span>

          {/* Type chip */}
          <span
            className="chip"
            style={{
              height: 18,
              fontSize: 9,
              fontWeight: 800,
              letterSpacing: ".07em",
              padding: "0 6px",
              textTransform: "uppercase",
              ...typeChipStyle(row.type),
            }}
          >
            {({
              brain: "BRAIN",
              tool: "TOOL CALL",
              mcp: "MCP",
              logic: "LOGIC",
              memory: "MEMORY",
              guard: "GUARD",
              approval: "APPROVAL",
              output: "OUTPUT",
              cleanup: "CLEANUP",
              trigger: "TRIGGER",
            } as Record<string, string>)[row.type] ?? row.type.toUpperCase()}
          </span>

          {/* Cost badge for Brain blocks */}
          {row.type === "brain" && row.costUsd !== undefined && row.costUsd > 0 && (
            <span className="mono" style={{ fontSize: 9, color: "var(--text-muted, #a8a29e)", background: "var(--surface-2, #fafaf9)", border: "1px solid var(--border, #e7e5e4)", padding: "1px 6px", borderRadius: 4, marginLeft: 4 }}>
              {row.inputTokens?.toLocaleString()} tok · ${row.costUsd.toFixed(4)}
            </span>
          )}

          {/* Provider badge */}
          {row.type === "brain" && row.provider && (
            <span style={{ fontSize: 9, color: "#0369a1", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "1px 6px", borderRadius: 4, fontWeight: 500, cursor: "default" }}>
              {PROVIDER_LABELS[row.provider] ?? row.provider}
            </span>
          )}

          {/* Model badge */}
          {row.type === "brain" && row.model && (
            <span
              title={row.routingReason}
              className="mono"
              style={{ fontSize: 10.5, color: "var(--text-muted, #a8a29e)", cursor: "default" }}
            >
              {formatModelLabel(row.model)}
            </span>
          )}

          {/* Sandbox routing badge — proxy/modal/e2b */}
          {row.type === "brain" && row.sandboxDecision && (
            <span
              title={row.sandboxProvider ? `Provider: ${row.sandboxProvider}` : row.sandboxDecision}
              style={{
                fontSize: 9,
                fontWeight: 600,
                padding: "1px 6px",
                borderRadius: 4,
                background: row.sandboxDecision === "proxy" ? "#f5f5f4" : "#f0fdf4",
                color: row.sandboxDecision === "proxy" ? "#78716c" : "#15803d",
                border: `1px solid ${row.sandboxDecision === "proxy" ? "#d6d3d1" : "#bbf7d0"}`,
                cursor: "default",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {row.sandboxProvider ?? row.sandboxDecision}
            </span>
          )}

          {dur && (
            <span className="mono" style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--text-muted, #a8a29e)" }}>
              {dur}
            </span>
          )}
          {row.status === "running" && (
            <span
              className="mono"
              style={{ fontSize: 11.5, color: "var(--info, #2563eb)", marginLeft: "auto", animation: "pulse 2s cubic-bezier(.4,0,.6,1) infinite" }}
            >
              running…
            </span>
          )}
        </div>

        {/* Brain tool calls — live sub-steps */}
        {row.toolCalls && row.toolCalls.length > 0 && (
          <div style={{ marginTop: 6, borderLeft: "2px solid #ddd6fe", paddingLeft: 8 }}>
            {row.toolCalls.map((tc, i) => (
              <p key={i} className="mono" style={{ fontSize: 10, color: "var(--text-3, #78716c)", whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 }}>
                {tc.summary}
              </p>
            ))}
          </div>
        )}

        {/* Budget exhausted warning */}
        {row.budgetExhausted && (
          <div style={{ marginTop: 6 }}>
            <p style={{ fontSize: 10, fontWeight: 500, color: "var(--warn, #d97706)", background: "var(--warn-bg, #fffbeb)", border: "1px solid var(--warn-bd, #fde68a)", borderRadius: 4, padding: "1px 6px", display: "inline-block", margin: 0 }}>
              ⚠ Budget exhausted ({row.budgetExhausted.reason ?? row.budgetExhausted.stopReason ?? "max_turns_reached"})
              {` · ${row.budgetExhausted.turns} turns · $${row.budgetExhausted.costUsd.toFixed(4)}`}
            </p>
            {row.budgetExhausted.nextAction && (
              <p style={{ marginTop: 2, fontSize: 12, color: "var(--text-3, #78716c)", lineHeight: 1.35 }}>
                Next: {row.budgetExhausted.nextAction}
              </p>
            )}
          </div>
        )}

        {/* Error */}
        {row.status === "failed" && row.error && (
          <p style={{ marginTop: 4, fontSize: 12.5, color: isTimedOut ? "var(--warn, #d97706)" : "var(--err, #dc2626)", lineHeight: 1.4 }}>
            {row.error}
          </p>
        )}

        {row.status === "failed" && (row.failure?.code || row.nextAction) && (
          <div style={{ marginTop: 4 }}>
            {row.failure?.code && (
              <p className="mono" style={{ fontSize: 11, color: "var(--text-3, #78716c)", margin: 0 }}>
                Reason: {row.failure.code}
              </p>
            )}
            {row.nextAction && (
              <p style={{ fontSize: 12, color: "var(--text-3, #78716c)", margin: "2px 0 0", lineHeight: 1.35 }}>
                Next: {row.nextAction}
              </p>
            )}
          </div>
        )}

        {/* Summary line */}
        {summary && row.status !== "failed" && (
          <p style={{ marginTop: 4, fontSize: 12.5, color: isSkipped ? "var(--text-muted, #a8a29e)" : "var(--text-3, #78716c)", lineHeight: 1.4, fontStyle: isSkipped ? "italic" : undefined }}>
            {summary}
          </p>
        )}

        {/* PR link — prominent */}
        {prUrl && (
          <a href={prUrl} target="_blank" rel="noopener noreferrer"
            style={{ display: "inline-flex", alignItems: "center", gap: 4, marginTop: 6, fontSize: 12, fontWeight: 500, color: "var(--info, #2563eb)", textDecoration: "none" }}>
            View PR →
          </a>
        )}

        {/* Files changed (Brain block) */}
        {row.filesChanged && row.filesChanged.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <p style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: ".1em", color: "var(--text-muted, #a8a29e)", marginBottom: 4 }}>Files changed</p>
            {row.filesChanged.map((f, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className="mono" style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", width: 52, flexShrink: 0, color: FILE_ACTION_COLOR[f.action] }}>{f.action}</span>
                <span className="mono" style={{ fontSize: 10, color: "var(--text-3, #78716c)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.path}</span>
              </div>
            ))}
            {row.diffStat && (
              <>
                <button
                  onClick={() => setDiffExpanded(d => !d)}
                  style={{ marginTop: 4, fontSize: 11.5, color: "var(--text-muted, #a8a29e)", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", padding: 0 }}
                >
                  {diffExpanded ? "▾ hide diff" : "▸ show diff"}
                </button>
                {diffExpanded && (
                  <pre className="mono" style={rawOutputPreStyle}>
                    {row.diffStat.split("\n").map((line, i) => {
                      const lineColor =
                        line.startsWith("+") && !line.startsWith("+++") ? "var(--ok, #16a34a)" :
                        line.startsWith("-") && !line.startsWith("---") ? "var(--err, #dc2626)" :
                        line.startsWith("@@") ? "var(--info, #2563eb)" :
                        "var(--text-3, #78716c)"
                      return (
                        <span key={i} style={{ display: "block", color: lineColor }}>
                          {line || " "}
                        </span>
                      )
                    })}
                  </pre>
                )}
              </>
            )}
          </div>
        )}

        {/* Expand/collapse raw output */}
        {row.output && !isSkipped && row.status === "completed" && (
          <button
            onClick={() => setExpanded(e => !e)}
            style={{ marginTop: 4, fontSize: 11.5, color: "var(--text-muted, #a8a29e)", cursor: "pointer", display: "flex", alignItems: "center", gap: 5, background: "none", border: "none", padding: 0 }}
          >
            {expanded ? "▾ hide output" : "▸ raw output"}
          </button>
        )}
        {expanded && row.output && (
          <pre className="mono" style={rawOutputPreStyle}>
            {JSON.stringify(row.output, null, 2)}
          </pre>
        )}
        {expanded && row.error && row.status === "failed" && (
          <pre className="mono" style={{
            ...rawOutputPreStyle,
            color: isTimedOut ? "var(--warn, #d97706)" : "var(--err, #dc2626)",
            background: isTimedOut ? "var(--warn-bg, #fffbeb)" : "var(--err-bg, #fef2f2)",
            border: `1px solid ${isTimedOut ? "var(--warn-bd, #fde68a)" : "var(--err-bd, #fecaca)"}`,
          }}>
            {row.error}
          </pre>
        )}
      </div>
    </div>
  )
}

// ── Run terminal row ──────────────────────────────────────────────────────────

function RunTerminalRow({ runFailed, runCompleted }: {
  runFailed?: RunEvent
  runCompleted?: RunEvent
}) {
  if (!runFailed && !runCompleted) return null

  const isReaped = runFailed?.payload?.reaped === true
  const errMsg   = typeof runFailed?.payload?.error === "string" ? runFailed.payload.error : ""
  const failure = (runFailed?.payload?.failure as FailureSummary | undefined) ?? undefined
  const reasonCode = typeof runFailed?.payload?.reason_code === "string" ? runFailed.payload.reason_code : failure?.code
  const nextAction = typeof runFailed?.payload?.next_action === "string" ? runFailed.payload.next_action : failure?.next_action

  if (runFailed) {
    if (isReaped) {
      return (
        <div style={{ display: "flex", gap: 14, position: "relative", paddingTop: 4 }}>
          <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
            <span style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid var(--warn, #d97706)", background: "var(--warn, #d97706)", display: "grid", placeItems: "center", boxShadow: "0 0 0 4px var(--bg, #fff)" }} />
          </div>
          <div className="card" style={{ flex: 1, padding: "12px 15px", background: "var(--warn-bg, #fffbeb)", border: "1px solid var(--warn-bd, #fde68a)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <p style={{ fontWeight: 600, color: "var(--warn, #d97706)", margin: 0, fontSize: 13.5 }}>
                <span aria-hidden="true" style={{ marginRight: 4 }}>⏱</span>
                Timed out
              </p>
              <span
                className="chip"
                style={{ height: 18, fontSize: 9, fontWeight: 800, letterSpacing: ".07em", padding: "0 6px", textTransform: "uppercase", background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }}
              >
                reaped
              </span>
            </div>
            {errMsg && (
              <p style={{ marginTop: 4, fontSize: 12.5, color: "var(--warn, #d97706)", lineHeight: 1.4 }}>{errMsg}</p>
            )}
          </div>
        </div>
      )
    }
    return (
      <div style={{ display: "flex", gap: 14, position: "relative", paddingTop: 4 }}>
        <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
          <span style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid var(--err, #dc2626)", background: "var(--err, #dc2626)", display: "grid", placeItems: "center", boxShadow: "0 0 0 4px var(--bg, #fff)" }} />
        </div>
        <div className="card" style={{ flex: 1, padding: "12px 15px", background: "var(--err-bg, #fef2f2)", border: "1px solid var(--err-bd, #fecaca)" }}>
          <p style={{ fontWeight: 600, color: "var(--err, #dc2626)", margin: 0, fontSize: 13.5 }}>
            Run failed{errMsg ? ` — ${errMsg}` : ""}
          </p>
          {reasonCode && (
            <p className="mono" style={{ marginTop: 4, fontSize: 11, color: "var(--text-3, #78716c)" }}>
              Reason: {reasonCode}
            </p>
          )}
          {nextAction && (
            <p style={{ marginTop: 2, fontSize: 12.5, color: "var(--text-3, #78716c)", lineHeight: 1.4 }}>
              Next: {nextAction}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: "flex", gap: 14, position: "relative", paddingTop: 4 }}>
      <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
        <span style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid var(--ok, #16a34a)", background: "var(--ok, #16a34a)", display: "grid", placeItems: "center", boxShadow: "0 0 0 4px var(--bg, #fff)" }} />
      </div>
      <div className="card" style={{ flex: 1, padding: "12px 15px", background: "var(--ok-bg, #f0fdf4)", border: "1px solid var(--ok-bd, #bbf7d0)" }}>
        <p style={{ fontWeight: 600, color: "var(--ok, #16a34a)", margin: 0, fontSize: 13.5 }}>Run completed successfully</p>
      </div>
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

export default function RunTrace({ workflowId, runId, initialStatus, initialMeta, maxTurns, getToken, onSseConnected, onSseEnded }: Props) {
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
      const headers = await buildHeaders(getToken)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
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
    buildHeaders(getToken).then(headers =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
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
      es.onopen = () => { setSseError(false); onSseConnected?.() }
      es.onmessage = (e) => {
        if (e.data === "[DONE]") { setDone(true); es?.close(); onSseEnded?.(); refreshMeta(); return }
        const event: RunEvent = JSON.parse(e.data)
        setEvents(prev => prev.find(p => p.id === event.id) ? prev : [...prev, event])
        if (event.kind === "run_completed") setStatus("succeeded")
        if (event.kind === "run_failed") setStatus("failed")
        if (event.kind === "run_paused" || event.kind === "approval_requested") {
          setStatus("paused"); setApprovalPending(true); setApprovalBlockId(event.block_id)
        }
      }
      es.onerror = () => { es?.close(); setSseError(true); setDone(true); onSseEnded?.(); refreshMeta() }
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
        if (typeof out.provider === "string") blockMap[ev.block_id].provider = out.provider
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

  const runFailed = events.find(e => e.kind === "run_failed")
  const runCompleted = events.find(e => e.kind === "run_completed")
  const totalDurRaw = formatDuration(meta.started_at ?? null, meta.completed_at ?? null)
  const totalDur = totalDurRaw === "—" ? null : totalDurRaw

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
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* SSE disconnect banner */}
      {sseError && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, borderRadius: 8, background: "var(--err-bg, #fef2f2)", border: "1px solid var(--err-bd, #fecaca)", padding: "8px 12px", fontSize: 12, color: "var(--err, #dc2626)", fontWeight: 500 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--err, #dc2626)", flexShrink: 0 }} />
          Stream disconnected — refresh to resume live updates.
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
          <BlockRowView key={row.blockId} row={row} isLast={i === blockRows.length - 1 && !runCompleted && !runFailed} />
        ))}

        {/* Run-level terminal event */}
        <RunTerminalRow runFailed={runFailed} runCompleted={runCompleted} />

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
