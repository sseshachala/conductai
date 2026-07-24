import { API, AuthFetch, json } from "./client"

export const meta = {
  blockSchemas: (f: AuthFetch, workspaceId: string) =>
    json<any>(f, `${API}/meta/block-schemas?workspace_id=${workspaceId}`),
  routingTable: (f: AuthFetch) =>
    json<any>(f, `${API}/meta/routing-table`),
}
