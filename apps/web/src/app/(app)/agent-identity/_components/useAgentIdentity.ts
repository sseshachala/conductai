"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { TABS, type Tab, type RunToken, type ApiToken, type Identity, type LensSession } from "./shared"

export function useAgentIdentity() {
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
  const [identitiesWorkspace, setIdentitiesWorkspace] = useState("")
  const currentWorkspace = useRef(workspaceId)
  currentWorkspace.current = workspaceId

  // Lens Sessions (#1218 Step 3b.6)
  const [lensSessions, setLensSessions] = useState<LensSession[]>([])
  const [lensSessionsLoading, setLensSessionsLoading] = useState(true)
  const [lensIncludeExpired, setLensIncludeExpired] = useState(false)
  const [revokingLensSessionId, setRevokingLensSessionId] = useState<string | null>(null)
  const [savingIdentity, setSavingIdentity] = useState<string | null>(null)

  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = (searchParams?.get("tab") as Tab) || "tokens"
  const [activeTab, setActiveTab] = useState<Tab>(TABS.includes(initialTab) ? initialTab : "tokens")
  const [integrationTab, setIntegrationTab] = useState<"okta" | "oidc">(searchParams.get("integration") === "oidc" ? "oidc" : "okta")
  const sourceFilter = searchParams?.get("source") || null
  // #1252 — deep-link support: click a Lens session's cond_agt_lens_* → land
  // on the Identities tab with ?id=<uuid> and highlight+scroll to the row.
  const highlightId = searchParams?.get("id") || null
  const [multipleSessions, setMultipleSessions] = useState(false)
  const sessionType = searchParams?.get("session_type")
  const [authenticationView, setAuthenticationView] = useState(sessionType === "authentication")
  useEffect(() => { setAuthenticationView(sessionType === "authentication") }, [sessionType])
  const sessionAgents = authenticationView ? identities : identities.filter(identity => (identity.recorded_session_count ?? 0) >= (multipleSessions ? 2 : 1))
  const selectedAgent = identities.find(identity => identity.id === highlightId)
  const sessionIdentity = selectedAgent ?? (highlightId ? null : sessionAgents[0])
  const sessionOptions = selectedAgent && !sessionAgents.some(identity => identity.id === selectedAgent.id) ? [selectedAgent, ...sessionAgents] : sessionAgents
  useEffect(() => {
    if (activeTab !== "identities" || !highlightId) return
    const row = document.getElementById(`identity-row-${highlightId}`)
    if (row) row.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [activeTab, highlightId])
  const selectTab = (t: Tab, extraQuery: Record<string, string> = {}) => {
    setActiveTab(t)
    if (t === "agent_sessions") setAuthenticationView(extraQuery.session_type === "authentication")
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


  // Each request unblocks its own consumer — no Promise.all barrier so the
  // Tokens tab paints as soon as api-tokens + installed return, without
  // waiting on agent-run-tokens or agent-identities (which scan history and
  // dominate p95).
  const load = useCallback(() => {
    if (!workspaceId) return
    const w = workspaceId
    authFetch(`${API}/workspaces/${w}/api-tokens`)
      .then(r => r.ok ? r.json() : []).then(setApiTokens)
      .catch(() => {}).finally(() => setApiLoading(false))
    authFetch(`${API}/guard/config/installed?workspace_id=${w}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.agent_token) setCliToken(d.agent_token) })
      .catch(() => {}).finally(() => setLoading(false))
    authFetch(`${API}/projects/${w}/my-role`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setIsAdmin(d?.role === "admin"))
      .catch(() => {})
    authFetch(`${API}/workspaces/${w}/agent-run-tokens`)
      .then(r => r.ok ? r.json() : []).then(setTokens)
      .catch(() => {})
    authFetch(`${API}/workspaces/${w}/agent-identities?workspace_id=${w}`)
      .then(r => r.ok ? r.json() : []).then(rows => {
        if (currentWorkspace.current !== w) return
        setIdentities(rows)
        setIdentitiesWorkspace(w)
      })
      .catch(() => {}).finally(() => { if (currentWorkspace.current === w) setIdentitiesLoading(false) })
  }, [workspaceId, authFetch])

  useEffect(() => { load() }, [load])

  // Lens Sessions loader (#1218 Step 3b.6)
  const loadLensSessions = useCallback(async () => {
    if (!workspaceId) return
    setLensSessionsLoading(true)
    try {
      const qs = lensIncludeExpired ? "?include_expired=true" : ""
      const res = await authFetch(`${API}/glens/lens-sessions${qs}`)
      if (res.ok) setLensSessions(await res.json())
    } catch {}
    setLensSessionsLoading(false)
  }, [workspaceId, authFetch, lensIncludeExpired])

  useEffect(() => {
    if (activeTab === "lens_sessions") loadLensSessions()
  }, [activeTab, loadLensSessions])

  async function revokeLensSession(id: string) {
    setRevokingLensSessionId(id)
    try {
      const res = await authFetch(`${API}/glens/lens-sessions/${id}/revoke`, { method: "POST" })
      if (res.ok) {
        const data = await res.json()
        setLensSessions(prev => prev.map(s => s.id === id ? { ...s, token_revoked_at: data.revoked_at, is_active: false } : s))
      }
    } catch {}
    setRevokingLensSessionId(null)
  }

  function fmt(d: string | null) {
    if (!d) return "—"
    // Hydration-safe: deterministic UTC. Server TZ vs client TZ would otherwise
    // trigger React error #418 (text mismatch) on every render.
    return d.slice(0, 16).replace("T", " ") + " UTC"
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

  return {
    activeWorkspace,
    workspaceId,
    authFetch,
    tokens,
    setTokens,
    loading,
    setLoading,
    cliToken,
    setCliToken,
    revealed,
    setRevealed,
    copied,
    setCopied,
    apiTokens,
    setApiTokens,
    apiLoading,
    setApiLoading,
    showCreateForm,
    setShowCreateForm,
    newTokenName,
    setNewTokenName,
    newTokenExpiry,
    setNewTokenExpiry,
    creating,
    setCreating,
    createdToken,
    setCreatedToken,
    createdCopied,
    setCreatedCopied,
    revokeId,
    setRevokeId,
    revoking,
    setRevoking,
    isAdmin,
    setIsAdmin,
    identities,
    setIdentities,
    identitiesLoading,
    setIdentitiesLoading,
    identitiesWorkspace,
    setIdentitiesWorkspace,
    currentWorkspace,
    lensSessions,
    setLensSessions,
    lensSessionsLoading,
    setLensSessionsLoading,
    lensIncludeExpired,
    setLensIncludeExpired,
    revokingLensSessionId,
    setRevokingLensSessionId,
    savingIdentity,
    setSavingIdentity,
    router,
    searchParams,
    initialTab,
    activeTab,
    setActiveTab,
    integrationTab,
    setIntegrationTab,
    sourceFilter,
    highlightId,
    multipleSessions,
    setMultipleSessions,
    sessionType,
    authenticationView,
    setAuthenticationView,
    sessionAgents,
    selectedAgent,
    sessionIdentity,
    sessionOptions,
    selectTab,
    clearSourceFilter,
    okta,
    setOkta,
    oktaLoading,
    setOktaLoading,
    oktaDomainInput,
    setOktaDomainInput,
    oktaTokenInput,
    setOktaTokenInput,
    oktaSaving,
    setOktaSaving,
    oktaSyncing,
    setOktaSyncing,
    oktaFeedback,
    setOktaFeedback,
    oktaIssuerInput,
    setOktaIssuerInput,
    oktaAudienceInput,
    setOktaAudienceInput,
    oktaJwtEnabled,
    setOktaJwtEnabled,
    oktaJwtSaving,
    setOktaJwtSaving,
    load,
    loadLensSessions,
    revokeLensSession,
    fmt,
    maskToken,
    copyToken,
    handleCreateToken,
    handleRevoke,
    patchIdentity,
    certifyIdentity,
    loadOktaConfig,
    saveOktaConfig,
    saveOktaJwt,
    syncOktaNow,
    disconnectOkta,
  }
}

export type AgentIdentityState = ReturnType<typeof useAgentIdentity>
