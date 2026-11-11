import { API, AuthFetch, del, json, patch, post, put } from "./client"
import { cachedGet, invalidating } from "./sharedCache"

export interface AuditFeedCollector {
  actor_id: string
  actor_email: string | null
  last_pull_at: string
  cursor_ts: string
  lag_seconds: number
  last_page_events: number
  stale: boolean
  collector_type?: "user" | "service_token"
  label?: string | null
}

export interface AuditFeedToken {
  id: string
  name: string | null
  token_prefix: string | null
  scope: string
  status: "active" | "revoked" | "expired"
  created_by: string | null
  created_at: string | null
  expires_at: string | null
  revoked_at: string | null
}

export interface AuditFeedTokenCreated extends AuditFeedToken {
  token: string
}

export interface AuditFeedStatus {
  available: boolean
  collectors: AuditFeedCollector[]
  stale_after_seconds: number
  /** ISO instant from which the audit hash chain fully covers the log; null when nothing is chained yet. */
  chain_complete_from?: string | null
}

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
      cachedGet(`${base(workspaceId)}/projects`, () => json<any[]>(f, `${base(workspaceId)}/projects`)),
    create: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      invalidating(`${base(workspaceId)}/projects`, post(f, `${base(workspaceId)}/projects`, body)),
    rename: (f: AuthFetch, workspaceId: string, projectId: string, body: Record<string, unknown>) =>
      invalidating(`${base(workspaceId)}/projects`, patch(f, `${base(workspaceId)}/projects/${projectId}`, body)),
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
      cachedGet(`${base(workspaceId)}/preferences`, () => json<any>(f, `${base(workspaceId)}/preferences`)),
    update: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
      invalidating(`${base(workspaceId)}/preferences`, put(f, `${base(workspaceId)}/preferences`, body)),
  },

  // Read-only in the web app (no read/clear writes exist); short TTL so new items surface.
  notifications: (f: AuthFetch, workspaceId: string, limit = 8) => {
    const url = `${base(workspaceId)}/notifications?limit=${limit}`
    return cachedGet(url, () => json<{ items: any[]; total?: number }>(f, url), 30_000)
  },

  auditLog: (f: AuthFetch, workspaceId: string, params?: { limit?: number; offset?: number; action?: string }) => {
    const q = new URLSearchParams()
    if (params?.limit != null) q.set("limit", String(params.limit))
    if (params?.offset != null) q.set("offset", String(params.offset))
    if (params?.action) q.set("action", params.action)
    const qs = q.toString() ? `?${q}` : ""
    return json<any[]>(f, `${base(workspaceId)}/audit-log${qs}`)
  },

  auditFeedStatus: (f: AuthFetch, workspaceId: string) =>
    json<AuditFeedStatus>(f, `${base(workspaceId)}/audit-log/feed-status`),

  auditFeedTokens: {
    list: (f: AuthFetch, workspaceId: string) =>
      json<AuditFeedToken[]>(f, `${base(workspaceId)}/audit-feed-tokens`),
    create: (f: AuthFetch, workspaceId: string, body: { name: string; expires_in_days?: number }) =>
      json<AuditFeedTokenCreated>(f, `${base(workspaceId)}/audit-feed-tokens`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      }),
    revoke: (f: AuthFetch, workspaceId: string, tokenId: string) =>
      del(f, `${base(workspaceId)}/audit-feed-tokens/${tokenId}`),
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