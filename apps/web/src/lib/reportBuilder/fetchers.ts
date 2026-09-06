/**
 * Widget data fetchers for the report-builder skill (#1450 PR 3).
 *
 * Each of the 10 widgets maps to an existing REST endpoint that already
 * powers /dashboard and /observability. This layer:
 *   - dedupes calls when multiple widgets share an endpoint (five
 *     dashboard KPIs all read from GET /dashboard — one fetch, five reads)
 *   - shapes each response into a `WidgetData` union the renderer can
 *     switch on without re-shaping per widget
 *
 * ponytail: no swr/react-query, no cache invalidation. The
 * `useReportData` hook re-fetches on layout change and mount, which is
 * all we need for a page that has no live updates.
 */
import { useEffect, useMemo, useState } from "react"

import { API } from "../api/client"
import type { AuthFetch } from "../api/client"
import type { WidgetSpec } from "./api"

// ── Response shapes (subset of DashboardOut / analytics endpoints) ──────────

export interface OutcomeStats {
  prs_opened: number
  issues_triaged: number
  reviews_completed: number
  incidents_investigated: number
  successful_automations: number
  failed_automations: number
}

export interface AttentionRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  trigger_summary: string | null
  created_at: string
}

export interface AgentHealth {
  workflow_id: string
  name: string
  playbook_slug: string | null
  run_count: number
  succeeded_count: number
  failed_count: number
  success_rate: number
  last_run_status: string | null
  last_run_at: string | null
}

export interface TokenUsage {
  total_input_tokens: number
  total_output_tokens: number
  estimated_cost_usd: number
  per_agent?: { name: string; input_tokens: number; output_tokens: number; cost_usd: number }[]
}

export interface PolicyHit {
  rule_id: string
  count: number
}

export interface DashboardResp {
  outcomes: OutcomeStats
  needs_attention: AttentionRun[]
  agent_health: AgentHealth[]
  token_usage: TokenUsage
  guard_snapshot: { top_policy_hits?: PolicyHit[] }
}

export interface ObservabilityHealth {
  runs_last_hour: number
  runs_last_24h: number
  error_rate: number
  p95_latency_ms: number | null
}

export interface DoraStat {
  deployment_frequency: number
  lead_time_hours: number | null
  mttr_hours: number | null
  change_failure_rate: number
}

export interface AnalyticsSummary {
  window_days: number
  total_runs: number
  succeeded: number
  failed: number
  success_rate: number
  total_cost_usd: number
}

export interface AgentStatus {
  name: string
  status: string
  last_run_at: string | null
  run_count_24h: number
}

export interface PlaybookScorecard {
  playbook_slug: string
  run_count: number
  succeeded: number
  failed: number
  success_rate: number
  avg_cost_usd: number | null
}

// ── Widget data union ──────────────────────────────────────────────────────

export type WidgetData =
  | { tool: "get_dashboard_outcomes";    data: OutcomeStats }
  | { tool: "list_attention_runs";       data: AttentionRun[] }
  | { tool: "list_agent_health";         data: AgentHealth[] }
  | { tool: "get_dashboard_token_usage"; data: TokenUsage }
  | { tool: "get_top_policy_hits";       data: PolicyHit[] }
  | { tool: "get_observability_health";  data: ObservabilityHealth }
  | { tool: "get_dora_metrics";          data: DoraStat }
  | { tool: "get_analytics_summary";     data: AnalyticsSummary }
  | { tool: "list_agent_status";         data: AgentStatus[] }
  | { tool: "get_playbook_scorecards";   data: PlaybookScorecard[] }

// ── Endpoint map (source of the dedup) ─────────────────────────────────────

const DASHBOARD_TOOLS = new Set([
  "get_dashboard_outcomes",
  "list_attention_runs",
  "list_agent_health",
  "get_dashboard_token_usage",
  "get_top_policy_hits",
])

async function fetchJson<T>(f: AuthFetch, url: string): Promise<T> {
  const res = await f(url)
  if (!res.ok) throw new Error(`${url}: ${res.status}`)
  return res.json() as Promise<T>
}

