import { API, AuthFetch, del, json, patch, post, put } from "./client"

const base = (id: string) => `${API}/workspaces/${id}`

export const workspaces = {
  members: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${base(workspaceId)}/members`),
    add: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${base(workspaceId)}/members`, body),
  },

  projects: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${base(workspaceId)}/projects`),
    create: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${base(workspaceId)}/projects`, body),
    rename: (f: AuthFetch, workspaceId: string, projectId: string, body: Record<string, unknown>) =>
      patch(f, `${base(workspaceId)}/projects/${projectId}`, body),
  },

  apiKeys: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${base(workspaceId)}/api-keys`),
    create: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${base(workspaceId)}/api-keys`, body),
    remove: (f: AuthFetch, workspaceId: string, keyId: string) =>
      del(f, `${base(workspaceId)}/api-keys/${keyId}`),
  },

  preferences: {
    get: (f: AuthFetch, workspaceId: string) =>
      json<any>(f, `${base(workspaceId)}/preferences`),
    update: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      put(f, `${base(workspaceId)}/preferences`, body),
  },

  notifications: (f: AuthFetch, workspaceId: string, limit = 8) =>
    json<{ items: any[]; total?: number }>(f, `${base(workspaceId)}/notifications?limit=${limit}`),

  auditLog: (f: AuthFetch, workspaceId: string, params?: { limit?: number; offset?: number; action?: string }) => {
    const q = new URLSearchParams()
    if (params?.limit != null) q.set("limit", String(params.limit))
    if (params?.offset != null) q.set("offset", String(params.offset))
    if (params?.action) q.set("action", params.action)
    const qs = q.toString() ? `?${q}` : ""
    return json<any[]>(f, `${base(workspaceId)}/audit-log${qs}`)
  },

  agentRunTokens: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${base(workspaceId)}/agent-run-tokens`),
  },

  apiTokens: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${base(workspaceId)}/api-tokens`),
    create: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${base(workspaceId)}/api-tokens`, body),
    remove: (f: AuthFetch, workspaceId: string, tokenId: string) =>
      del(f, `${base(workspaceId)}/api-tokens/${tokenId}`),
  },
}