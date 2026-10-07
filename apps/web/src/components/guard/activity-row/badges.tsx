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
      title="Routed through Conduct Guard Gateway"
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
      via gateway
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
