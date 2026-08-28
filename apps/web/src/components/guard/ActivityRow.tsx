"use client"

import { useState, type MouseEvent as ReactMouseEvent } from "react"
import { timeAgo } from "@/lib/runUtils"
import { DecisionBadge } from "./DecisionBadge"

/**
 * Shared event row used by /guard/activity (full feed) and /governance
 * (Recent activity preview). Same shape, same badges, same column widths —
 * so a user moving between pages sees one consistent representation of a
 * guard event.
 *
 * If a caller wants a slimmer layout (e.g. dashboard preview), pass
 * `compact={true}` to drop Blast Radius and Tool columns.
 */
import Link from "next/link"

export interface AuditEvent {
  id: string
  ts: string
  user_email: string | null
  ai_tool: string
  tool_call: string | null
  input_summary: string | null
  decision: string                // "allowed" | "blocked" | "warned" | "approval" | "audited"
  rule_id: string | null
  source?: "hook" | "proxy" | "mcp" | "local_audit" | "brain_block" | null
  provider?: string | null         // 'anthropic' | 'openai' | 'perplexity' (proxy only)
  model?: string | null            // vendor model id (proxy only)
  conductai_run_id?: string | null
  conductai_workflow?: string | null
  conductai_workflow_id?: string | null
  goal_id?: string | null
  goal_name?: string | null
  blast_radius?: { files: number; symbols?: number; tier: string } | null
  hostname?: string | null
  hook_session_id?: string | null
  session_id?: string | null
  agent_identity_id?: string | null
  entry_hash?: string | null
  policy_hash?: string | null
  // #1150 phase 2 — layered verdict envelope
  evaluated_rules?: Array<{ rule_id: string | null; severity?: string; action?: string }> | null
  defense_score?: number | null
  routing_meta?: {
    tier_form?: string | null
    resolved_model?: string | null
    endpoint_provider?: string | null
    reason?: string | null
    resolution_source?: string | null
  } | null
}

const TOOL_COLORS: Record<string, string> = {
  "claude-code":     "var(--chart-claude)",
  "claude_code":     "var(--chart-claude)",
  "claude_chat":     "var(--chart-claude)",
  "claude-chat":     "var(--chart-claude)",
  "claude_desktop":  "var(--chart-claude)",
  "claude-desktop":  "var(--chart-claude)",
  "claude_work":     "var(--chart-claude)",
  "claude-work":     "var(--chart-claude)",
  "codex":           "var(--chart-codex)",
  "codex_cli":       "var(--chart-codex)",
  "codex_chat":      "var(--chart-codex)",
  "cursor":          "#7c3aed",
  "windsurf":        "#0284c7",
  "copilot":         "#24292f",
  "gemini":          "#ea580c",
}

const TOOL_LABELS: Record<string, string> = {
  claude_code: "Claude Code", claude: "Claude",
  claude_chat: "Claude.ai", claude_desktop: "Claude Desktop", claude_work: "Claude Work",
  codex: "Codex", codex_cli: "Codex CLI", codex_chat: "Codex Chat",
  cursor: "Cursor", windsurf: "Windsurf", copilot: "Copilot", gemini: "Gemini",
}

export function isProxyEvent(toolCall: string | null | undefined): boolean {
  if (!toolCall) return false
  return /^(anthropic|openai|perplexity)\//.test(toolCall)
}

