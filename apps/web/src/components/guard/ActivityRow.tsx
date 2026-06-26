"use client"

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
  source?: "hook" | "proxy" | "mcp" | null
  provider?: string | null         // 'anthropic' | 'openai' | 'perplexity' (proxy only)
  model?: string | null            // vendor model id (proxy only)
  conductai_run_id?: string | null
  blast_radius?: { files: number; symbols?: number; tier: string } | null
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

export function DecisionBadge({ decision }: { decision: string }) {
  // Consistent palette across the app (matches Guard policy badges):
  //   blocked → red    (var(--err))
  //   warned  → yellow (var(--warn))
  //   audited → blue   (var(--info))  — recorded only, no action
  //   allowed → green  (var(--ok))    — explicit pass
  const cls =
    decision === "allowed"   ? "sbadge ok"
    : decision === "audited" ? "sbadge info"
    : decision === "blocked" ? "sbadge err"
    : decision === "warned"  ? "sbadge warn"
    : decision === "approval"? "sbadge warn"
    :                          "sbadge warn"
  return (
    <span className={cls} style={{ textTransform: "capitalize" }}>{decision}</span>
  )
}

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

export function ActivityRow({ ev, compact = false, isLast = false }: {
  ev: AuditEvent
  compact?: boolean
  isLast?: boolean
}) {
  // Same grid layout the full /guard/activity page uses. The compact variant
  // drops Tool and Blast Radius columns for the dashboard preview, but keeps
  // every cell aligned to the same axis so width stays consistent.
  const cols = compact
    ? "0.8fr 1.4fr 0.7fr 1.8fr 0.9fr 0.8fr"      // time · dev · call · input · decision · rule
    : "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr 0.9fr"  // + tool, + blast radius

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: cols,
      gap: 12,
      padding: "11px 18px",
      borderBottom: isLast ? "none" : "1px solid var(--border)",
      alignItems: "center",
      background: ev.decision === "blocked" ? "var(--err-bg)" : "transparent",
    }}>
      <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{formatTs(ev.ts)}</div>
      <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {ev.user_email ?? "—"}
      </div>
      {!compact && (
        <div><ToolBadge tool={ev.ai_tool} /></div>
      )}
      <div className="mono" style={{ fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
        {ev.source === "proxy" && ev.provider
          ? `${ev.provider}/${ev.model ?? "?"}`
          : ev.tool_call}
        {ev.source === "proxy" && <ProxyPill />}
      </div>
      <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {ev.input_summary ? `${ev.input_summary}…` : "—"}
      </div>
      <div>
        {ev.conductai_run_id ? (
          <Link href={`/runs/${ev.conductai_run_id}`} style={{ display: "inline-flex", alignItems: "center", gap: 3, textDecoration: "none" }}>
            <DecisionBadge decision={ev.decision} />
            <span style={{ fontSize: 11, color: "var(--accent-text)" }}>→</span>
          </Link>
        ) : (
          <DecisionBadge decision={ev.decision} />
        )}
      </div>
      <div className="mono" style={{ fontSize: 11.5, color: ev.rule_id ? "var(--err)" : "var(--text-muted)" }}>
        {ev.rule_id ?? "—"}
      </div>
      {!compact && (
        <div>
          {ev.blast_radius ? (
            <BlastRadiusBadge br={ev.blast_radius} />
          ) : (
            <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>—</span>
          )}
        </div>
      )}
    </div>
  )
}

/** Column header strip — same widths/labels as the rows, with optional compact mode. */
export function ActivityHeader({ compact = false }: { compact?: boolean }) {
  const cols = compact
    ? "0.8fr 1.4fr 0.7fr 1.8fr 0.9fr 0.8fr"
    : "0.8fr 1.4fr 1fr 0.7fr 1.8fr 0.9fr 0.8fr 0.9fr"
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
      <div>Developer</div>
      {!compact && <div>Tool</div>}
      <div>Call</div>
      <div>Input</div>
      <div>Decision</div>
      <div>Rule</div>
      {!compact && <div>Blast</div>}
    </div>
  )
}
