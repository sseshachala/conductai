import { API, AuthFetch, del, json, post, put } from "./client"

const base = () => `${API}/mcp-servers`

export const mcpServers = {
  list: (f: AuthFetch, workspaceId?: string) => {
    const q = workspaceId ? `?workspace_id=${workspaceId}` : ""
    return json<any[]>(f, `${base()}${q}`)
  },
  create: (f: AuthFetch, body: Record<string, unknown>) => post(f, base(), body),
  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    put(f, `${base()}/${id}`, body),
  remove: (f: AuthFetch, id: string) => del(f, `${base()}/${id}`),
  tools: (f: AuthFetch, id: string) => json<any[]>(f, `${base()}/${id}/tools`),
  testConnection: (f: AuthFetch, body: Record<string, unknown>) =>
    post(f, `${base()}/test-connection`, body),
}
