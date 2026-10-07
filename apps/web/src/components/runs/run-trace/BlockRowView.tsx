"use client"

import { memo, useState } from "react"
import { duration as formatDuration } from "@/lib/runUtils"
import { AskLensLink } from "@/components/glens/AskLensLink"
import type { BlockRow } from "./types"
import { summariseOutput, typeChipStyle, FILE_ACTION_COLOR, PROVIDER_LABELS, formatModelLabel, dotStyle, cardStyle } from "./helpers"

export const BlockRowView = memo(function BlockRowView({ row, isLast, runId }: { row: BlockRow; isLast: boolean; runId: string }) {
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
          <AskLensLink kind="run" resourceId={runId} blockId={row.blockId} />

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

          {/* AI Gateway badge */}
          {row.type === "brain" && row.upstreamUrl && (
            <span
              title={row.upstreamUrl}
              style={{ fontSize: 9, color: "#6b7280", background: "#f3f4f6", border: "1px solid #e5e7eb", padding: "1px 6px", borderRadius: 4, fontWeight: 500 }}
            >
              via {row.upstreamUrl.replace(/^https?:\/\//, "").split("/")[0]}
            </span>
          )}
          {/* LLM upstream badge — shown only when env has PROXY_CONFIG_LLM_UPSTREAM */}
          {row.type === "brain" && row.llmUpstream && (
            <span
              title={row.llmUpstream}
              style={{ fontSize: 9, color: "#7c3aed", background: "#ede9fe", border: "1px solid #ddd6fe", padding: "1px 6px", borderRadius: 4, fontWeight: 500 }}
            >
              → {row.llmUpstream.replace(/^https?:\/\//, "").split("/")[0]}
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
                background: row.sandboxDecision === "managed" ? "#f5f5f4" : "#f0fdf4",
                color: row.sandboxDecision === "managed" ? "#78716c" : "#15803d",
                border: `1px solid ${row.sandboxDecision === "managed" ? "#d6d3d1" : "#bbf7d0"}`,
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

        {/* Error / Blocked — both red (block headline still says Blocked, not Failed) */}
        {row.status === "failed" && row.error && (() => {
          const isGuardBlock = row.failure?.code === "GUARD_POLICY_BLOCKED"
          const color = isTimedOut ? "var(--warn, #d97706)" : "var(--err, #dc2626)"
          return (
            <p style={{ marginTop: 4, fontSize: 12.5, color, lineHeight: 1.4 }}>
              {isGuardBlock ? row.error.replace(/^\[ConductGuard\]\s*/, "") : row.error}
            </p>
          )
        })()}

        {row.status === "failed" && (row.failure?.code || row.nextAction) && (
          <div style={{ marginTop: 4 }}>
            {row.failure?.code && (
              <p className="mono" style={{ fontSize: 11, color: "var(--text-3, #78716c)", margin: 0 }}>
                Reason: {row.failure.code === "GUARD_POLICY_BLOCKED" ? "BLOCKED_BY_GUARD" : row.failure.code}
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
            {JSON.stringify(row.output, null, 2).replace(/\\u[\dA-Fa-f]{4}/g, m => String.fromCharCode(parseInt(m.slice(2), 16)))}
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
}, (prev, next) => (
  prev.isLast === next.isLast &&
  prev.row.blockId === next.row.blockId &&
  prev.row.status === next.row.status &&
  prev.row.startedAt === next.row.startedAt &&
  prev.row.completedAt === next.row.completedAt &&
  prev.row.error === next.row.error &&
  prev.row.output === next.row.output &&
  prev.row.toolCalls === next.row.toolCalls &&
  prev.row.budgetExhausted === next.row.budgetExhausted
))
