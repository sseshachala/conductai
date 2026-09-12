import { API, type AuthFetch, json, patch as patchReq, post } from "./client"

const base = () => `${API}/guard/inbox`

export type InboxSeverity = "critical" | "medium" | "low"
export type InboxStatus = "open" | "triaging" | "resolved"
export type InboxSource = "proxy" | "mcp" | "hook" | "runtime"
export type ResolvedReason = "expected" | "escalated" | "exception_added" | "false_positive"

export interface InboxRow {
  id: string
  rule_id: string
  source: string
  severity: string
  description: string | null
  occurrences: number
  first_seen_at: string
  last_seen_at: string
  status: string
  resolved_reason: string | null
  resolved_note: string | null
  resolved_at: string | null
  resolved_by: string | null
  latest_event_id: string | null
}

export interface InboxEvent {
  id: string
  ts: string
  decision: string
  ai_tool: string | null
  user_email: string | null
  input_summary: string | null
  provider: string | null
  model: string | null
}

export interface InboxPatch {
  status: InboxStatus
  resolved_reason?: ResolvedReason
  resolved_note?: string
}

export interface BackfillResult {
  days: number
  inserted: number
}

export interface InboxListFilters {
  status?: InboxStatus
  severity?: InboxSeverity
  source?: InboxSource
  limit?: number
  offset?: number
}

function qs(filters?: InboxListFilters): string {
  if (!filters) return ""
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ""
}

export const guardInbox = {
  list: (f: AuthFetch, filters?: InboxListFilters) =>
    json<InboxRow[]>(f, `${base()}${qs(filters)}`),

  get: (f: AuthFetch, id: string) =>
    json<InboxRow>(f, `${base()}/${encodeURIComponent(id)}`),

  events: (f: AuthFetch, id: string, limit = 20) =>
    json<InboxEvent[]>(f, `${base()}/${encodeURIComponent(id)}/events?limit=${limit}`),

  patch: async (f: AuthFetch, id: string, body: InboxPatch): Promise<InboxRow> => {
    const res = await patchReq(f, `${base()}/${encodeURIComponent(id)}`, body)
    if (!res.ok) throw new Error(await res.text().catch(() => `patch ${res.status}`))
    return res.json()
  },

  backfill: async (f: AuthFetch, days: number): Promise<BackfillResult> => {
    const res = await post(f, `${base()}/backfill?days=${days}`, {})
    if (!res.ok) throw new Error(await res.text().catch(() => `backfill ${res.status}`))
    return res.json()
  },
}
