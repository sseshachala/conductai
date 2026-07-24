import { API, AuthFetch, json, patch, post } from "./client"

const base = () => `${API}/security-findings`

export const security = {
  list: (f: AuthFetch, workspaceId: string, params?: { days?: number; limit?: number }) => {
    const q = new URLSearchParams({ workspace_id: workspaceId })
    if (params?.days != null) q.set("days", String(params.days))
    if (params?.limit != null) q.set("limit", String(params.limit))
    return json<any[]>(f, `${base()}?${q}`)
  },
  summary: (f: AuthFetch, workspaceId: string, params?: { days?: number }) => {
    const q = new URLSearchParams({ workspace_id: workspaceId })
    if (params?.days != null) q.set("days", String(params.days))
    return json<any>(f, `${base()}/summary?${q}`)
  },
  get: (f: AuthFetch, id: string, workspaceId: string) =>
    json<any>(f, `${base()}/${id}?workspace_id=${workspaceId}`),
  update: (f: AuthFetch, id: string, workspaceId: string, body: Record<string, unknown>) =>
    patch(f, `${base()}/${id}?workspace_id=${workspaceId}`, body),
  triggerFix: (f: AuthFetch, id: string, workspaceId: string) =>
    post(f, `${base()}/${id}/trigger-fix?workspace_id=${workspaceId}`, {}),
}
