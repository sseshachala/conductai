import { API } from "@/lib/api"

export type CompleterOption = { value: string; label: string; sublabel?: string }
type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>
type CompleterFn = (authFetch: AuthFetch, workspaceId: string | null) => Promise<CompleterOption[]>

// Map arg completers → REST endpoints. Every endpoint already exists — no
// backend changes for this feature. Entries are wired to args in SLASH_TOOLS;
// dormant entries (budgets/agents/marketplace_packs) are ready for the
// #1300-#1304 mutators when they land.
export const COMPLETERS: Record<string, CompleterFn> = {
  workflows: async authFetch => {
    const r = await authFetch(`${API}/workflows`)
    if (!r.ok) throw new Error(`workflows ${r.status}`)
    const rows = (await r.json()) as Array<{ id: string; name: string; playbook_slug?: string | null }>
    return rows.map(w => ({
      value: w.playbook_slug || w.id,
      label: w.name,
      sublabel: w.playbook_slug ? `slug: ${w.playbook_slug}` : undefined,
    }))
  },
  pending_approvals: async authFetch => {
    const r = await authFetch(`${API}/guard/approvals?status=pending&limit=50`)
    if (!r.ok) throw new Error(`approvals ${r.status}`)
    const body = (await r.json()) as { items: Array<{ id: string; rule_message: string | null; tool_name: string | null }> }
    return body.items.map(a => ({
      value: a.id,
      label: a.rule_message || a.tool_name || a.id,
      sublabel: a.tool_name ? `tool: ${a.tool_name}` : undefined,
    }))
  },
  // Dormant until #1302 update_budget mutator lands and attaches completer.
  budgets: async authFetch => {
    const r = await authFetch(`${API}/guard/spend/budgets`)
    if (!r.ok) throw new Error(`budgets ${r.status}`)
    const rows = (await r.json()) as Array<{ id: string; email: string | null; monthly_limit_usd: number }>
    return rows.map(b => ({
      value: b.id,
      label: b.email || b.id,
      sublabel: `$${b.monthly_limit_usd}/mo`,
    }))
  },
  // Dormant until #1304 deactivate_agent_identity mutator lands.
  agents: async (authFetch, workspaceId) => {
    if (!workspaceId) return []
    const r = await authFetch(`${API}/workspaces/${workspaceId}/agent-identities?workspace_id=${workspaceId}`)
    if (!r.ok) throw new Error(`agents ${r.status}`)
    const rows = (await r.json()) as Array<{ id: string; name: string; provider: string }>
    return rows.map(a => ({
      value: a.id,
      label: a.name,
      sublabel: a.provider ? `provider: ${a.provider}` : undefined,
    }))
  },
  // Date-range presets for /export-audit. Static: no endpoint. The value is a
  // natural-language range with explicit ISO bounds that Lens routes to
  // export_audit_log (since/until).
  audit_ranges: async () => auditRangePresets(new Date()),
  // Wired for #1303 enable_policy / disable_policy — lists both custom and pack rules.
  policies: async authFetch => {
    const r = await authFetch(`${API}/guard/policies`)
    if (!r.ok) throw new Error(`policies ${r.status}`)
    const rows = (await r.json()) as Array<{ rule_id: string; description?: string | null; enabled: boolean; pack_id?: string | null }>
    return rows.map(p => ({
      value: p.rule_id,
      label: p.description || p.rule_id,
      sublabel: `${p.enabled ? "enabled" : "disabled"}${p.pack_id ? ` · pack: ${p.pack_id}` : ""}`,
    }))
  },
  // Wired for #1300 install_pack mutator.
  marketplace_packs: async authFetch => {
    const r = await authFetch(`${API}/compliance/packs/available`)
    if (!r.ok) throw new Error(`packs ${r.status}`)
    const rows = (await r.json()) as Array<{ slug: string; name: string; description?: string }>
    return rows.map(p => ({
      value: p.slug,
      label: p.name,
      sublabel: p.description || undefined,
    }))
  },
}

export function auditRangePresets(now: Date): CompleterOption[] {
  const until = now.toISOString()
  const day = 86_400_000
  const ago = (ms: number) => new Date(now.getTime() - ms).toISOString()
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString()
  const mk = (label: string, since: string): CompleterOption => ({
    value: `since ${since} until ${until}`,
    label,
    sublabel: `${since.slice(0, 10)} to ${until.slice(0, 10)}`,
  })
  return [
    mk("Last 24 hours", ago(day)),
    mk("Last 7 days", ago(7 * day)),
    mk("Last 30 days", ago(30 * day)),
    mk("This month", monthStart),
  ]
}
