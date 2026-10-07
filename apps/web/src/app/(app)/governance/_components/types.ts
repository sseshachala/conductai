export interface SpendStats {
  active_developers: number
  events_today: number
  blocked_today: number
  tokens_saved_today: number
}

export interface InstalledPacksResponse { installed: string[] }

export interface FrameworkRow {
  framework: string
  rules_count: number
  controls: string[]
  packs: string[]
}

export interface BonusFrameworkRow extends FrameworkRow {
  recommended_pack: string | null
}

export interface FrameworksOut {
  installed: FrameworkRow[]
  bonus: BonusFrameworkRow[]
  total_rules: number
  rules_with_framework: number
}

export interface NarrativeOut {
  paragraph: string
  generated_at: string
  source: "template" | "llm"
}

export interface RuleDrillRow {
  rule_id: string
  description: string | null
  action: string
  severity: string | null
  pack_slug: string
  match_tool: string | null
  match_pattern: string | null
  match_path_pattern: string | null
  recommendation: string | null
  iso_control: string | null
  frameworks: string[]
  events_30d: number
}

export interface ControlDrillOut {
  framework: string
  control: string | null
  rules: RuleDrillRow[]
}

export interface RecentEvent {
  id: string
  ts: string
  decision: string
  rule_id: string | null
  ai_tool: string
  tool_call: string
  user_email: string | null
  input_summary: string | null
}

export interface CertificationOut {
  id: string
  pack_slug: string
  certified_by: string
  policy_version: string | null
  certified_at: string
}

export interface KpiValue {
  value: number
  avg_7d: number | null
  delta_pct: number | null
}

export interface ChainVerifyOut {
  valid: boolean
  events_checked: number
  broken_at: string | null
  first_event: string | null
  last_event: string | null
  verified_at: string
}

export interface KpisOut {
  events_today: KpiValue
  blocked_today: KpiValue
  active_developers_today: KpiValue
  risk_avoided_usd_mtd: number
  blocks_mtd: number
}