function shapeFromDashboard(tool: string, dash: DashboardResp): WidgetData {
  switch (tool) {
    case "get_dashboard_outcomes":
      return { tool: "get_dashboard_outcomes", data: dash.outcomes }
    case "list_attention_runs":
      return { tool: "list_attention_runs", data: (dash.needs_attention || []).slice(0, 5) }
    case "list_agent_health":
      return { tool: "list_agent_health", data: dash.agent_health || [] }
    case "get_dashboard_token_usage":
      return { tool: "get_dashboard_token_usage", data: dash.token_usage }
    case "get_top_policy_hits":
      return {
        tool: "get_top_policy_hits",
        data: (dash.guard_snapshot?.top_policy_hits || []).slice(0, 10),
      }
  }
  throw new Error(`unknown dashboard tool: ${tool}`)
}

async function fetchNonDashboard(
  f: AuthFetch,
  tool: string,
): Promise<WidgetData> {
  switch (tool) {
    case "get_observability_health":
      return {
        tool: "get_observability_health",
        data: await fetchJson<ObservabilityHealth>(f, `${API}/observability/summary`),
      }
    case "get_dora_metrics":
      return {
        tool: "get_dora_metrics",
        data: await fetchJson<DoraStat>(f, `${API}/analytics/dora`),
      }
    case "get_analytics_summary":
      return {
        tool: "get_analytics_summary",
        data: await fetchJson<AnalyticsSummary>(f, `${API}/analytics/summary`),
      }
    case "list_agent_status":
      return {
        tool: "list_agent_status",
        data: await fetchJson<AgentStatus[]>(f, `${API}/observability/agents`),
      }
    case "get_playbook_scorecards":
      return {
        tool: "get_playbook_scorecards",
        data: await fetchJson<PlaybookScorecard[]>(f, `${API}/analytics/scorecards`),
      }
  }
  throw new Error(`unknown tool: ${tool}`)
}

// ── React hook ─────────────────────────────────────────────────────────────

export type WidgetLoadState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ok"; data: WidgetData }

export function useReportData(
  authFetch: AuthFetch,
  workspaceId: string | null,
  layout: WidgetSpec[],
): Map<string, WidgetLoadState> {
  const [byTool, setByTool] = useState<Map<string, WidgetLoadState>>(new Map())

  const toolNames = useMemo(() => layout.map((w) => w.tool_name), [layout])
  const key = toolNames.join(",")

  useEffect(() => {
    if (!workspaceId || toolNames.length === 0) {
      setByTool(new Map())
      return
    }

    let cancelled = false
    const next = new Map<string, WidgetLoadState>()
    for (const t of toolNames) next.set(t, { status: "loading" })
    setByTool(new Map(next))

    const needsDashboard = toolNames.some((t) => DASHBOARD_TOOLS.has(t))
    const others = Array.from(new Set(toolNames.filter((t) => !DASHBOARD_TOOLS.has(t))))

    const dashboardPromise = needsDashboard
      ? fetchJson<DashboardResp>(authFetch, `${API}/dashboard`)
      : Promise.resolve<DashboardResp | null>(null)

    dashboardPromise
      .then((dash) => {
        if (cancelled) return
        if (dash) {
          for (const t of toolNames) {
            if (!DASHBOARD_TOOLS.has(t)) continue
            try {
              next.set(t, { status: "ok", data: shapeFromDashboard(t, dash) })
            } catch (e) {
              next.set(t, { status: "error", error: String((e as Error).message) })
            }
          }
          setByTool(new Map(next))
        }
      })
      .catch((e) => {
        if (cancelled) return
        for (const t of toolNames) {
          if (DASHBOARD_TOOLS.has(t)) {
            next.set(t, { status: "error", error: String((e as Error).message) })
          }
        }
        setByTool(new Map(next))
      })

    for (const t of others) {
      fetchNonDashboard(authFetch, t)
        .then((wd) => {
          if (cancelled) return
          next.set(t, { status: "ok", data: wd })
          setByTool(new Map(next))
        })
        .catch((e) => {
          if (cancelled) return
          next.set(t, { status: "error", error: String((e as Error).message) })
          setByTool(new Map(next))
        })
    }

    return () => {
      cancelled = true
    }
    // key is the dependency signal — re-fetch when layout changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, workspaceId])

  return byTool
}
