// ─── Gateway Profile v2 (#2001/#2003) ───────────────────────────────

export interface GatewayProfileAgentRateCap {
  agent_identity_id: string
  rpm: number | null
  tpm: number | null
}

export interface GatewayProfileRateLimitsInput {
  rpm: number | null
  tpm: number | null
  agent_limits?: GatewayProfileAgentRateCap[]
}

export interface GatewayProfileRateLimits extends GatewayProfileRateLimitsInput {
  agent_limits: GatewayProfileAgentRateCap[]
  available_agents: Array<{ id: string; name: string }>
}

export type GatewayProfileV2Operation =
  | "anthropic_messages"
  | "anthropic_count_tokens"
  | "openai_chat_completions"
  | "openai_responses"

export type GatewayProfileV2Target =
  | {
      id: string
      transport: "native_http"
      provider: string
      model: string
      credential_ref: string
      provider_options?: Record<string, unknown>
    }
  | {
      id: string
      transport: "litellm_sdk"
      provider: string
      model: string
      credential_ref: string
      provider_options?: Record<string, unknown>
    }
  | {
      id: string
      transport: "http_passthrough"
      integration: string
      model: string
      credential_ref: string
      endpoint?: string | null
      provider_options?: Record<string, unknown>
    }

export interface GatewayProfileV2WorkingCopy {
  name: string
  model_alias: string
  accepts: GatewayProfileV2Operation[]
  timeout_seconds?: number
  max_attempts?: number
  targets: GatewayProfileV2Target[]
}

export interface GatewayProfileV2Revision {
  id: string
  version: number
  published_by: string
  published_at: string
}

export interface GatewayProfileV2Out {
  id: string
  workspace_id: string
  name: string
  model_alias: string | null
  /** Server-generated 8-char alphanumeric. Immutable. Forms the
   *  client-facing routing key `cond-<code>-<alias>`. */
  cond_code: string
  /** NULL for drafts; points at the currently-served revision when
   *  published. Working_copy is API-locked whenever this is non-null. */
  active_revision_id: string | null
  working_copy: Record<string, unknown> | null
  revisions: GatewayProfileV2Revision[]
  created_at: string
  updated_at: string
}

/**
 * Response shape for the ``/import`` endpoint. Mirrors backend
 * ``ImportProfileOut``. ``credential_gaps`` lists every target that
 * needs a vault + credential handle pick post-import (the editor's
 * Save gate then blocks Save until they're filled).
 */
export interface GatewayProfileV2ImportGap {
  target_index: number
  target_id: string
  transport: string
  reason: string
}

export interface GatewayProfileV2ImportOut {
  profile: GatewayProfileV2Out
  credential_gaps: GatewayProfileV2ImportGap[]
  next_url: string
}

export type GuardPolicyAction = "block" | "approval" | "warn" | "audit"

export interface GuardPolicy {
  id: string
  workspace_id: string
  rule_id: string
  description: string | null
  match_tool: string | null
  match_pattern: string | null
  match_path_pattern: string | null
  action: GuardPolicyAction
  inject_guidance: boolean
  guidance: string | null
  message: string | null
  enabled: boolean
  builtin: boolean
  pack_id: string | null
  // Legacy value ``proxy`` stays accepted on read; new writes use ``gateway``.
  persona: "agent" | "proxy" | "gateway"
  non_overridable: boolean
  persona_affinity: string[]
  gates?: string[]  // #1733/#1750 Phase B — locked enum [action, prompt, response]
  // #1755 Slice 2 — derived per-PEP surface status from rule.gates × PEP_CAPABILITIES.
  // Values: "hard" | "not_supported" (locked; deploy-caveat statuses stay hand-authored).
  derived_mcp?: string
  derived_proxy?: string
  derived_runtime?: string
  derived_hook?: string
  guarantee?: string | null  // #1750 Phase B — hand-authored trust prose
  known_limitations?: string[]  // #1750 Phase B — hand-authored operational caveats
  tag: string | null
  exception_reason: string | null
  exception_expires_at: string | null
  exception_active: boolean
  exception_expired: boolean
  last_triggered: string | null
  created_at: string
  updated_at: string
}

export interface GuardPolicyPatch {
  enabled?: boolean
  description?: string
  match_pattern?: string
  match_path_pattern?: string
  action?: GuardPolicyAction
  inject_guidance?: boolean
  guidance?: string
  message?: string
  reason?: string
  expires_at?: string
}

// #1755 Slice 2 — redacted rule-firing shape for the Policies UI panel.
// Raw input_summary NEVER lands here (Property 9); only the redacted preview,
// a sha256 prefix, and byte size for dedupe/volume signal.
export interface RuleFire {
  id: string
  ts: string
  rule_id: string | null
  decision: string
  tool_call: string | null
  source: string
  ai_tool: string
  input_summary_redacted: string | null
  input_hash_prefix: string | null
  input_size_bytes: number
}

export type EnforcementStatus = "hard" | "conditional" | "advisory" | "not_supported"

export interface GuardEnforcementCoverage {
  rule_id: string
  name: string
  pack: string | null
  pack_version: string | null
  builtin: boolean
  personas: string[]
  action: string
  base_action: string
  enabled: boolean
  proxy: EnforcementStatus
  hook: EnforcementStatus
  mcp: EnforcementStatus
  runtime: EnforcementStatus
  // #1755 Slice 2 (real PR 5) — derived counterparts for divergence UI.
  // Locked to "hard" | "not_supported" today; expands when derive_surface_status
  // learns to model deploy-caveat statuses.
  derived_proxy?: string
  derived_hook?: string
  derived_mcp?: string
  derived_runtime?: string
  guarantee: string
  requires: string[]
  known_limitations: string[]
  enforcement_version: 1
  exception_reason: string | null
  exception_expires_at: string | null
  exception_active: boolean
  exception_expired: boolean
}

export type NotificationAction = "block" | "warn" | "audit" | "approval" | "fail_open" | "drift"
export type NotificationChannelType = "slack" | "email" | "pagerduty" | "webhook"

export interface NotificationChannel {
  id: string
  action: NotificationAction
  channel_type: NotificationChannelType
  integration_id: string | null
  channel_ref: string
  enabled: boolean
  dedupe_window_sec: number
  created_at: string
}

export interface NotificationGroup {
  action: NotificationAction
  channels: NotificationChannel[]
}

export interface NotificationList {
  workspace_id: string
  groups: NotificationGroup[]
}
