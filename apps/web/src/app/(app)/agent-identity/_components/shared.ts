export type Tab = "tokens" | "run_tokens" | "identities" | "agent_sessions" | "lens_sessions" | "rate_limits" | "integrations" | "delegation"
export const TAB_LABELS: Record<Tab, string> = {
  tokens: "Tokens",
  run_tokens: "Run tokens",
  identities: "Identities",
  agent_sessions: "Agent sessions",
  lens_sessions: "Lens sessions",
  rate_limits: "Rate limits",
  integrations: "Integrations",
  delegation: "Delegation",
}
export const TABS: Tab[] = ["tokens", "run_tokens", "identities", "agent_sessions", "lens_sessions", "rate_limits", "integrations", "delegation"]

export interface RunToken {
  id: string
  run_id: string
  token_prefix: string | null
  workflow_id: string | null
  workflow_name: string | null
  created_at: string | null
  first_used_at: string | null
  invalidated_at: string | null
}

export interface ApiToken {
  id: string
  token_name: string | null
  token_prefix: string | null
  token_type: string
  expires_at: string | null
  last_used_at: string | null
  created_at: string | null
}

export interface Identity {
  recorded_session_count?: number
  last_activity_at?: string | null
  id: string
  name: string
  provider: string
  token_prefix: string
  created_at: string
  last_used_at: string | null
  environment_id: string | null
  source: string | null
  source_id: string | null
  platform_of_origin: string | null
  owner_user_id: string | null
  agent_role_id: string | null
  lifecycle_state: string | null
  last_certified_at: string | null
  certification_cadence_days: number | null
  risk_tier: string | null
  deactivated_at: string | null
  // expires_at is exposed by the API after backend PR normalizes sources.
  // Older responses omit it — treat as null.
  expires_at?: string | null
}

export type IdentityKind = "trial" | "auto" | "human"

// Classify by explicit source first (backend PR 1 normalizes these), then
// fall back to name-pattern heuristics for legacy rows that pre-date the
// backfill migration.
export function classifyIdentity(id: Identity): IdentityKind {
  switch (id.source) {
    case "conduct_trial": return "trial"
    case "conduct_cli":
    case "conduct_auto": return "auto"
    case "okta_jwt":
    case "okta":
    case "conduct_api": return "human"
  }
  // Legacy fallbacks.
  if (id.name === "Trial (7 days)") return "trial"
  if (id.name.includes("(CLI)")) return "auto"
  if (id.name.includes("(auto)")) return "auto"
  return "human"
}

export function trialCountdown(expiresAt: string): { label: string; expired: boolean } {
  const diffMs = new Date(expiresAt).getTime() - Date.now()
  if (diffMs <= 0) return { label: "expired", expired: true }
  const days  = Math.floor(diffMs / 86_400_000)
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000)
  return { label: days > 0 ? `${days}d ${hours}h left` : `${hours}h left`, expired: false }
}

export const KIND_SECTIONS: readonly { id: IdentityKind; label: string; description: string }[] = [
  { id: "trial", label: "Time-limited",      description: "Trials and short-lived tokens — expire automatically." },
  { id: "auto",  label: "Auto-provisioned",  description: "Machine-issued identities from CLI login, guard join, and other flows." },
  { id: "human", label: "Human",             description: "Real users signed in via Clerk or imported via Okta." },
]

export interface LensSession {
  id: string
  title: string
  created_at: string
  updated_at: string
  token_revoked_at: string | null
  is_active: boolean
  is_idle: boolean
  turns: number
  spend_usd: number
  agent_identity_id: string | null
  agent_identity_name: string | null
  agent_identity_token_prefix: string | null
}

export const TIER_STYLE: Record<string, { bg: string; fg: string }> = {
  tier_1: { bg: "#dcfce7", fg: "#166534" },
  tier_2: { bg: "#fef3c7", fg: "#92400e" },
  tier_3: { bg: "#fee2e2", fg: "#991b1b" },
}

export const LIFECYCLE_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  active:         { bg: "#dcfce7", fg: "#166534", label: "Active" },
  pending_review: { bg: "#fef3c7", fg: "#92400e", label: "Pending review" },
  deactivated:    { bg: "#f3f4f6", fg: "#4b5563", label: "Deactivated" },
  expired:        { bg: "#fee2e2", fg: "#991b1b", label: "Expired" },
}
