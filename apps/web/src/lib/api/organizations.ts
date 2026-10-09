import { API, AuthFetch, json, patch } from "./client"
import { cachedGet, invalidating } from "./sharedCache"

const base = () => `${API}/organizations`

export const organizations = {
  list: (f: AuthFetch) => cachedGet(base(), () => json<any[]>(f, base())),
  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    invalidating(base(), patch(f, `${base()}/${id}`, body)),
}
