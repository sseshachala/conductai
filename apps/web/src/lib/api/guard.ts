import { API, AuthFetch, del, json, patch, post, put } from "./client"
import { cachedGet, invalidating } from "./sharedCache"
import { _mutateJson, _mutateVoid, base } from "./guard-http"
import type {
  GatewayProfileRateLimits,
  GatewayProfileRateLimitsInput,
  GatewayProfileV2ImportOut,
  GatewayProfileV2Out,
  GatewayProfileV2Revision,
  GuardEnforcementCoverage,
  GuardPolicy,
  GuardPolicyPatch,
  NotificationAction,
  NotificationChannelType,
  NotificationList,
  RuleFire,
} from "./guard-types"

export { GatewayValidationError } from "./guard-http"
export type { GatewayValidationErrorItem } from "./guard-http"
export type {
  GatewayProfileAgentRateCap,
  GatewayProfileRateLimitsInput,
  GatewayProfileRateLimits,
  GatewayProfileV2Operation,
  GatewayProfileV2Target,
  GatewayProfileV2WorkingCopy,
  GatewayProfileV2Revision,
  GatewayProfileV2Out,
  GatewayProfileV2ImportGap,
  GatewayProfileV2ImportOut,
  GuardPolicyAction,
  GuardPolicy,
  GuardPolicyPatch,
  RuleFire,
  EnforcementStatus,
  GuardEnforcementCoverage,
  NotificationAction,
  NotificationChannelType,
  NotificationChannel,
  NotificationGroup,
  NotificationList,
} from "./guard-types"
export { governance, teamMemory, teamOs, glens, reservations, blocks } from "./guard-extras"
export type { BlockReceipt, ReservationScope, ShareResult } from "./guard-extras"

export const guard = {
  config: {
    get: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return cachedGet(`${base()}/config${q}`, () => json<any>(f, `${base()}/config${q}`))
    },
    installed: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return cachedGet(`${base()}/config/installed${q}`, () => json<any>(f, `${base()}/config/installed${q}`))
    },
    persona: (f: AuthFetch) => json<any>(f, `${base()}/config/persona`),
    patch: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      invalidating(`${base()}/config`, patch(f, `${base()}/config?workspace_id=${workspaceId}`, body)),
    resync: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return invalidating(`${base()}/config`, post(f, `${base()}/config/resync${q}`, {}))
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
    agents: (f: AuthFetch, workspaceId: string) =>
      json<Array<{ id: string; name: string }>>(f, `${base()}/rate-limits/agents?${new URLSearchParams({ workspace_id: workspaceId })}`),
    list: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ""
      return json<Array<{ id: string; agent_identity_id: string | null; rpm: number | null; tpm: number | null }>>(
        f, `${base()}/rate-limits${q}`,
      )
    },
    upsert: (f: AuthFetch, body: { agent_identity_id?: string | null; rpm?: number | null; tpm?: number | null }, workspaceId?: string) =>
      _mutateJson<{ id: string; agent_identity_id: string | null; rpm: number | null; tpm: number | null }>(f, "PUT",
        `${base()}/rate-limits${workspaceId ? `?${new URLSearchParams({ workspace_id: workspaceId })}` : ""}`, body),
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
    agents: (f: AuthFetch, offset = 0, limit = 100, inventory = "all") => json<any[]>(f, `${base()}/discover/agents?offset=${offset}&limit=${limit}&inventory=${encodeURIComponent(inventory)}`),
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

  gatewayProfilesV2: {
    rateLimits: {
      get: (f: AuthFetch, workspaceId: string, id: string) =>
        json<GatewayProfileRateLimits>(f, `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/rate-limits`),
      set: (f: AuthFetch, workspaceId: string, id: string, body: Partial<GatewayProfileRateLimitsInput>) =>
        _mutateJson<GatewayProfileRateLimits>(f, "PUT", `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/rate-limits`, body),
    },
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
    /**
     * Import a profile from a portable JSON payload. Server strips
     * every credential_ref on import; response.credential_gaps
     * lists targets that still need a vault pick. Same endpoint the
     * CLI conduct import --gateway-config hits.
     */
    importJson: (
      f: AuthFetch, workspaceId: string,
      body: { working_copy: Record<string, unknown>; name_override?: string },
    ) =>
      _mutateJson<GatewayProfileV2ImportOut>(
        f, "POST",
        `${API}/workspaces/${workspaceId}/gateway-profiles-v2/import`,
        body,
      ),
    /**
     * Export a profile as portable JSON (credentials stripped).
     * Round-trips cleanly through importJson.
     */
    exportJson: (f: AuthFetch, workspaceId: string, id: string) =>
      json<Record<string, unknown>>(
        f, `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${id}/export`,
      ),
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
