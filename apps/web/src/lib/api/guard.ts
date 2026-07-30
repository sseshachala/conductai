import { API, AuthFetch, json, patch, post, put } from "./client"

const base = () => `${API}/guard`

export type GuardPolicyAction = "block" | "approval" | "warn" | "inject" | "audit"

export interface GuardPolicy {
  id: string
  workspace_id: string
  rule_id: string
  description: string | null
  match_tool: string | null
  match_pattern: string | null
  match_path_pattern: string | null
  action: GuardPolicyAction
  message: string | null
  enabled: boolean
  builtin: boolean
  pack_id: string | null
  persona: "agent" | "proxy"
  non_overridable: boolean
  persona_affinity: string[]
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
  message?: string
  reason?: string
  expires_at?: string
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
  guarantee: string
  requires: string[]
  known_limitations: string[]
  enforcement_version: 1
  exception_reason: string | null
  exception_expires_at: string | null
  exception_active: boolean
  exception_expired: boolean
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
    },
    sessions: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any[]>(f, `${base()}/spend/sessions${q}`)
    },
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
