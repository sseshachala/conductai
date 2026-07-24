import { API, AuthFetch, del, json, post, put } from "./client"

const base = (id: string) => `${API}/workspaces/${id}`

export const workspaces = {
  members: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<any[]>(f, `${base(workspaceId)}/members`),
    add: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      post(f, `${base(workspaceId)}/members`, body),
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
    json<any[]>(f, `${base(workspaceId)}/notifications?limit=${limit}`),

  auditLog: (f: AuthFetch, workspaceId: string) =>
    json<any[]>(f, `${base(workspaceId)}/audit-log`),
}
