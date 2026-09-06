/**
 * Starter templates for the report-builder skill (#1450 PR 2).
 *
 * Static registry. "Use template" copies the widget list into a new
 * `workspace_report_layouts` row — from that point on it's a normal
 * user-editable layout, no template link retained.
 */
import type { WidgetHint } from "./widgets"

export interface ReportTemplate {
  slug: string
  name: string
  description: string
  widgets: readonly { tool_name: string; hint: WidgetHint }[]
}

export const TEMPLATES: readonly ReportTemplate[] = [
  {
    slug: "operations",
    name: "Operations",
    description: "Day-to-day agent output — outcomes, attention, health, token usage, policy hits.",
    widgets: [
      { tool_name: "get_dashboard_outcomes",    hint: "kpi_card" },
      { tool_name: "list_attention_runs",       hint: "list" },
      { tool_name: "list_agent_health",         hint: "agent_row" },
      { tool_name: "get_dashboard_token_usage", hint: "spark" },
      { tool_name: "get_top_policy_hits",       hint: "table" },
    ],
  },
  {
    slug: "observability",
    name: "Observability",
    description: "Platform health — DORA, analytics, agent status, playbook scorecards.",
    widgets: [
      { tool_name: "get_observability_health",  hint: "kpi_card" },
      { tool_name: "get_dora_metrics",          hint: "kpi_card" },
      { tool_name: "get_analytics_summary",     hint: "spark" },
      { tool_name: "list_agent_status",         hint: "list" },
      { tool_name: "get_playbook_scorecards",   hint: "table" },
    ],
  },
] as const

export function templateBySlug(slug: string): ReportTemplate | undefined {
  return TEMPLATES.find((t) => t.slug === slug)
}
