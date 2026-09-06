/**
 * Widget catalog for the report-builder skill (#1450 PR 2).
 *
 * ponytail: hardcoded, mirrors what the backend tools export with
 * (`widget`, `hint:<kind>`) tags. When the catalog grows past manual
 * maintenance, expose a `/tools?tag=widget` endpoint and generate this
 * from the response.
 */
export type WidgetHint = "kpi_card" | "spark" | "list" | "table" | "agent_row"

export interface WidgetDef {
  tool_name: string
  hint: WidgetHint
  label: string
  description: string
  group: "dashboard" | "observability"
}

export const WIDGETS: readonly WidgetDef[] = [
  // dashboard KPIs
  {
    tool_name: "get_dashboard_outcomes",
    hint: "kpi_card",
    label: "Outcomes",
    description: "PRs, issues, reviews, incidents + succeeded/failed counts.",
    group: "dashboard",
  },
  {
    tool_name: "list_attention_runs",
    hint: "list",
    label: "Needs Attention",
    description: "Failed, paused, or cancelled runs — newest first.",
    group: "dashboard",
  },
  {
    tool_name: "list_agent_health",
    hint: "agent_row",
    label: "Agent Health",
    description: "Per-agent run count, success rate, last-run status.",
    group: "dashboard",
  },
  {
    tool_name: "get_dashboard_token_usage",
    hint: "spark",
    label: "Token Usage",
    description: "Token totals + per-agent breakdown + estimated cost.",
    group: "dashboard",
  },
  {
    tool_name: "get_top_policy_hits",
    hint: "table",
    label: "Top Policy Hits",
    description: "Guard policy hit leaderboard — blocked-only rule_id counts.",
    group: "dashboard",
  },
  // observability KPIs
  {
    tool_name: "get_observability_health",
    hint: "kpi_card",
    label: "System Health",
    description: "Recent runs, error rate, latency snapshot.",
    group: "observability",
  },
  {
    tool_name: "get_dora_metrics",
    hint: "kpi_card",
    label: "DORA Metrics",
    description: "Deployment frequency, lead time, MTTR, change-fail rate.",
    group: "observability",
  },
  {
    tool_name: "get_analytics_summary",
    hint: "spark",
    label: "Analytics Summary",
    description: "Rolling counts + trend sparks.",
    group: "observability",
  },
  {
    tool_name: "list_agent_status",
    hint: "list",
    label: "Agent Status",
    description: "Per-agent current status + recent activity.",
    group: "observability",
  },
  {
    tool_name: "get_playbook_scorecards",
    hint: "table",
    label: "Playbook Scorecards",
    description: "Per-playbook success rate + volume + recent failures.",
    group: "observability",
  },
] as const

const _BY_NAME: Record<string, WidgetDef> = Object.fromEntries(
  WIDGETS.map((w) => [w.tool_name, w])
)

export function widgetByName(tool_name: string): WidgetDef | undefined {
  return _BY_NAME[tool_name]
}

/** CSS Grid col/row span per hint. Grid uses `grid-auto-flow: dense`. */
export const HINT_SIZES: Record<WidgetHint, { col: number; row: number }> = {
  kpi_card:  { col: 3,  row: 1 },
  spark:     { col: 3,  row: 2 },
  list:      { col: 4,  row: 3 },
  table:     { col: 6,  row: 3 },
  agent_row: { col: 12, row: 1 },
}
