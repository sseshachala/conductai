"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard, environments } from "@/lib/api"

type Profile = Record<string, any> & { id?: string }

const PROVIDERS = ["anthropic", "openai", "perplexity", "together"]

export default function GatewayProfileSettings({ workspaceId, isAdmin }: { workspaceId: string; isAdmin: boolean }) {
  const { authFetch } = useAuthFetch()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [provider, setProvider] = useState("anthropic")
  const [protocol, setProtocol] = useState("anthropic")
  const [name, setName] = useState("default")
  const [upstream, setUpstream] = useState("")
  const [credentialRef, setCredentialRef] = useState("")
  const [litellmBase, setLitellmBase] = useState("")
  const [litellmVersion, setLitellmVersion] = useState("")
  const [litellmProvider, setLitellmProvider] = useState("")
  const [dropParams, setDropParams] = useState(false)
  const [requestTimeout, setRequestTimeout] = useState("")
  const [numRetries, setNumRetries] = useState("0")
  const [deployments, setDeployments] = useState("{}")
  const [advanced, setAdvanced] = useState("{}")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [vaults, setVaults] = useState<Array<{ id: string; name: string }>>([])
  const [pushVaultId, setPushVaultId] = useState("")
  const [pushing, setPushing] = useState(false)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const rows = await guard.gatewayProfiles.list(authFetch, workspaceId)
      const envRows = await environments.list(authFetch)
      setVaults(envRows)
      setPushVaultId(current => current || envRows[0]?.id || "")
      const next = rows[0] as Profile | undefined
      if (next) {
        setProfile(next)
        setName(next.name || "default")
        setProvider(next.provider || "anthropic")
        setProtocol(next.protocol || "anthropic")
        setUpstream(next.upstream_url || "")
        setCredentialRef(next.credential_ref || "")
        setLitellmBase(next.litellm?.api_base || "")
        setLitellmVersion(next.litellm?.api_version || "")
        setLitellmProvider(next.litellm?.custom_llm_provider || "")
        setDropParams(!!next.litellm?.drop_params)
        setRequestTimeout(next.litellm?.request_timeout_seconds?.toString() || "")
        setNumRetries(next.litellm?.num_retries?.toString() || "0")
        setDeployments(JSON.stringify(Object.fromEntries((next.deployments || []).map((d: any) => [d.alias, d.model])), null, 2))
        setAdvanced(JSON.stringify({ reliability: next.reliability, limits: next.limits, streaming: next.streaming, provider_options: next.provider_options }, null, 2))
      }
      setError("")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load gateway")
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => { load() }, [load])

  const parsed = useMemo(() => {
    try {
      const tiers = JSON.parse(deployments)
      const extra = JSON.parse(advanced)
      if (!tiers || Array.isArray(tiers) || typeof tiers !== "object") throw new Error("Model aliases must be a JSON object")
      if (!extra || Array.isArray(extra) || typeof extra !== "object") throw new Error("Advanced options must be a JSON object")
      return { tiers, extra, error: "" }
    } catch (e) {
      return { tiers: {}, extra: {}, error: e instanceof Error ? e.message : "Invalid JSON" }
    }
  }, [deployments, advanced])

  function body() {
    return {
      name, provider, protocol, upstream_url: upstream || null,
      credential_ref: credentialRef || null,
      deployments: Object.entries(parsed.tiers).map(([alias, model]) => ({ alias, model })),
      routing: { strategy: "ordered", fallback_aliases: [] },
      reliability: parsed.extra.reliability || {},
      limits: parsed.extra.limits || {},
      streaming: parsed.extra.streaming || {},
      litellm: {
        api_base: litellmBase || null,
        api_version: litellmVersion || null,
        custom_llm_provider: litellmProvider || null,
        drop_params: dropParams,
        request_timeout_seconds: requestTimeout ? Number(requestTimeout) : null,
        num_retries: Number(numRetries || 0),
        stream_options: parsed.extra.stream_options || {},
      },
      provider_options: parsed.extra.provider_options || {},
    }
  }

  async function save() {
    if (!isAdmin || parsed.error) return
    setSaving(true); setError(""); setMessage("")
    try {
      const result = profile?.id
        ? await guard.gatewayProfiles.update(authFetch, workspaceId, profile.id, body())
        : await guard.gatewayProfiles.create(authFetch, workspaceId, body())
      setProfile(await result.json())
      setMessage("Gateway saved")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally { setSaving(false) }
  }

  async function validate() {
    if (parsed.error) return
    try {
      await guard.gatewayProfiles.validate(authFetch, workspaceId, body())
      setMessage("Configuration is valid")
      setError("")
    } catch (e) { setError(e instanceof Error ? e.message : "Validation failed") }
  }

  async function pushToVault() {
    if (!profile?.id || !pushVaultId) return
    setPushing(true); setError(""); setMessage("")
    try {
      const result = await guard.gatewayProfiles.push(authFetch, workspaceId, profile.id, pushVaultId)
      if (!result.ok) throw new Error(`Vault push failed (${result.status})`)
      const data = await result.json()
      setMessage(data.credential_resolved ? "Gateway pushed to vault" : "Gateway URL pushed; no credential resolved")
    } catch (e) { setError(e instanceof Error ? e.message : "Vault push failed") }
    finally { setPushing(false) }
  }

  if (loading) return <div style={{ height: 180, background: "var(--surface-2)", borderRadius: 8 }} />

  const inputStyle = { width: "100%", padding: "9px 11px", border: "1px solid var(--border)", borderRadius: 7, background: "var(--surface)", color: "var(--text)", fontSize: 13 }
  return (
    <div style={{ maxWidth: 700, display: "flex", flexDirection: "column", gap: 18 }}>
      <section>
        <h3 style={{ margin: 0, fontSize: 15 }}>Gateway profile</h3>
        <p style={{ margin: "5px 0 0", color: "var(--text-3)", fontSize: 12.5 }}>One configuration for proxy, workflows, Lens, and local CLI routing.</p>
      </section>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <label style={{ fontSize: 12 }}>Name<input value={name} disabled={!isAdmin} onChange={e => setName(e.target.value)} style={inputStyle} /></label>
        <label style={{ fontSize: 12 }}>Provider<select value={provider} disabled={!isAdmin} onChange={e => { setProvider(e.target.value); setProtocol(e.target.value === "anthropic" ? "anthropic" : "openai_compatible") }} style={inputStyle}>{PROVIDERS.map(p => <option key={p}>{p}</option>)}</select></label>
      </div>
      <label style={{ fontSize: 12 }}>Upstream URL<input value={upstream} disabled={!isAdmin} onChange={e => setUpstream(e.target.value)} placeholder="https://api.example.com/v1" style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>Vault credential reference<input value={credentialRef} disabled={!isAdmin} onChange={e => setCredentialRef(e.target.value)} placeholder="vault://providers/anthropic" style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>Model aliases<textarea value={deployments} disabled={!isAdmin} onChange={e => setDeployments(e.target.value)} rows={5} spellCheck={false} style={{ ...inputStyle, fontFamily: "monospace", resize: "vertical" }} /></label>
      <details>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600 }}>LiteLLM transport options</summary>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 10 }}>
          <label style={{ fontSize: 12 }}>API base<input value={litellmBase} disabled={!isAdmin} onChange={e => setLitellmBase(e.target.value)} placeholder="https://litellm.example.com/v1" style={inputStyle} /></label>
          <label style={{ fontSize: 12 }}>API version<input value={litellmVersion} disabled={!isAdmin} onChange={e => setLitellmVersion(e.target.value)} placeholder="2025-01-01" style={inputStyle} /></label>
          <label style={{ fontSize: 12 }}>Custom provider<input value={litellmProvider} disabled={!isAdmin} onChange={e => setLitellmProvider(e.target.value)} placeholder="openai" style={inputStyle} /></label>
          <label style={{ fontSize: 12 }}>Request timeout (seconds)<input type="number" min="1" max="600" value={requestTimeout} disabled={!isAdmin} onChange={e => setRequestTimeout(e.target.value)} placeholder="60" style={inputStyle} /></label>
          <label style={{ fontSize: 12 }}>Retries<input type="number" min="0" max="5" value={numRetries} disabled={!isAdmin} onChange={e => setNumRetries(e.target.value)} style={inputStyle} /></label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, paddingTop: 20 }}><input type="checkbox" checked={dropParams} disabled={!isAdmin} onChange={e => setDropParams(e.target.checked)} /> Drop unsupported parameters</label>
        </div>
      </details>
      <details>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600 }}>Advanced routing and provider options</summary>
        <textarea value={advanced} disabled={!isAdmin} onChange={e => setAdvanced(e.target.value)} rows={8} spellCheck={false} style={{ ...inputStyle, marginTop: 10, fontFamily: "monospace", resize: "vertical" }} />
      </details>
      {parsed.error && <p style={{ margin: 0, color: "var(--err)", fontSize: 12 }}>{parsed.error}</p>}
      {error && <p style={{ margin: 0, color: "var(--err)", fontSize: 12 }}>{error}</p>}
      {message && <p style={{ margin: 0, color: "var(--green)", fontSize: 12 }}>{message}</p>}
      {isAdmin && <div style={{ display: "flex", gap: 8 }}><button className="btn btn-primary btn-sm" disabled={saving || !!parsed.error} onClick={save}>{saving ? "Saving…" : "Save gateway"}</button><button className="btn btn-ghost btn-sm" disabled={!!parsed.error} onClick={validate}>Validate</button></div>}
      {isAdmin && profile?.id && <section style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>Push to vault</h3>
        <p style={{ margin: "5px 0 10px", color: "var(--text-3)", fontSize: 12 }}>Copy this profile&apos;s upstream URL and Vault-managed credential into an environment.</p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select value={pushVaultId} onChange={e => setPushVaultId(e.target.value)} style={{ ...inputStyle, maxWidth: 300 }}>
            {vaults.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
          <button className="btn btn-ghost btn-sm" disabled={pushing || !pushVaultId} onClick={pushToVault}>{pushing ? "Pushing…" : "Push"}</button>
        </div>
      </section>}
    </div>
  )
}
