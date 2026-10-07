import type { FederationAttribution } from "@/components/federation/AttributionDetails"
import type { SessionUsageEvidence } from "../SessionUsageDetails"

export interface AuditEvent {
  federation?: FederationAttribution | null
  id: string
  ts: string
  user_email: string | null
  ai_tool: string
  tool_call: string | null
  input_summary: string | null
  decision: string                // "allowed" | "blocked" | "warned" | "approval" | "audited"
  rule_id: string | null
  source?: "hook" | "proxy" | "gateway" | "mcp" | "local_audit" | "brain_block" | null
  provider?: string | null         // 'anthropic' | 'openai' | 'perplexity' (proxy only)
  model?: string | null            // vendor model id (proxy only)
  conductai_run_id?: string | null
  conductai_workflow?: string | null
  conductai_workflow_id?: string | null
  goal_id?: string | null
  goal_name?: string | null
  blast_radius?: { files: number; symbols?: number; tier: string } | null
  hostname?: string | null
  hook_session_id?: string | null
  session_id?: string | null
  agent_identity_id?: string | null
  entry_hash?: string | null
  policy_hash?: string | null
  // #1150 phase 2 — layered verdict envelope
  evaluated_rules?: Array<{ rule_id: string | null; severity?: string; action?: string }> | null
  defense_score?: number | null
  routing_meta?: {
    gateway_profile_id?: string | null
    gateway_profile?: string | null
    session_usage?: SessionUsageEvidence
    tier_form?: string | null
    resolved_model?: string | null
    endpoint_provider?: string | null
    reason?: string | null
    resolution_source?: string | null
  } | null
  execution_status?: "success" | "error" | "timeout" | null
  result_summary?: string | null
  // Added by #1959 Phase 3 — durable-audit lifecycle fields projected by
  // GET /guard/events. All optional so legacy single-phase rows stay
  // valid; nullish values render as em dash in the Lifecycle column.
  lifecycle_state?: "accepted" | "finalized" | "orphaned" | "expired" | null
  accepted_at?: string | null
  finalized_at?: string | null
  lease_expires_at?: string | null
  request_id?: string | null
  // Server names them tokens_before / tokens_after (input / output).
  // See _event_to_dict in apps/api/app/modules/guard/routers/events.py.
  tokens_before?: number | null
  tokens_after?: number | null
}
