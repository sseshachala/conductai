import { API, AuthFetch, del, json, post, put } from "./client"

const base = () => `${API}/credentials`

export const credentials = {
  list: (f: AuthFetch) => json<any[]>(f, base()),
  create: (f: AuthFetch, body: Record<string, unknown>) => post(f, base(), body),
  remove: (f: AuthFetch, handle: string) => del(f, `${base()}/${handle}`),
  reveal: (f: AuthFetch, handle: string) => json<any>(f, `${base()}/reveal/${handle}`),
  byEnvironment: (f: AuthFetch, envId: string) =>
    json<any[]>(f, `${base()}/by-environment/${envId}`),

  envVars: {
    get: (f: AuthFetch, envId: string) => json<any>(f, `${base()}/env-vars/${envId}`),
    set: (f: AuthFetch, envId: string, body: Record<string, unknown>) =>
      post(f, `${base()}/env-vars/${envId}`, body),
    update: (f: AuthFetch, envId: string, body: Record<string, unknown>) =>
      put(f, `${base()}/env-vars/${envId}`, body),
  },

  github: {
    repos: (f: AuthFetch, environmentId?: string) => {
      const q = environmentId ? `?environment_id=${environmentId}` : ""
      return json<any[]>(f, `${base()}/github/repos${q}`)
    },
    branches: (f: AuthFetch, owner: string, repo: string) =>
      json<any[]>(f, `${base()}/github/repos/${owner}/${repo}/branches`),
    issues: (f: AuthFetch, params: { repo: string; label?: string }) => {
      const q = new URLSearchParams({ repo: params.repo })
      if (params.label) q.set("label", params.label)
      return json<any[]>(f, `${base()}/github/issues?${q}`)
    },
    webhook: (f: AuthFetch, owner: string, repo: string, body: Record<string, unknown>) =>
      post(f, `${base()}/github/repos/${owner}/${repo}/webhook`, body),
  },

  slack: {
    integration: (f: AuthFetch, workspaceId: string) =>
      json<any>(f, `${base()}/integrations/slack?workspace_id=${workspaceId}`),
  },

  vercel: {
    webhook: (f: AuthFetch, body: Record<string, unknown>) =>
      post(f, `${base()}/vercel/webhook`, body),
  },
}
