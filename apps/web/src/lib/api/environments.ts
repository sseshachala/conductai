import { API, AuthFetch, del, json, post, put } from "./client"

const base = () => `${API}/environments`

export const environments = {
  list: (f: AuthFetch) => json<any[]>(f, base()),
  create: (f: AuthFetch, body: Record<string, unknown>) => post(f, base(), body),
  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    put(f, `${base()}/${id}`, body),
  remove: (f: AuthFetch, id: string) => del(f, `${base()}/${id}`),
}
