"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { TabBar } from "@/components/TabBar"

type Tab = "tokens" | "run_tokens" | "identities" | "integrations"
const TAB_LABELS: Record<Tab, string> = {
  tokens: "Tokens",
  run_tokens: "Run tokens",
  identities: "Identities",
  integrations: "Integrations",
}
const TABS: Tab[] = ["tokens", "run_tokens", "identities", "integrations"]

interface RunToken {
  id: string
  run_id: string
  token_prefix: string | null
  workflow_id: string | null
  workflow_name: string | null
  created_at: string | null
  first_used_at: string | null
  invalidated_at: string | null
}

interface ApiToken {
  id: string
  token_name: string | null
  token_prefix: string | null
  token_type: string
  expires_at: string | null
  last_used_at: string | null
  created_at: string | null
}

interface Identity {
  id: string
  name: string
  provider: string
  token_prefix: string
  created_at: string
  last_used_at: string | null
  environment_id: string | null
  source: string | null
  source_id: string | null
  platform_of_origin: string | null
  owner_user_id: string | null
  agent_role_id: string | null
  lifecycle_state: string | null
  last_certified_at: string | null
  certification_cadence_days: number | null
  risk_tier: string | null
  deactivated_at: string | null
}

const TIER_STYLE: Record<string, { bg: string; fg: string }> = {
  tier_1: { bg: "#dcfce7", fg: "#166534" },
  tier_2: { bg: "#fef3c7", fg: "#92400e" },
  tier_3: { bg: "#fee2e2", fg: "#991b1b" },
}

const LIFECYCLE_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  active:         { bg: "#dcfce7", fg: "#166534", label: "Active" },
  pending_review: { bg: "#fef3c7", fg: "#92400e", label: "Pending review" },
  deactivated:    { bg: "#f3f4f6", fg: "#4b5563", label: "Deactivated" },
  expired:        { bg: "#fee2e2", fg: "#991b1b", label: "Expired" },
}

export default function AgentIdentityPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <WithAuth />
  return <Inner getToken={null} />
}

function WithAuth() {
  const { getToken } = useAuth()
  return <Inner getToken={getToken} />
}

