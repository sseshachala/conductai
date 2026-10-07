export interface OutcomeStats {
  prs_opened: number
  issues_triaged: number
  reviews_completed: number
  incidents_investigated: number
  successful_automations: number
  failed_automations: number
  // optional prev-period deltas from API
  prev_prs_opened?: number
  prev_issues_triaged?: number
  prev_reviews_completed?: number
  prev_incidents_investigated?: number
  prev_successful_automations?: number
  prev_failed_automations?: number
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

export interface AttentionRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  trigger_summary: string | null
  created_at: string
  repo: string | null
}

export interface RecentRun {
  run_id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  started_at: string | null
  created_at: string
  repo: string | null
}

export interface AgentTokenUsage {
  workflow_id: string
  name: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost_usd: number
}

export interface TokenUsage {
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  estimated_cost_usd: number
  by_agent: AgentTokenUsage[]
}

export interface PolicyHit {
  policy_name: string
  count: number
  severity?: string
}

export interface DeveloperSpend {
  name: string
  spent_usd: number
  limit_usd: number | null
}

export interface GuardSnapshot {
  policy_blocks_today?: number
  top_policy_hits?: PolicyHit[]
  developer_near_limit?: DeveloperSpend[]
}

export interface DashboardData {
  outcomes: OutcomeStats
  needs_attention: AttentionRun[]
  agent_health: AgentHealth[]
  recent_activity: RecentRun[]
  token_usage: TokenUsage
  guard_blocks_today: number
  guard_snapshot?: GuardSnapshot
}
