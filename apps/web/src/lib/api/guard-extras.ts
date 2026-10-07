import { API, AuthFetch, json, post } from "./client"
import { base } from "./guard-http"

export const governance = {
  narrative: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any>(f, `${API}/governance/narrative${q}`)
  },
  frameworks: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any>(f, `${API}/governance/frameworks${q}`)
  },
  eventsRecent: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any[]>(f, `${API}/governance/events/recent${q}`)
  },
}

export const teamMemory = {
  search: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any[]>(f, `${API}/team-memory/search${q}`)
  },
}

export const teamOs = {
  instructions: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any>(f, `${API}/team-os/instructions${q}`)
  },
  publishInstructions: (f: AuthFetch, params: Record<string, string> | undefined, body: Record<string, unknown>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return post(f, `${API}/team-os/instructions${q}`, body)
  },
  adoption: (f: AuthFetch, params?: Record<string, string>) => {
    const q = params ? `?${new URLSearchParams(params)}` : ""
    return json<any[]>(f, `${API}/team-os/instructions/adoption${q}`)
  },
  templates: (f: AuthFetch) => json<any[]>(f, `${API}/team-os/templates`),
}

export const glens = {
  session: (f: AuthFetch, sessionId: string) =>
    json<any>(f, `${API}/glens/sessions/${sessionId}`),
}

// Block receipts (#1712 Track 1) — every Guard block response carries a
// receipt_id + receipt_url. Workspace users read via authFetch; anonymous
// trial signup users hit the public path with a share token embedded in
// the URL (never persisted anywhere else).
export interface BlockReceipt {
  receipt_id: string
  ts: string | null
  decision: string
  rule_id: string | null
  rule_message: string | null
  provider: string | null
  model: string | null
  ai_tool: string
  input_summary: string | null
  evaluated_rules: Array<Record<string, unknown>> | null
  defense_score: number | null
  conductai_run_id: string | null
  hook_session_id: string | null
  // PR-B: correlation to budget_reservations rows. Present on gateway rows
  // that reached the ledger; null on rows written before PR-A2b or when
  // BUDGET_LEDGER_ENABLED was off.
  request_id?: string | null
}

// PR-B: per-scope reservation record for the drawer scope table.
export interface ReservationScope {
  reservation_id: string
  workspace_id: string
  clerk_user_id: string | null
  agent_identity_id: string | null
  deleted_agent_identity_id: string | null
  ai_tool: string | null
  source: string | null
  client_tool: string | null
  period_key: string
  estimated_cents: number
  actual_cents: number | null
  status: string
  created_at: string
  resolved_at: string | null
}

export interface ShareResult {
  receipt_id: string
  already_shared: boolean
  receipt_url: string | null
}

// PR-B: fetch the per-scope reservations tied to a single audit request_id.
// Empty array is a valid response — feature flag off or no hard caps applied.
async function fetchReservationsForRequest(
  f: AuthFetch,
  requestId: string,
): Promise<ReservationScope[]> {
  const url = `${base()}/spend/reservations?request_id=${encodeURIComponent(requestId)}`
  return json<ReservationScope[]>(f, url)
}

export const reservations = {
  forRequest: fetchReservationsForRequest,
}

export const blocks = {
  get: (f: AuthFetch, id: string) =>
    json<BlockReceipt>(f, `${base()}/blocks/${encodeURIComponent(id)}`),
  getPublic: async (id: string, token: string): Promise<BlockReceipt> => {
    const res = await fetch(
      `${base()}/blocks/public/${encodeURIComponent(id)}/${encodeURIComponent(token)}`,
    )
    if (!res.ok) throw new Error(`receipt fetch ${res.status}`)
    return res.json()
  },
  share: async (f: AuthFetch, id: string): Promise<ShareResult> => {
    const res = await post(f, `${base()}/blocks/${encodeURIComponent(id)}/share`, {})
    if (!res.ok) throw new Error(`share ${res.status}`)
    return res.json()
  },
}
