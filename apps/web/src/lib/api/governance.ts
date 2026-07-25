import { API, AuthFetch, json, post } from "./client"

const base = () => `${API}/governance`

export const governance = {
  frameworks: (f: AuthFetch, workspaceId: string) =>
    json<any>(f, `${base()}/frameworks?workspace_id=${workspaceId}`),

  narrative: (f: AuthFetch, workspaceId: string, period: string) =>
    json<any>(f, `${base()}/narrative?workspace_id=${workspaceId}&period=${period}`),

  eventsRecent: (f: AuthFetch, workspaceId: string, params?: { limit?: number; decision?: string; from_dt?: string; to_dt?: string }) => {
    const q = new URLSearchParams({ workspace_id: workspaceId })
    if (params?.limit != null) q.set("limit", String(params.limit))
    if (params?.decision) q.set("decision", params.decision)
    if (params?.from_dt) q.set("from_dt", params.from_dt)
    if (params?.to_dt) q.set("to_dt", params.to_dt)
    return json<any[]>(f, `${base()}/events/recent?${q}`)
  },

  kpis: (f: AuthFetch, workspaceId: string) =>
    json<any>(f, `${base()}/kpis?workspace_id=${workspaceId}`),

  certifications: (f: AuthFetch, workspaceId: string) =>
    json<any[]>(f, `${base()}/certifications?workspace_id=${workspaceId}`),

  certify: (f: AuthFetch, workspaceId: string, body: Record<string, unknown>) =>
    post(f, `${base()}/certify?workspace_id=${workspaceId}`, body),

  controlRules: (f: AuthFetch, framework: string, control: string, workspaceId: string) =>
    json<any>(f, `${base()}/frameworks/${framework}/controls/${control}/rules?workspace_id=${workspaceId}`),
}

export const compliance = {
  installedPacks: (f: AuthFetch, workspaceId: string) =>
    json<any>(f, `${API}/compliance/packs/installed?workspace_id=${workspaceId}`),
}
