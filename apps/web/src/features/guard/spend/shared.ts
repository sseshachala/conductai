// Shared types + formatters for /theguard/spend and /theguard/spend/glance.
// Both surfaces render the same currency amounts, month labels, and tool
// coverage names — keep the mapping in one place so a rename doesn't have
// to touch two pages.

export type Currency = "USD" | "EUR" | "INR"

export const CURRENCY_SYMBOLS: Record<Currency, string> = {
  USD: "$",
  EUR: "€",
  INR: "₹",
}
export const CURRENCY_RATES: Record<Currency, number> = {
  USD: 1,
  EUR: 0.92,
  INR: 83.5,
}

export function fromUsd(amount: number, currency: Currency): number {
  return amount * CURRENCY_RATES[currency]
}
export function toUsd(amount: number, currency: Currency): number {
  return amount / CURRENCY_RATES[currency]
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

export const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const

export function formatMonthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number)
  return `${MONTHS[m - 1]} ${y}`
}

export const TOOL_LABELS: Record<string, string> = {
  "claude-code":    "Claude Code",
  "claude_code":    "Claude Code",
  "claude_chat":    "Claude.ai",
  "claude-chat":    "Claude.ai",
  "claude_desktop": "Claude Desktop",
  "claude-desktop": "Claude Desktop",
  "claude_work":    "Claude Work",
  "claude-work":    "Claude Work",
  "codex":          "Codex",
  "codex_cli":      "Codex CLI",
  "codex_chat":     "Codex Chat",
  "cursor":         "Cursor",
  "windsurf":       "Windsurf",
  "copilot":        "Copilot",
  "gemini":         "Gemini",
  "vscode":         "VS Code",
  "unknown":        "Claude.ai",
}

// API response shapes.

export interface DeveloperSpend {
  email: string
  sessions: number
  hook_sessions: number
  tokens_after: number
  cost_usd: number
  saved_usd: number
  detected_tools: string[]
  mcp_registered: string[]
  hook_registered: string[]
}

export interface AiToolBreakdown {
  ai_tool: string
  tokens_after: number
  cost_usd: number
  tokens_saved: number
  cost_saved: number
}

export interface ModelBreakdown {
  provider: string
  model: string
  tokens_after: number
  cost_usd: number
}

export interface ProviderBreakdown {
  provider: string
  tokens_after: number
  cost_usd: number
}

export interface SpendData {
  team_id: string
  period: string
  total_tokens_before: number
  total_tokens_after: number
  total_saved_pct: number
  total_cost_usd: number
  total_saved_usd: number
  sessions: number
  hook_sessions: number
  by_developer: DeveloperSpend[]
  by_ai_tool: AiToolBreakdown[]
  by_model?: ModelBreakdown[]
  by_provider?: ProviderBreakdown[]
}

export interface TeamBudgetSettings {
  team_monthly_limit_usd: number | null
  alert_threshold_pct: number
  hard_cap_enabled: boolean
  default_per_developer_usd: number | null
}

// AI tools you can scope a per-tool budget to. Single source of truth lives
// in config/ai_tools.json — the API asserts at import time that every key
// there has matching pricing in TOOL_PRICING (events.py).
// Add a new tool: append it to config/ai_tools.json, add pricing in events.py.
import aiToolsConfig from "@config/ai_tools.json"
export const AI_TOOL_OPTIONS: readonly string[] = aiToolsConfig.tools

// Transports are server-stamped surface identifiers ('gateway', 'mcp', ...).
// A budget scoped to a transport caps aggregate spend that arrived via that
// surface regardless of which client tool called it. Source of truth lives
// in config/transports.json.
import transportsConfig from "@config/transports.json"
export const TRANSPORT_OPTIONS: readonly string[] = transportsConfig.transports

export interface ToolCap {
  id: string
  ai_tool: string
  monthly_limit_usd: number
  hard_limit_usd: number | null
  current_month_cost_usd: number
}
