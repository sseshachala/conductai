import { API, AuthFetch, json } from "./client"

const base = () => `${API}/share`

export const share = {
  create: (f: AuthFetch, body: Record<string, unknown>) =>
    json<{ share_url: string }>(f, base(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
}
