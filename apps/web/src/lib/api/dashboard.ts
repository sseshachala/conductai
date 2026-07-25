import { API, AuthFetch, json } from "./client"

export const dashboard = {
  get: (f: AuthFetch) => json<any>(f, `${API}/dashboard`),
}