function Inner({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""
  const { authFetch } = useAuthFetch()

  const [tokens, setTokens] = useState<RunToken[]>([])
  const [loading, setLoading] = useState(true)
  const [cliToken, setCliToken] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)
  const [copied, setCopied] = useState(false)

  const [apiTokens, setApiTokens] = useState<ApiToken[]>([])
  const [apiLoading, setApiLoading] = useState(true)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newTokenName, setNewTokenName] = useState("")
  const [newTokenExpiry, setNewTokenExpiry] = useState<string>("never")
  const [creating, setCreating] = useState(false)
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [createdCopied, setCreatedCopied] = useState(false)
  const [revokeId, setRevokeId] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)

  const [identities, setIdentities] = useState<Identity[]>([])
  const [identitiesLoading, setIdentitiesLoading] = useState(true)
  const [savingIdentity, setSavingIdentity] = useState<string | null>(null)

  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = (searchParams?.get("tab") as Tab) || "tokens"
  const [activeTab, setActiveTab] = useState<Tab>(TABS.includes(initialTab) ? initialTab : "tokens")
  const sourceFilter = searchParams?.get("source") || null
  const selectTab = (t: Tab, extraQuery: Record<string, string> = {}) => {
    setActiveTab(t)
    const params = new URLSearchParams({ tab: t, ...extraQuery })
    router.replace(`/agent-identity?${params.toString()}`, { scroll: false })
  }
  const clearSourceFilter = () => {
    router.replace(`/agent-identity?tab=${activeTab}`, { scroll: false })
  }

  // Okta integration (#1036 Phase 2 — Sync UI, #1056 Phase 3b — JWT auth)
  const [okta, setOkta] = useState<{ configured: boolean; domain?: string; token_prefix?: string; last_synced_at?: string | null; last_import?: number | null; last_update?: number | null; last_error?: string | null; issuer?: string | null; audience?: string | null; jwt_auth_enabled?: boolean }>({ configured: false })
  const [oktaLoading, setOktaLoading] = useState(true)
  const [oktaDomainInput, setOktaDomainInput] = useState("")
  const [oktaTokenInput, setOktaTokenInput] = useState("")
  const [oktaSaving, setOktaSaving] = useState(false)
  const [oktaSyncing, setOktaSyncing] = useState(false)
  const [oktaFeedback, setOktaFeedback] = useState<string | null>(null)
  // #1056 — JWT auth config
  const [oktaIssuerInput, setOktaIssuerInput] = useState("")
  const [oktaAudienceInput, setOktaAudienceInput] = useState("")
  const [oktaJwtEnabled, setOktaJwtEnabled] = useState(false)
  const [oktaJwtSaving, setOktaJwtSaving] = useState(false)


  const load = useCallback(async () => {
    if (!workspaceId) return
    try {
      const [tokensRes, installedRes, apiTokensRes, roleRes, identitiesRes] = await Promise.all([
        authFetch(`${API}/workspaces/${workspaceId}/agent-run-tokens`),
        authFetch(`${API}/guard/config/installed?workspace_id=${workspaceId}`),
        authFetch(`${API}/workspaces/${workspaceId}/api-tokens`),
        authFetch(`${API}/projects/${workspaceId}/my-role`),
        authFetch(`${API}/workspaces/${workspaceId}/agent-identities?workspace_id=${workspaceId}`),
      ])
      if (tokensRes.ok) setTokens(await tokensRes.json())
      if (installedRes.ok) {
        const data = await installedRes.json()
        if (data.agent_token) setCliToken(data.agent_token)
      }
      if (apiTokensRes.ok) setApiTokens(await apiTokensRes.json())
      if (roleRes.ok) {
        const data = await roleRes.json()
        setIsAdmin(data.role === "admin")
      }
      if (identitiesRes.ok) setIdentities(await identitiesRes.json())
      setIdentitiesLoading(false)
    } catch {}
    setLoading(false)
    setApiLoading(false)
  }, [workspaceId, authFetch])

  useEffect(() => { load() }, [load])

  function fmt(d: string | null) {
    if (!d) return "—"
    return new Date(d).toLocaleDateString("en-GB", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })
  }

  function maskToken(t: string) {
    // show prefix (cond_agt_XXXX) + mask the rest
    const visible = t.slice(0, 13)
    return visible + "•".repeat(Math.min(t.length - 13, 32))
  }

  function copyToken() {
    if (!cliToken) return
    navigator.clipboard.writeText(cliToken).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  async function handleCreateToken() {
    if (!newTokenName.trim()) return
    setCreating(true)
    const body: Record<string, unknown> = { name: newTokenName.trim() }
    if (newTokenExpiry !== "never") body.expires_in_days = parseInt(newTokenExpiry)
    const res = await authFetch(`${API}/workspaces/${workspaceId}/api-tokens`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    })
    if (res.ok) {
      const data = await res.json()
      setCreatedToken(data.token)
      setNewTokenName("")
      setNewTokenExpiry("never")
      setShowCreateForm(false)
      load()
    }
    setCreating(false)
  }

  async function handleRevoke(id: string) {
    setRevoking(id)
    await authFetch(`${API}/workspaces/${workspaceId}/api-tokens/${id}`, { method: "DELETE" })
    setApiTokens(prev => prev.filter(t => t.id !== id))
    setRevokeId(null)
    setRevoking(null)
  }

  async function patchIdentity(id: string, changes: Partial<Identity>) {
    setSavingIdentity(id)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/agent-identities/${id}?workspace_id=${workspaceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(changes),
      })
      if (res.ok) {
        const updated: Identity = await res.json()
        setIdentities(prev => prev.map(i => i.id === id ? updated : i))
      }
    } finally {
      setSavingIdentity(null)
    }
  }

  async function certifyIdentity(id: string) {
    setSavingIdentity(id)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/agent-identities/${id}/certify?workspace_id=${workspaceId}`, {
        method: "POST",
      })
      if (res.ok) {
        const updated: Identity = await res.json()
        setIdentities(prev => prev.map(i => i.id === id ? updated : i))
      }
    } finally {
      setSavingIdentity(null)
    }
  }

  // Okta integration handlers (#1036 Phase 2)
  const loadOktaConfig = useCallback(async () => {
    if (!workspaceId) return
    setOktaLoading(true)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/integrations/okta/config?workspace_id=${workspaceId}`)
      if (res.ok) {
        const data = await res.json()
        setOkta(data)
        if (data.domain) setOktaDomainInput(data.domain)
        setOktaIssuerInput(data.issuer ?? "")
        setOktaAudienceInput(data.audience ?? "")
        setOktaJwtEnabled(!!data.jwt_auth_enabled)
      }
    } finally {
      setOktaLoading(false)
    }
  }, [workspaceId])
  useEffect(() => { loadOktaConfig() }, [loadOktaConfig])

  async function saveOktaConfig() {
    if (!workspaceId || !oktaDomainInput.trim() || !oktaTokenInput.trim()) return
    setOktaSaving(true); setOktaFeedback(null)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/integrations/okta/config?workspace_id=${workspaceId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain: oktaDomainInput.trim(), token: oktaTokenInput.trim() }),
      })
      if (res.ok) {
        const data = await res.json()
        setOkta(data)
        setOktaTokenInput("")
        setOktaFeedback("Saved.")
      } else {
        setOktaFeedback(`Save failed (HTTP ${res.status})`)
      }
    } finally {
      setOktaSaving(false)
    }
  }

  async function saveOktaJwt() {
    if (!workspaceId) return
    setOktaJwtSaving(true); setOktaFeedback(null)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/integrations/okta/config?workspace_id=${workspaceId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          issuer: oktaIssuerInput.trim() || null,
          audience: oktaAudienceInput.trim() || null,
          jwt_auth_enabled: oktaJwtEnabled,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setOkta(data)
        setOktaFeedback(oktaJwtEnabled ? "JWT auth saved (enabled)." : "JWT auth saved (disabled).")
      } else {
        setOktaFeedback(`JWT save failed (HTTP ${res.status})`)
      }
    } finally {
      setOktaJwtSaving(false)
    }
  }

  async function syncOktaNow() {
    if (!workspaceId) return
    setOktaSyncing(true); setOktaFeedback(null)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/integrations/okta/sync?workspace_id=${workspaceId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),  // omit domain+token to use stored config
      })
      if (res.ok) {
        const data = await res.json()
        setOktaFeedback(`Imported ${data.imported}, updated ${data.updated}${data.errors.length ? `, ${data.errors.length} errors` : ""}.`)
        await loadOktaConfig()
        // also refresh identities so the table updates
        const identitiesRes = await authFetch(`${API}/workspaces/${workspaceId}/agent-identities?workspace_id=${workspaceId}`)
        if (identitiesRes.ok) setIdentities(await identitiesRes.json())
      } else {
        setOktaFeedback(`Sync failed (HTTP ${res.status})`)
      }
    } finally {
      setOktaSyncing(false)
    }
  }

  async function disconnectOkta() {
    if (!workspaceId) return
    if (!confirm("Disconnect Okta? Stored credentials will be deleted. Existing imported identities are kept.")) return
    setOktaSaving(true); setOktaFeedback(null)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/integrations/okta/config?workspace_id=${workspaceId}`, { method: "DELETE" })
      if (res.ok || res.status === 204) {
        setOkta({ configured: false })
        setOktaDomainInput("")
        setOktaTokenInput("")
        setOktaFeedback("Disconnected.")
      }
    } finally {
      setOktaSaving(false)
    }
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: 0 }}>Agent Identity</h1>
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>
            Your CLI token and per-run tokens issued to workflow agents. Guard validates authority at the execution boundary — short-lived run tokens mean permissions expire with the action, not the session. There are no stale approvals.
          </p>
        </div>

        <div style={{ marginBottom: -8 }}>
          <TabBar tabs={TABS} labels={TAB_LABELS} activeTab={activeTab} onSelect={selectTab} />
        </div>

        {/* CLI Developer Token */}
        <div role="tabpanel" id="tabpanel-tokens" aria-labelledby="tab-tokens" hidden={activeTab !== "tokens"} style={{ display: activeTab === "tokens" ? "flex" : "none", flexDirection: "column", gap: 20 }}>
        <div className="card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginBottom: 10 }}>CLI Token</div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Your personal agent token. Set by <code>conduct login</code>. Valid for 8 hours — re-run to rotate.
          </p>
          {loading ? (
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading…</span>
          ) : cliToken ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <code style={{
                fontFamily: "monospace", fontSize: 12,
                background: "var(--bg)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "4px 10px", color: "var(--text-3)",
                letterSpacing: revealed ? "normal" : "0.05em",
                userSelect: revealed ? "text" : "none",
              }}>
                {revealed ? cliToken : maskToken(cliToken)}
              </code>
              <button
                onClick={() => setRevealed(r => !r)}
                style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-muted)", cursor: "pointer" }}
              >
                {revealed ? "Hide" : "Reveal"}
              </button>
              {revealed && (
                <button
                  onClick={copyToken}
                  style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: copied ? "var(--ok)" : "var(--text-muted)", cursor: "pointer" }}
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
              )}
            </div>
          ) : (
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              No CLI token found. Run <code>conduct login</code> to authenticate.
            </span>
          )}
        </div>

        {/* API Tokens */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>API Tokens</div>
            {isAdmin && !showCreateForm && (
              <button onClick={() => setShowCreateForm(true)} className="btn btn-sm btn-primary">+ Create token</button>
            )}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Long-lived tokens for external apps and agents calling Guard via MCP. Admin-managed.
          </p>

          {/* One-time reveal after creation */}
          {createdToken && (
            <div className="card" style={{ padding: "12px 16px", marginBottom: 12, background: "var(--ok-bg)", border: "1px solid var(--ok-bd)" }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)", margin: "0 0 8px" }}>Token created — copy it now. It won&apos;t be shown again.</p>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <code style={{ fontFamily: "monospace", fontSize: 12, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 10px", flex: 1 }}>
                  {createdToken}
                </code>
                <button
                  onClick={() => { navigator.clipboard.writeText(createdToken); setCreatedCopied(true); setTimeout(() => setCreatedCopied(false), 2000) }}
                  style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: createdCopied ? "var(--ok)" : "var(--text-muted)", cursor: "pointer" }}
                >{createdCopied ? "Copied!" : "Copy"}</button>
                <button onClick={() => setCreatedToken(null)} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-muted)", cursor: "pointer" }}>Dismiss</button>
              </div>
            </div>
          )}

          {/* Create form */}
          {showCreateForm && (
            <div className="card" style={{ padding: "12px 16px", marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Token name</label>
                  <input
                    type="text" value={newTokenName} onChange={e => setNewTokenName(e.target.value)}
                    placeholder="e.g. fraud-detection-agent"
                    style={{ width: "100%", height: 32, border: "1px solid var(--border)", borderRadius: 6, padding: "0 10px", fontSize: 12, background: "var(--surface)", color: "var(--text)" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Expires</label>
                  <select value={newTokenExpiry} onChange={e => setNewTokenExpiry(e.target.value)}
                    style={{ height: 32, border: "1px solid var(--border)", borderRadius: 6, padding: "0 8px", fontSize: 12, background: "var(--surface)", color: "var(--text)" }}>
                    <option value="never">Never</option>
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="365">1 year</option>
                  </select>
                </div>
                <button onClick={handleCreateToken} disabled={!newTokenName.trim() || creating} className="btn btn-sm btn-primary">
                  {creating ? "Creating\u2026" : "Create"}
                </button>
                <button onClick={() => setShowCreateForm(false)} className="btn btn-sm btn-ghost">Cancel</button>
              </div>
            </div>
          )}

          {/* Token list */}
          <div className="card" style={{ overflow: "hidden" }}>
            {apiLoading ? (
              <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading\u2026</div>
            ) : apiTokens.length === 0 ? (
              <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                No API tokens yet.{isAdmin ? " Create one to let external apps call Guard." : " Ask an admin to create one."}
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Name</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Prefix</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Expires</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Last used</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Status</th>
                    {isAdmin && <th style={{ padding: "9px 16px" }} />}
                  </tr>
                </thead>
                <tbody>
                  {apiTokens.map(t => {
                    const expired = t.expires_at ? new Date(t.expires_at) < new Date() : false
                    return (
                      <tr key={t.id} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 16px", fontWeight: 500 }}>{t.token_name ?? "\u2014"}</td>
                        <td style={{ padding: "8px 16px" }}>
                          <code style={{ fontSize: 11.5, color: "var(--text-3)", background: "var(--bg)", padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)" }}>
                            {t.token_prefix ? `${t.token_prefix}...` : "\u2014"}
                          </code>
                        </td>
                        <td style={{ padding: "8px 16px", color: expired ? "var(--err)" : "var(--text-muted)" }}>
                          {t.expires_at ? fmt(t.expires_at) : "Never"}
                        </td>
                        <td style={{ padding: "8px 16px", color: "var(--text-muted)" }}>{fmt(t.last_used_at)}</td>
                        <td style={{ padding: "8px 16px" }}>
                          {expired
                            ? <span style={{ color: "var(--err)", fontSize: 11.5 }}>Expired</span>
                            : <span style={{ color: "var(--ok)", fontWeight: 600, fontSize: 11.5 }}>Active</span>
                          }
                        </td>
                        {isAdmin && (
                          <td style={{ padding: "8px 16px", textAlign: "right" }}>
                            {revokeId === t.id ? (
                              <span style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                                <button onClick={() => handleRevoke(t.id)} disabled={revoking === t.id}
                                  style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid var(--err)", background: "var(--err)", color: "#fff", cursor: "pointer" }}>
                                  {revoking === t.id ? "\u2026" : "Confirm"}
                                </button>
                                <button onClick={() => setRevokeId(null)} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-muted)", cursor: "pointer" }}>Cancel</button>
                              </span>
                            ) : (
                              <button onClick={() => setRevokeId(t.id)}
                                style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--err)", cursor: "pointer" }}>
                                Revoke
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        </div>{/* end tabpanel tokens */}

        {/* Run Tokens */}
        <div role="tabpanel" id="tabpanel-run_tokens" aria-labelledby="tab-run_tokens" hidden={activeTab !== "run_tokens"} style={{ display: activeTab === "run_tokens" ? "block" : "none" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>Run Tokens</div>
          <div className="card" style={{ overflow: "hidden" }}>
            {loading ? (
              <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading...</div>
            ) : tokens.length === 0 ? (
              <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                No run tokens yet. Trigger a workflow to see tokens here.
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Token</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Workflow</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Run</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Minted</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>First used</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.map(rt => (
                    <tr key={rt.id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 16px" }}>
                        <code className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", background: "var(--bg)", padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)" }}>
                          {rt.token_prefix ? `${rt.token_prefix}...` : "—"}
                        </code>
                      </td>
                      <td style={{ padding: "8px 16px" }}>
                        {rt.workflow_id
                          ? <a href={`/workflows/${rt.workflow_id}`} style={{ color: "var(--text)", textDecoration: "none" }} onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")} onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}>{rt.workflow_name ?? "—"}</a>
                          : <span style={{ color: "var(--text)" }}>{rt.workflow_name ?? "—"}</span>
                        }
                      </td>
                      <td style={{ padding: "8px 16px" }}>
                        <a href={rt.workflow_id ? `/workflows/${rt.workflow_id}/runs/${rt.run_id}` : `/runs/${rt.run_id}`} style={{ color: "var(--accent)", textDecoration: "none", fontFamily: "monospace", fontSize: 11.5 }}>
                          {rt.run_id.slice(0, 8)}
                        </a>
                      </td>
                      <td style={{ padding: "8px 16px", color: "var(--text-muted)" }}>{fmt(rt.created_at)}</td>
                      <td style={{ padding: "8px 16px", color: rt.first_used_at ? "var(--ok)" : "var(--text-muted)" }}>
                        {rt.first_used_at ? fmt(rt.first_used_at) : "—"}
                      </td>
                      <td style={{ padding: "8px 16px" }}>
                        {rt.invalidated_at
                          ? <span style={{ color: "var(--text-muted)", fontSize: 11.5 }}>Invalidated</span>
                          : <span style={{ color: "var(--ok)", fontWeight: 600, fontSize: 11.5 }}>Active</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            Run tokens are single-use and workspace-scoped. They are invalidated automatically when their run completes. Every run mints fresh credentials — authority validation happens at the execution boundary on every action.
          </p>
        </div>

        {/* Okta integration — #1036 Phase 2 */}
        <div role="tabpanel" id="tabpanel-integrations" aria-labelledby="tab-integrations" hidden={activeTab !== "integrations"} style={{ display: activeTab === "integrations" ? "block" : "none" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>Okta integration</div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Pull agent identities from your Okta tenant into Conduct as Guard principals. Okta owns auth; Conduct governs what each identity is allowed to do.
          </p>
          <div className="card" style={{ padding: "16px 20px" }}>
            {oktaLoading ? (
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading…</div>
            ) : okta.configured ? (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
                  <div style={{ fontSize: 12, color: "var(--text-2)" }}>
                    <div><span style={{ color: "var(--text-muted)" }}>Domain:</span> <code>{okta.domain}</code></div>
                    <div style={{ marginTop: 2 }}><span style={{ color: "var(--text-muted)" }}>Token:</span> <code>{okta.token_prefix}</code> (stored encrypted)</div>
                    {okta.last_synced_at ? (
                      <div style={{ marginTop: 6, fontSize: 11 }}>
                        <span style={{ color: "var(--text-muted)" }}>Last sync:</span> {new Date(okta.last_synced_at).toLocaleString()} ·{" "}
                        <button
                          onClick={() => selectTab("identities", { source: "okta" })}
                          title="View Okta-sourced identities"
                          style={{ background: "none", border: "none", padding: 0, color: "var(--accent-text)", fontSize: 11, cursor: "pointer", textDecoration: "underline" }}
                        >
                          imported {okta.last_import ?? 0}
                        </button>
                        {" · "}
                        <button
                          onClick={() => selectTab("identities", { source: "okta" })}
                          title="View Okta-sourced identities"
                          style={{ background: "none", border: "none", padding: 0, color: "var(--accent-text)", fontSize: 11, cursor: "pointer", textDecoration: "underline" }}
                        >
                          updated {okta.last_update ?? 0}
                        </button>
                      </div>
                    ) : (
                      <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>Never synced.</div>
                    )}
                    {okta.last_error && (
                      <div style={{ marginTop: 6, fontSize: 11, color: "var(--err)" }}>Last error: {okta.last_error}</div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={syncOktaNow}
                      disabled={oktaSyncing || oktaSaving}
                      className="btn btn-primary btn-sm"
                    >
                      {oktaSyncing ? "Syncing…" : "Sync now"}
                    </button>
                    <button
                      onClick={disconnectOkta}
                      disabled={oktaSyncing || oktaSaving}
                      style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 12, cursor: "pointer" }}
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>Update stored credentials:</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      type="text"
                      value={oktaDomainInput}
                      onChange={e => setOktaDomainInput(e.target.value)}
                      placeholder="dev-XXXXXX.okta.com"
                      style={{ flex: "1 1 220px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <input
                      type="password"
                      value={oktaTokenInput}
                      onChange={e => setOktaTokenInput(e.target.value)}
                      placeholder="New Okta API token (SSWS)"
                      style={{ flex: "2 1 260px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <button
                      onClick={saveOktaConfig}
                      disabled={oktaSaving || !oktaDomainInput.trim() || !oktaTokenInput.trim()}
                      className="btn btn-sm"
                      style={{ padding: "6px 12px", fontSize: 12 }}
                    >
                      {oktaSaving ? "Saving…" : "Save"}
                    </button>
                  </div>
                </div>
                {/* JWT authentication (#1056) — Phase 3b runtime enforcement */}
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      JWT authentication — accept Okta-signed tokens as Guard principals
                    </div>
                    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-2)", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={oktaJwtEnabled}
                        onChange={e => setOktaJwtEnabled(e.target.checked)}
                        disabled={oktaJwtSaving}
                      />
                      Enabled
                    </label>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      type="text"
                      value={oktaIssuerInput}
                      onChange={e => setOktaIssuerInput(e.target.value)}
                      placeholder={okta.domain ? `https://${okta.domain}/oauth2/default` : "https://{domain}/oauth2/default"}
                      style={{ flex: "1 1 260px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <input
                      type="text"
                      value={oktaAudienceInput}
                      onChange={e => setOktaAudienceInput(e.target.value)}
                      placeholder="api://default"
                      style={{ flex: "1 1 160px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <button
                      onClick={saveOktaJwt}
                      disabled={oktaJwtSaving}
                      className="btn btn-sm"
                      style={{ padding: "6px 12px", fontSize: 12 }}
                    >
                      {oktaJwtSaving ? "Saving…" : "Save JWT config"}
                    </button>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>
                    Configure the OAuth authorization server in your Okta admin, then set the issuer + audience here and toggle Enabled.
                  </div>
                </div>
              </>
            ) : (
              <div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
                  Not configured. Enter your Okta domain and an admin API token to start pulling apps into Guard as agent identities.
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input
                    type="text"
                    value={oktaDomainInput}
                    onChange={e => setOktaDomainInput(e.target.value)}
                    placeholder="dev-XXXXXX.okta.com"
                    style={{ flex: "1 1 220px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                  />
                  <input
                    type="password"
                    value={oktaTokenInput}
                    onChange={e => setOktaTokenInput(e.target.value)}
                    placeholder="Okta API token (SSWS)"
                    style={{ flex: "2 1 260px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                  />
                  <button
                    onClick={saveOktaConfig}
                    disabled={oktaSaving || !oktaDomainInput.trim() || !oktaTokenInput.trim()}
                    className="btn btn-primary btn-sm"
                    style={{ padding: "6px 12px", fontSize: 12 }}
                  >
                    {oktaSaving ? "Saving…" : "Save & Connect"}
                  </button>
                </div>
                <p style={{ fontSize: 10.5, color: "var(--text-muted)", margin: "8px 0 0" }}>
                  Create a token in Okta admin: Security → API → Tokens → Create Token. The token is stored encrypted and never returned by the API.
                </p>
              </div>
            )}
            {oktaFeedback && (
              <div style={{ marginTop: 10, fontSize: 11, color: oktaFeedback.toLowerCase().includes("fail") ? "var(--err)" : "var(--ok)" }}>
                {oktaFeedback}
              </div>
            )}
          </div>
        </div>

        {/* Agent identities — Phase 3 of #1037 */}
        <div role="tabpanel" id="tabpanel-identities" aria-labelledby="tab-identities" hidden={activeTab !== "identities"} style={{ display: activeTab === "identities" ? "block" : "none" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>Agent identities</div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Every agent has an accountable owner, a risk tier, a lifecycle state, and a certification cadence. Tier drives what the agent is allowed to do; lifecycle drives whether it can act at all. Deactivating an identity revokes its tokens on the next check.
          </p>
          {sourceFilter && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, fontSize: 12, color: "var(--text-2)" }}>
              <span style={{ color: "var(--text-muted)" }}>Filter:</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 8px", borderRadius: 4, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                Source: {sourceFilter}
                <button
                  onClick={clearSourceFilter}
                  aria-label="Clear filter"
                  style={{ background: "none", border: "none", padding: 0, color: "var(--text-muted)", cursor: "pointer", fontSize: 14, lineHeight: 1 }}
                >
                  ×
                </button>
              </span>
              <span style={{ color: "var(--text-muted)" }}>({identities.filter(i => i.source === sourceFilter).length} of {identities.length})</span>
            </div>
          )}
          <div className="card" style={{ overflow: "hidden" }}>
            {identitiesLoading ? (
              <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>Loading identities…</div>
            ) : (() => {
              const visibleIdentities = sourceFilter ? identities.filter(i => i.source === sourceFilter) : identities
              if (visibleIdentities.length === 0) {
                return <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>{sourceFilter ? `No identities with source “${sourceFilter}”.` : "No agent identities yet."}</div>
              }
              return (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Name</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Source</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Owner</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Tier</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Lifecycle</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Last certified</th>
                    <th style={{ padding: "8px 12px" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleIdentities.map(id => {
                    const tier = TIER_STYLE[id.risk_tier ?? ""] ?? { bg: "var(--surface-2)", fg: "var(--text-muted)" }
                    const lc   = LIFECYCLE_STYLE[id.lifecycle_state ?? ""] ?? { bg: "var(--surface-2)", fg: "var(--text-muted)", label: id.lifecycle_state ?? "—" }
                    const busy = savingIdentity === id.id
                    return (
                      <tr key={id.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 12px" }}>
                          <div style={{ fontWeight: 500, color: "var(--text)" }}>{id.name}</div>
                          <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--text-muted)" }}>{id.token_prefix?.startsWith("okta_import") ? "external identity" : id.token_prefix}</div>
                        </td>
                        <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-2)" }}>
                          {id.source ?? "conduct"}
                          {id.platform_of_origin && <span style={{ color: "var(--text-muted)" }}> · {id.platform_of_origin}</span>}
                        </td>
                        <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-2)" }}>
                          {id.owner_user_id ?? <span style={{ color: "var(--text-muted)" }}>unassigned</span>}
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          <select
                            value={id.risk_tier ?? "tier_1"}
                            disabled={busy || !isAdmin}
                            onChange={e => patchIdentity(id.id, { risk_tier: e.target.value })}
                            style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)", background: tier.bg, color: tier.fg }}
                          >
                            <option value="tier_1">Tier 1</option>
                            <option value="tier_2">Tier 2</option>
                            <option value="tier_3">Tier 3</option>
                          </select>
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          <select
                            value={id.lifecycle_state ?? "active"}
                            disabled={busy || !isAdmin}
                            onChange={e => patchIdentity(id.id, { lifecycle_state: e.target.value })}
                            style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)", background: lc.bg, color: lc.fg }}
                          >
                            <option value="active">Active</option>
                            <option value="pending_review">Pending review</option>
                            <option value="deactivated">Deactivated</option>
                            <option value="expired">Expired</option>
                          </select>
                        </td>
                        <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-muted)" }}>
                          {id.last_certified_at
                            ? new Date(id.last_certified_at).toLocaleDateString()
                            : <span>never</span>}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "right" }}>
                          {isAdmin && (
                            <button
                              onClick={() => certifyIdentity(id.id)}
                              disabled={busy}
                              style={{ fontSize: 10, padding: "3px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text-2)", cursor: busy ? "not-allowed" : "pointer" }}
                            >
                              {busy ? "…" : "Certify"}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              )
            })()}
          </div>
          <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "8px 0 0" }}>
            Tier 3 agents are the strictest (regulated decisions, requires human oversight); Tier 1 is drafting-adjacent (reversible, low blast radius). Only workspace admins can change tier, lifecycle, or certify.
          </p>
        </div>
      </div>
    </AppShell>
  )
}
