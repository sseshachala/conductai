import { API, AuthFetch, del, json, patch, post, put } from "./client"

const base = () => `${API}/workflows`

export const workflows = {
  list: (f: AuthFetch, params?: { project_id?: string }) => {
    const q = params?.project_id ? `?project_id=${params.project_id}` : ""
    return json<any[]>(f, `${base()}${q}`)
  },

  get: (f: AuthFetch, id: string) => json<any>(f, `${base()}/${id}`),

  create: (f: AuthFetch, body: Record<string, unknown>) =>
    post(f, base(), body),

  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}`, body),

  remove: (f: AuthFetch, id: string) => del(f, `${base()}/${id}`),

  validate: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}/validate`, body),

  validateInputs: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}/validate-inputs`, body),

  preflight: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}/preflight`, body),

  trigger: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}/trigger`, body),

  estimate: (f: AuthFetch, id: string, params?: { issues?: number }) => {
    const q = params?.issues != null ? `?issues=${params.issues}` : ""
    return json<any>(f, `${base()}/${id}/estimate${q}`)
  },

  setEnvironment: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}/set-environment`, body),

  patchEnvironment: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    patch(f, `${base()}/${id}/environment`, body),

  setTurnSettings: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    post(f, `${base()}/${id}/turn-settings`, body),

  yaml: {
    update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
      put(f, `${base()}/${id}/yaml`, body),
    fromGraph: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/yaml/from-graph`, body),
    validate: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/yaml/validate`, body),
  },

  webhook: {
    get: (f: AuthFetch, id: string) => json<any>(f, `${base()}/${id}/webhook`),
    create: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
      post(f, `${base()}/${id}/webhook`, body),
    remove: (f: AuthFetch, id: string) => del(f, `${base()}/${id}/webhook`),
  },

  blocks: {
    compileStreamUrl: (workflowId: string, blockId: string) =>
      `${base()}/${workflowId}/blocks/${blockId}/compile/stream`,
  },

  runs: {
    list: (f: AuthFetch, workflowId: string, params?: { limit?: number; offset?: number }) => {
      const q = new URLSearchParams()
      if (params?.limit != null) q.set("limit", String(params.limit))
      if (params?.offset != null) q.set("offset", String(params.offset))
      const qs = q.toString() ? `?${q}` : ""
      return json<any[]>(f, `${base()}/${workflowId}/runs${qs}`)
    },
    get: (f: AuthFetch, workflowId: string, runId: string) =>
      json<any>(f, `${base()}/${workflowId}/runs/${runId}`),
    trigger: (f: AuthFetch, workflowId: string, body?: Record<string, unknown>) =>
      post(f, `${base()}/${workflowId}/runs`, body ?? {}),
    approve: (f: AuthFetch, workflowId: string, runId: string, body: Record<string, unknown>) =>
      post(f, `${base()}/${workflowId}/runs/${runId}/approve`, body),
    cancel: (f: AuthFetch, workflowId: string, runId: string) =>
      post(f, `${base()}/${workflowId}/runs/${runId}/cancel`, {}),
    streamUrl: (workflowId: string, runId: string) =>
      `${base()}/${workflowId}/runs/${runId}/stream`,
  },

  playbooks: {
    list: (f: AuthFetch) => json<any[]>(f, `${base()}/playbooks`),
    get: (f: AuthFetch, slug: string) => json<any>(f, `${base()}/playbooks/${slug}`),
  },

  generate: (f: AuthFetch, body: Record<string, unknown>) =>
    post(f, `${base()}/generate`, body),
}

// Appended by migration
