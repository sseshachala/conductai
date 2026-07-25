import { API, AuthFetch, json, post } from "./client"

const base = () => `${API}/runs`

export const runs = {
  list: (f: AuthFetch, params?: { limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.limit != null) q.set("limit", String(params.limit))
    if (params?.offset != null) q.set("offset", String(params.offset))
    const qs = q.toString() ? `?${q}` : ""
    return json<any[]>(f, `${base()}${qs}`)
  },

  listByProject: (f: AuthFetch, params: { project_id: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams({ project_id: params.project_id })
    if (params.limit != null) q.set("limit", String(params.limit))
    if (params.offset != null) q.set("offset", String(params.offset))
    return json<any[]>(f, `${base()}?${q}`)
  },

  listFiltered: (f: AuthFetch, params: Record<string, string>) => {
    const q = new URLSearchParams(params)
    return json<any[]>(f, `${base()}?${q}`)
  },

  approve: (f: AuthFetch, runId: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${runId}/approve`, body),
}