export function ProxyPill() {
  return (
    <span
      title="Routed through Conduct Guard Proxy"
      style={{
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: 0.4,
        padding: "1px 5px",
        borderRadius: 3,
        background: "var(--accent-weak)",
        color: "var(--accent-text)",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      via proxy
    </span>
  )
}

export function LocalRiskPill() {
  return (
    <span
      title="Pre-existing real API key detected on a dev's machine"
      style={{
        fontSize: 9.5,
        fontWeight: 700,
        letterSpacing: 0.4,
        padding: "1px 5px",
        borderRadius: 3,
        background: "color-mix(in srgb, var(--err) 16%, transparent)",
        color: "var(--err)",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      local risk
    </span>
  )
}


export function ToolBadge({ tool }: { tool: string }) {
  const norm = tool.replace(/-/g, "_")
  const color = TOOL_COLORS[tool] ?? TOOL_COLORS[norm] ?? "var(--text-3)"
  const label = TOOL_LABELS[norm] ?? tool
  return (
    <span style={{
      fontSize: 11,
      fontWeight: 600,
      color,
      background: "var(--surface-3)",
      borderRadius: 5,
      padding: "2px 7px",
    }}>
      {label}
    </span>
  )
}

export { DecisionBadge } from "./DecisionBadge"

export function BlastRadiusBadge({ br }: { br: { tier: string; files: number } }) {
  const colors: Record<string, { bg: string; text: string }> = {
    LOW:      { bg: "var(--ok-bg)",   text: "var(--ok)"   },
    MEDIUM:   { bg: "var(--warn-bg)", text: "var(--warn)"  },
    HIGH:     { bg: "#fff3e0",        text: "#e65100"      },
    CRITICAL: { bg: "var(--err-bg)",  text: "var(--err)"   },
  }
  const c = colors[br.tier] ?? colors.LOW
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: "1px 7px", borderRadius: 20,
      background: c.bg, color: c.text, whiteSpace: "nowrap",
    }}>
      {br.tier} · {br.files}f
    </span>
  )
}

export function formatTs(ts: string): string {
  try {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return ts
  }
}

const MCP_SERVER_LABELS: Record<string, string> = {
  claude_ai_conduct_ai: "Conduct",
  "agent-booster": "Booster",
  plugin_vercel_vercel: "Vercel",
}

export function formatToolCall(call: string | null | undefined): string {
  if (!call) return "—"
  // Workflow auto-guard: __guard_<block_id> → block name
  const guardM = call.match(/^__guard_(.+)$/)
  if (guardM) return guardM[1]
  // MCP tool: mcp__server__tool → Server · tool
  const mcpM = call.match(/^mcp__([^_].+?)__(.+)$/)
  if (!mcpM) return call
  const [, server, tool] = mcpM
  const label = MCP_SERVER_LABELS[server] ?? "MCP"
  return `${label} · ${tool}`
}

/** Row + inline drill-down for policy_signature_invalid events. */
export function SignatureTamperRow({ ev, isLast = false }: { ev: AuditEvent; isLast?: boolean }) {
  const [open, setOpen] = useState(false)

  let expected_signature = ""
  let computed_signature = ""
  let policy_version     = ""
  let hostname           = ev.hostname ?? ""
  try {
    const payload = JSON.parse(ev.input_summary ?? "{}")
    expected_signature = payload.expected_signature ?? ""
    computed_signature = payload.computed_signature ?? ""
    policy_version     = payload.policy_version ?? ""
    if (!hostname) hostname = payload.hostname ?? ""
  } catch { /* non-fatal */ }

  const cols = "0.8fr 1.4fr 1fr 1.2fr 1.8fr 0.9fr 0.8fr 0.9fr"

  return (
    <>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: "grid",
          gridTemplateColumns: cols,
          gap: 12,
          padding: "11px 18px",
          borderBottom: isLast && !open ? "none" : "1px solid var(--border)",
          alignItems: "center",
          background: "var(--err-bg)",
          cursor: "pointer",
        }}
        title="Click to see signature details"
      >
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }} title={formatTs(ev.ts)}>{timeAgo(ev.ts)}</div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {ev.user_email ?? "—"}
        </div>
        <div><ToolBadge tool={ev.ai_tool} /></div>
        <div className="mono" style={{ fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--err)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
          </svg>
          tampered
        </div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          Policy file tampered on {hostname || "unknown"} ({ev.user_email ?? "—"})
        </div>
        <div><span className="sbadge err" style={{ textTransform: "capitalize" }}>blocked</span></div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--err)" }}>policy_signature_invalid</div>
        <div><span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>—</span></div>
      </div>

      {open && (
        <div style={{
          padding: "14px 24px 18px",
          borderBottom: isLast ? "none" : "1px solid var(--border)",
          background: "color-mix(in srgb, var(--err-bg) 60%, var(--surface))",
          fontSize: 12,
        }}>
          <div style={{ fontWeight: 700, color: "var(--err)", marginBottom: 10 }}>Signature mismatch detail</div>
          <table style={{ borderCollapse: "collapse", width: "100%", fontFamily: "var(--font-mono, ui-monospace, monospace)", fontSize: 11.5 }}>
            <tbody>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, paddingBottom: 6, whiteSpace: "nowrap" }}>Expected signature</td>
                <td style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{expected_signature || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, paddingBottom: 6, whiteSpace: "nowrap" }}>Computed signature</td>
                <td style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{computed_signature || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, paddingBottom: 6, whiteSpace: "nowrap" }}>Policy version</td>
                <td style={{ color: "var(--text-2)" }}>{policy_version || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, whiteSpace: "nowrap" }}>Hostname</td>
                <td style={{ color: "var(--text-2)" }}>{hostname || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, whiteSpace: "nowrap" }}>Timestamp</td>
                <td style={{ color: "var(--text-2)" }}>{formatTs(ev.ts)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}


