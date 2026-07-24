import { API, AuthFetch, json, patch } from "./client"

const base = () => `${API}/organizations`

export const organizations = {
  list: (f: AuthFetch) => json<any[]>(f, base()),
  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    patch(f, `${base()}/${id}`, body),
}
