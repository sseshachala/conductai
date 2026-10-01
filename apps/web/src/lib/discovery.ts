import { toolCatalog } from "./toolCatalog"

export interface DiscoveryAgent {
  id: string
  framework: string | null
  device_id: string | null
  installation_id: string | null
  detection: string
  freshness: string
  hooks_status: string
  gateway_status: string
  gateway_checked_at?: string | null
  gateway_remediation?: { label: string; command: string; detail: string }
  last_seen_at: string | null
  hook_observed_at: string | null
  hook_event_id: string | null
  mcp_configured: boolean
  evidence: { signals?: string[]; config_unreadable?: boolean; mcp_servers?: McpFinding[] }
  evidence_note: string
  remediation: { label: string; command: string | null; detail: string }
}

export interface McpFinding {
  id: string
  name: string
  scope: "user" | "legacy-user" | "project"
  transport: "stdio" | "http" | "sse" | "streamable-http" | "unknown"
  disabled: boolean
}

export interface DiscoverySummary {
  total: number
  confirmed: number
  possible_integrations: number
  recent_hook_evidence: number
  needs_attention: number
  stale: number
  legacy_unverified: number
}

export function discoveryLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    ...Object.fromEntries(toolCatalog.map(tool => [tool.id, tool.label])),
    possible_integration: "Possible integration",
    legacy_unverified: "Legacy / unverified", installed: "Installed", running: "Running at scan",
    observed: "Activity observed", configured: "Configured", unverified: "Unverified",
    fresh: "Recent scan", stale: "Stale scan", tool_installation: "Tool installation",
    connection_verified: "Connection verified", authentication_failed: "Authentication failed", unavailable: "Check unavailable",
    running_executable: "Running executable", dependency_manifest: "Dependency manifest",
  }
  return value ? labels[value] ?? value : "Not recorded"
}

export function discoveryTime(value: string | null | undefined): string {
  if (!value) return "Not recorded"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
  }) + " UTC"
}