export function ActivityRow({ ev, compact = false, isLast = false }: {
  ev: AuditEvent
  compact?: boolean
  isLast?: boolean
}) {
  const [hovered, setHovered] = useState(false)
  const [open, setOpen] = useState(false)

  if (ev.rule_id === "policy_signature_invalid") {
    return <SignatureTamperRow ev={ev} isLast={isLast} />
  }

  const cols = compact
    ? "0.8fr 1.4fr 1.2fr 1.8fr 0.9fr 0.8fr"
    : "0.8fr 1.4fr 1fr 1.2fr 1.8fr 0.9fr 0.8fr 0.9fr"

  const bg = ev.decision === "blocked"
    ? "var(--err-bg)"
    : hovered ? "var(--surface-2)" : "transparent"

  return (
    <>
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => setOpen(o => !o)}
      style={{
        display: "grid",
        gridTemplateColumns: cols,
        gap: 12,
        padding: "10px 18px",
        borderBottom: (isLast && !open) ? "none" : "1px solid var(--border)",
        alignItems: "center",
        background: bg,
        transition: "background .1s",
        cursor: "pointer",
      }}
    >
      <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }} title={formatTs(ev.ts)}>{timeAgo(ev.ts)}</div>
      <div style={{ minWidth: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}
          title={ev.user_email ?? ev.agent_identity_id ?? undefined}>
          <span className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {ev.user_email ? ev.user_email.split("@")[0] : ev.conductai_workflow ?? "—"}
          </span>
          {(() => {
            const isHuman = !!ev.user_email
            const pill = (
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: ".04em",
                padding: "1px 4px", borderRadius: 3,
                background: isHuman ? "var(--surface-2)" : "#e0e7ff",
                color: isHuman ? "var(--text-muted)" : "#3730a3",
                whiteSpace: "nowrap",
              }}>
                {isHuman ? "HUMAN" : "AGENT"}
              </span>
            )
            // AGENT rows with a known identity → deep-link to /agent-identity
            // (uses the ?id=<uuid> highlight from PR #1286).
            if (!isHuman && ev.agent_identity_id) {
              return (
                <a href={`/agent-identity?tab=identities&id=${ev.agent_identity_id}`}
                   title={`View agent identity ${ev.agent_identity_id}`}
                   style={{ textDecoration: "none" }}>
                  {pill}
                </a>
              )
            }
            return pill
          })()}
        </div>
        {(ev.hook_session_id || ev.session_id) && (
          <div className="mono" style={{ fontSize: 9.5, color: "var(--text-muted)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            title={ev.hook_session_id || ev.session_id || ""}>
            {(ev.hook_session_id || ev.session_id || "").slice(-8)}
          </div>
        )}
      </div>
      {!compact && (
        <div>
          {ev.source === "brain_block" && ev.conductai_workflow ? (
            ev.conductai_run_id ? (
              <Link href={`/workflows/${ev.conductai_workflow_id}/runs/${ev.conductai_run_id}`}
                onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
                style={{ textDecoration: "none", fontSize: 11.5, fontFamily: "var(--font-mono, monospace)", color: "var(--accent-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block", maxWidth: "100%" }}>
                {ev.conductai_workflow}
              </Link>
            ) : (
              <span style={{ fontSize: 11.5, fontFamily: "var(--font-mono, monospace)", color: "var(--text-2)" }}>{ev.conductai_workflow}</span>
            )
          ) : (
            ev.conductai_run_id ? (
              <Link href={`/workflows/${ev.conductai_workflow_id}/runs/${ev.conductai_run_id}`} onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()} style={{ textDecoration: "none" }}>
                <ToolBadge tool={ev.ai_tool} />
              </Link>
            ) : (
              <ToolBadge tool={ev.ai_tool} />
            )
          )}
        </div>
      )}
      <div className="mono" style={{ fontSize: 11.5, fontWeight: 600, display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
        <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {(ev.source === "proxy") && ev.provider
            ? `${ev.provider}/${ev.model ?? "?"}`
            : ev.source === "local_audit"
              ? (ev.provider ? `${ev.provider} key found` : "local key found")
              : formatToolCall(ev.tool_call)}
        </span>
        {ev.source === "proxy" && <ProxyPill />}
        {ev.source === "brain_block" && (
          <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: ".06em", padding: "1px 5px", borderRadius: 3, background: "#ede9fe", color: "#6d28d9", border: "1px solid #c4b5fd" }}>
            AGENT
          </span>
        )}
        {ev.source === "local_audit" && <LocalRiskPill />}
      </div>
      <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
        {ev.source === "brain_block" && ev.provider && ev.model
          ? `${ev.input_summary || "vendor"} → ${ev.provider} · ${ev.model}`
          : ev.input_summary ? `${ev.input_summary}…` : "—"}
      </div>
      <div>
        {ev.conductai_run_id ? (
          <Link href={`/workflows/${ev.conductai_workflow_id}/runs/${ev.conductai_run_id}`} onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()} style={{ display: "inline-flex", alignItems: "center", gap: 3, textDecoration: "none" }}>
            <DecisionBadge decision={ev.decision} />
            <span style={{ fontSize: 11, color: "var(--accent-text)" }}>→</span>
          </Link>
        ) : (
          <DecisionBadge decision={ev.decision} />
        )}
      </div>
      <div className="mono" style={{ fontSize: 11, color: ev.rule_id ? "var(--err)" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0, display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{ev.rule_id ?? "—"}</span>
        {ev.evaluated_rules && ev.evaluated_rules.length > 1 && (
          <span
            title={`Also flagged by: ${ev.evaluated_rules
              .filter(r => r.rule_id !== ev.rule_id)
              .map(r => r.rule_id)
              .join(", ")}`}
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "var(--text-2)",
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              padding: "0 5px",
              flexShrink: 0,
            }}
          >
            +{ev.evaluated_rules.length - 1}
          </span>
        )}
      </div>
      {!compact && (
        <div>
          {ev.blast_radius ? (
            <BlastRadiusBadge br={ev.blast_radius} />
          ) : (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
          )}
        </div>
      )}
    </div>
    {open && (
      <div style={{
        padding: "12px 18px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--border)",
        background: "var(--surface-2)",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "8px 24px",
        fontSize: 11,
      }}>
        {ev.input_summary && (
          <div style={{ gridColumn: "1 / -1" }}>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Input</span>
            <span className="mono" style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{ev.input_summary}</span>
          </div>
        )}
        <div>
          <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Time</span>
          <span className="mono" style={{ color: "var(--text-2)" }}>{formatTs(ev.ts)}</span>
        </div>
        {ev.policy_hash && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Policy</span>
            <span className="mono" style={{ color: "var(--text-2)" }} title={ev.policy_hash}>sha:{ev.policy_hash.slice(0, 8)}</span>
          </div>
        )}
        {ev.entry_hash && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Chain</span>
            <span className="mono" style={{ color: "var(--text-2)" }} title={ev.entry_hash}>sha:{ev.entry_hash.slice(0, 8)}</span>
          </div>
        )}
        {ev.blast_radius && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Blast radius</span>
            <span style={{ color: "var(--text-2)" }}>{ev.blast_radius.files} files · {ev.blast_radius.tier}</span>
          </div>
        )}
        {(ev.provider || ev.model) && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Model</span>
            <span className="mono" style={{ color: "var(--text-2)" }}>{[ev.provider, ev.model].filter(Boolean).join(" / ")}</span>
          </div>
        )}
        {ev.routing_meta && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Routed</span>
            <span className="mono" style={{ color: "var(--text-2)" }}>
              {ev.routing_meta.tier_form ?? "?"} → {ev.routing_meta.resolved_model ?? ev.model ?? "?"}
            </span>
            {ev.routing_meta.resolution_source && (
              <span style={{ color: "var(--text-muted)", marginLeft: 6, fontSize: 11 }}>
                via {ev.routing_meta.resolution_source.replace(/_/g, " ")}
              </span>
            )}
          </div>
        )}
        {ev.rule_id && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Rule</span>
            <span className="mono" style={{ color: "var(--err)" }}>{ev.rule_id}</span>
          </div>
        )}
        {(ev.hostname || ev.hook_session_id) && (
          <div style={{ gridColumn: "1 / -1" }}>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Session</span>
            <span className="mono" style={{ color: "var(--text-2)" }}>
              {ev.hostname && <>{ev.hostname} · </>}{ev.hook_session_id ?? ev.session_id ?? "—"}
            </span>
          </div>
        )}
      </div>
    )}
    </>
  )
}

/** Column header strip — same widths/labels as the rows, with optional compact mode. */
export function ActivityHeader({ compact = false }: { compact?: boolean }) {
  const cols = compact
    ? "0.8fr 1.4fr 1.2fr 1.8fr 0.9fr 0.8fr"
    : "0.8fr 1.4fr 1fr 1.2fr 1.8fr 0.9fr 0.8fr 0.9fr"
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: cols,
      gap: 12,
      padding: "10px 18px",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface-2)",
      fontSize: 10,
      fontWeight: 600,
      letterSpacing: ".06em",
      textTransform: "uppercase",
      color: "var(--text-muted)",
    }}>
      <div>Time</div>
      <div>Actor</div>
      {!compact && <div>Tool</div>}
      <div>Action</div>
      <div>Input</div>
      <div>Decision</div>
      <div>Rule</div>
      {!compact && <div>Blast</div>}
    </div>
  )
}
