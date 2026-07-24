import { API, AuthFetch, json, post, put } from "./client"

const base = () => `${API}/guard`

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
    resync: (f: AuthFetch) => post(f, `${base()}/config/resync`, {}),
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
    costTrend: (f: AuthFetch, period: string) =>
      json<any>(f, `${base()}/events/cost-trend?period=${period}`),
    streamUrl: () => `${base()}/events/stream`,
  },

  policies: {
    list: (f: AuthFetch, workspaceId?: string) => {
      const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
      return json<any[]>(f, `${base()}/policies${q}`)
    },
    get: (f: AuthFetch, id: string) => json<any>(f, `${base()}/policies/${id}`),
    create: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/policies`, body),
    update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
      put(f, `${base()}/policies/${id}`, body),
  },

  spend: {
    get: (f: AuthFetch, params?: Record<string, string>) => {
      const q = params ? `?${new URLSearchParams(params)}` : ""
      return json<any>(f, `${base()}/spend${q}`)
    },
    budgets: {
      get: (f: AuthFetch) => json<any>(f, `${base()}/spend/budgets`),
      set: (f: AuthFetch, body: Record<string, unknown>) =>
        post(f, `${base()}/spend/budgets`, body),
    },
    sessions: (f: AuthFetch) => json<any[]>(f, `${base()}/spend/sessions`),
  },

  tokenGuardrails: {
    get: (f: AuthFetch) => json<any>(f, `${base()}/token-guardrails`),
    set: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/token-guardrails`, body),
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
    chain: (f: AuthFetch) => json<any>(f, `${base()}/verify/chain`),
    run: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/verify/run`, body),
    history: (f: AuthFetch) => json<any[]>(f, `${base()}/verify/history`),
  },

  sessionReports: {
    list: (f: AuthFetch) => json<any[]>(f, `${base()}/session-reports`),
    get: (f: AuthFetch, id: string) => json<any>(f, `${base()}/session-reports/${id}`),
  },

  proxyConfig: {
    get: (f: AuthFetch) => json<any>(f, `${base()}/proxy-config`),
    set: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/proxy-config`, body),
    push: (f: AuthFetch) => post(f, `${base()}/proxy-config/push`, {}),
  },

  mcp: {
    memberToken: (f: AuthFetch) => json<any>(f, `${base()}/mcp/oauth/member-token`),
  },
}
