import { API, AuthFetch, del, json, patch, post, put } from "./client"

const base = () => `${API}/guard`

// Mutation helpers that THROW on non-2xx and return the parsed JSON body.
// The base `post`/`put`/`del` in ./client swallow errors — the caller gets
// a raw Response object even for 4xx/5xx, which silently masks server
// rejections. Every Gateway v2 mutation goes through these so the UI
// dialogs see errors and surface them.
async function _mutateJson<T>(
  f: AuthFetch, method: "POST" | "PUT" | "PATCH", url: string, body: unknown,
): Promise<T> {
  const res = await f(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function _mutateVoid(
  f: AuthFetch, method: "DELETE", url: string,
): Promise<void> {
  const res = await f(url, { method })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
}

// ─── Gateway Profile v2 (#2001/#2003) ───────────────────────────────

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
  persona: "agent" | "proxy"
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

export const guard = {
  config: {
    get: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return json<any>(f, `${base()}/config${q}`)
    },
    installed: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return json<any>(f, `${base()}/config/installed${q}`)
    },
    persona: (f: AuthFetch) => json<any>(f, `${base()}/config/persona`),
    patch: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      patch(f, `${base()}/config?workspace_id=${workspaceId}`, body),
    resync: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return post(f, `${base()}/config/resync${q}`, {})
    },
  },

  events: {
    list: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/events${q}`)
    },
    unified: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/events/unified${q}`)
    },
    costTrend: (f: AuthFetch, params: Record<string, string>) =>
      json<any>(f, `${base()}/events/cost-trend?${new URLSearchParams(params)}`),
    auditVerify: (f: AuthFetch, workspaceId: string) =>
      json<any>(f, `${base()}/events/audit/verify?workspace_id=${workspaceId}`),
    streamUrl: () => `${base()}/events/stream`,
    // #1755 Slice 2 — redacted-preview firings for one rule (Policies UI panel).
    ruleFires: (f: AuthFetch, ruleId: string, workspaceId?: string, limit = 20) => {
      const params = new URLSearchParams({ limit: String(limit) })
      if (workspaceId) params.set("workspace_id", workspaceId)
      return json<RuleFire[]>(f, `${base()}/events/rule/${encodeURIComponent(ruleId)}/fires?${params}`)
    },
  },

  policies: {
    list: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return json<GuardPolicy[]>(f, `${base()}/policies${q}`)
    },
    get: (f: AuthFetch, id: string) => json<GuardPolicy>(f, `${base()}/policies/${id}`),
    create: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/policies`, body),
    update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
      put(f, `${base()}/policies/${id}`, body),
    patch: (f: AuthFetch, id: string, workspaceId: string, body: GuardPolicyPatch) =>
      json<GuardPolicy>(
        f,
        `${base()}/policies/${id}?workspace_id=${encodeURIComponent(workspaceId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      ),
    delete: (f: AuthFetch, id: string, workspaceId: string) =>
      f(`${base()}/policies/${id}?workspace_id=${encodeURIComponent(workspaceId)}`, { method: "DELETE" }),
    reinstallBase: (f: AuthFetch, workspaceId: string) =>
      post(f, `${base()}/policies/reinstall-base?workspace_id=${encodeURIComponent(workspaceId)}`, {}),
    lint: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${base()}/policies/lint?workspace_id=${encodeURIComponent(workspaceId)}`, body),
    coverage: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""
      return json<GuardEnforcementCoverage[]>(f, `${base()}/policies/coverage${q}`)
    },
  },

  spend: {
    get: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/spend${q}`)
    },
    budgets: {
      get: (f: AuthFetch, params?: Record<string, string>) => {
        const q = params ? `?${new URLSearchParams(params)}` : ""
        return json<any>(f, `${base()}/spend/budgets${q}`)
      },
      set: (f: AuthFetch, body: Record<string, unknown>) =>
        post(f, `${base()}/spend/budgets`, body),
      remove: (f: AuthFetch, id: string) =>
        f(`${base()}/spend/budgets/${encodeURIComponent(id)}`, { method: "DELETE" }),
    },
    sessions: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any[]>(f, `${base()}/spend/sessions${q}`)
    },
  },

  rateLimits: {
    list: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""
      return json<Array<{ id: string; agent_identity_id: string | null; rpm: number | null; tpm: number | null }>>(
        f, `${base()}/rate-limits${q}`,
      )
    },
    upsert: (f: AuthFetch, body: { agent_identity_id?: string | null; rpm?: number | null; tpm?: number | null }) =>
      put(f, `${base()}/rate-limits`, body),
    remove: (f: AuthFetch, id: string) => del(f, `${base()}/rate-limits/${encodeURIComponent(id)}`),
  },

  tokenGuardrails: {
    get: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return json<any>(f, `${base()}/token-guardrails${q}`)
    },
    set: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/token-guardrails`, body),
    patch: (f: AuthFetch, body: Record<string, unknown>) =>
      patch(f, `${base()}/token-guardrails`, body),
  },

  developerTools: {
    list: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return json<any[]>(f, `${base()}/developer-tools${q}`)
    },
    me: (f: AuthFetch) => json<any>(f, `${base()}/developer-tools/me`),
  },

  discover: {
    summary: (f: AuthFetch) => json<any>(f, `${base()}/discover/summary`),
    agents: (f: AuthFetch) => json<any[]>(f, `${base()}/discover/agents`),
    register: (f: AuthFetch, agentId: string) =>
      post(f, `${base()}/discover/agents/${agentId}/register`, {}),
    scans: (f: AuthFetch) => json<any[]>(f, `${base()}/discover/scans`),
  },

  verify: {
    chain: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/verify/chain${q}`)
    },
    run: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return post(f, `${base()}/verify/run${q}`, {})
    },
    history: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<{ runs: any[] }>(f, `${base()}/verify/history${q}`)
    },
    evidence: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/verify/evidence${q}`)
    },
  },

  sessionReports: {
    list: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any[]>(f, `${base()}/session-reports${q}`)
    },
    get: (f: AuthFetch, id: string, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/session-reports/${id}${q}`)
    },
  },

  savings: {
    summary: (f: AuthFetch, workspaceId: string, month?: string) => {
      const q = new URLSearchParams({ workspace_id: workspaceId })
      if (month) q.set("month", month)
      return json<any>(f, `${base()}/savings/summary?${q}`)
    },
  },

  proxyConfig: {
    get: (f: AuthFetch) => json<any>(f, `${base()}/proxy-config`),
    set: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/proxy-config`, body),
    update: (f: AuthFetch, body: Record<string, unknown>) =>
      put(f, `${base()}/proxy-config`, body),
    push: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/proxy-config/push`, body),
  },

  gatewayProfiles: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${API}/workspaces/${workspaceId}/gateways`),
    create: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${API}/workspaces/${workspaceId}/gateways`, body),
    update: (f: AuthFetch, workspaceId: string, id: string, body: Record<string, unknown>) =>
      put(f, `${API}/workspaces/${workspaceId}/gateways/${id}`, body),
    validate: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      json<{ valid: boolean; warnings: string[] }>(f, `${API}/workspaces/${workspaceId}/gateways/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    push: (f: AuthFetch, workspaceId: string, id: string, environmentId: string) =>
      post(f, `${API}/workspaces/${workspaceId}/gateways/${id}/push`, { environment_id: environmentId }),
  },

  gatewayProfilesV2: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<GatewayProfileV2Out[]>(f, `${API}/workspaces/${workspaceId}/gateway-profiles-v2`),
    get: (f: AuthFetch, workspaceId: string, id: string) =>
      json<GatewayProfileV2Out>(f, `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}`),
    create: (f: AuthFetch, workspaceId: string, body: { name: string; working_copy?: Record<string, unknown> }) =>
      _mutateJson<GatewayProfileV2Out>(f, "POST", `${API}/workspaces/${workspaceId}/gateway-profiles-v2`, body),
    updateWorkingCopy: (f: AuthFetch, workspaceId: string, id: string, workingCopy: Record<string, unknown>) =>
      // Router mounts PUT at the profile-id path itself (no `/working_copy`
      // suffix); posting to `/working_copy` was 404-ing the Save button.
      _mutateJson<GatewayProfileV2Out>(f, "PUT", `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}`, { working_copy: workingCopy }),
    publish: (f: AuthFetch, workspaceId: string, id: string) =>
      _mutateJson<GatewayProfileV2Out>(f, "POST", `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/publish`, {}),
    rollback: (f: AuthFetch, workspaceId: string, id: string, revisionId: string) =>
      _mutateJson<GatewayProfileV2Out>(f, "POST", `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/rollback`, { revision_id: revisionId }),
    revisions: (f: AuthFetch, workspaceId: string, id: string) =>
      json<GatewayProfileV2Revision[]>(f, `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/revisions`),
    revisionSnapshot: (f: AuthFetch, workspaceId: string, id: string, revisionId: string) =>
      json<Record<string, unknown>>(f, `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/revisions/${revisionId}`),
    remove: (f: AuthFetch, workspaceId: string, id: string) =>
      _mutateVoid(f, "DELETE", `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}`),
  },

  notifications: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<NotificationList>(f, `${base()}/notifications?workspace_id=${workspaceId}`),
    create: (f: AuthFetch, workspaceId: string, body: {
      action: NotificationAction
      channel_type?: NotificationChannelType
      integration_id?: string | null
      channel_ref: string
      dedupe_window_sec?: number
    }) =>
      post(f, `${base()}/notifications?workspace_id=${workspaceId}`, body),
    patch: (f: AuthFetch, id: string, workspaceId: string, body: {
      enabled?: boolean
      channel_ref?: string
      integration_id?: string | null
      dedupe_window_sec?: number
    }) =>
      patch(f, `${base()}/notifications/${id}?workspace_id=${workspaceId}`, body),
    remove: (f: AuthFetch, id: string, workspaceId: string) =>
      f(`${base()}/notifications/${id}?workspace_id=${workspaceId}`, { method: "DELETE" }),
    test: (f: AuthFetch, id: string, workspaceId: string) =>
      json<{ ok: boolean; error: string | null }>(f, `${base()}/notifications/${id}/test?workspace_id=${workspaceId}`, {
        method: "POST",
      }),
  },

  mcp: {
    memberToken: (f: AuthFetch) => json<any>(f, `${base()}/mcp/oauth/member-token`),
  },
}

export const governance = {
  narrative: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any>(f, `${API}/governance/narrative${q}`)
  },
  frameworks: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any>(f, `${API}/governance/frameworks${q}`)
  },
  eventsRecent: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any[]>(f, `${API}/governance/events/recent${q}`)
  },
}

export const teamMemory = {
  search: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any[]>(f, `${API}/team-memory/search${q}`)
  },
}

export const teamOs = {
  instructions: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any>(f, `${API}/team-os/instructions${q}`)
  },
  publishInstructions: (f: AuthFetch, params: Record<string, string> | undefined, body: Record<string, unknown>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return post(f, `${API}/team-os/instructions${q}`, body)
  },
  adoption: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any[]>(f, `${API}/team-os/instructions/adoption${q}`)
  },
  templates: (f: AuthFetch) => json<any[]>(f, `${API}/team-os/templates`),
}

export const glens = {
  session: (f: AuthFetch, sessionId: string) =>
    json<any>(f, `${API}/glens/sessions/${sessionId}`),
}

// Block receipts (#1712 Track 1) — every Guard block response carries a
// receipt_id + receipt_url. Workspace users read via authFetch; anonymous
// trial signup users hit the public path with a share token embedded in
// the URL (never persisted anywhere else).
export interface BlockReceipt {
  receipt_id: string
  ts: string | null
  decision: string
  rule_id: string | null
  rule_message: string | null
  provider: string | null
  model: string | null
  ai_tool: string
  input_summary: string | null
  evaluated_rules: Array<Record<string, unknown>> | null
  defense_score: number | null
  conductai_run_id: string | null
  hook_session_id: string | null
}

export interface ShareResult {
  receipt_id: string
  already_shared: boolean
  receipt_url: string | null
}

export const blocks = {
  get: (f: AuthFetch, id: string) =>
    json<BlockReceipt>(f, `${base()}/blocks/${encodeURIComponent(id)}`),
  getPublic: async (id: string, token: string): Promise<BlockReceipt> => {
    const res = await fetch(
      `${base()}/blocks/public/${encodeURIComponent(id)}/${encodeURIComponent(token)}`,
    )
    if (!res.ok) throw new Error(`receipt fetch ${res.status}`)
    return res.json()
  },
  share: async (f: AuthFetch, id: string): Promise<ShareResult> => {
    const res = await post(f, `${base()}/blocks/${encodeURIComponent(id)}/share`, {})
    if (!res.ok) throw new Error(`share ${res.status}`)
    return res.json()
  },
}
