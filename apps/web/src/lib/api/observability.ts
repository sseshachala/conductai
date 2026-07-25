import { API, AuthFetch, json } from "./client"

export const observability = {
  agents: (f: AuthFetch) => json<any[]>(f, `${API}/observability/agents`),
}

export const analytics = {
  summary: (f: AuthFetch, days = 30) =>
    json<any>(f, `${API}/analytics/summary?days=${days}`),
  dora: (f: AuthFetch, days = 30) =>
    json<any>(f, `${API}/analytics/dora?days=${days}`),
  scorecards: (f: AuthFetch, days = 30) =>
    json<any[]>(f, `${API}/analytics/scorecards?days=${days}`),
}
