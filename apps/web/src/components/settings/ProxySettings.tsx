"use client"

import { useState, useEffect } from "react"

const API = process.env.NEXT_PUBLIC_API_URL ?? ""

interface Props {
  workspaceId: string
  getToken: (() => Promise<string | null>) | null
}

interface Env {
  id: string
  name: string
}

export default function ProxySettings({ workspaceId, getToken }: Props) {
  const [envs, setEnvs]                     = useState<Env[]>([])
  const [envId, setEnvId]                   = useState("")
  const [proxyUrl, setProxyUrl]             = useState("")
  const [upstream, setUpstream]             = useState("")
  const [upstreamKey, setUpstreamKey]       = useState("")
  const [hasUpstreamKey, setHasUpstreamKey] = useState(false)
  const [saving, setSaving]                 = useState(false)
  const [saved, setSaved]                   = useState(false)
  const [copied, setCopied]                 = useState(false)

  async function headers(): Promise<Record<string, string>> {
    const h: Record<string, string> = { "X-Workspace-ID": workspaceId }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    return h
  }

  // Load environments on mount, auto-select first
  useEffect(() => {
    if (!workspaceId) return
    ;(async () => {
      const h = await headers()
      const r = await fetch(`${API}/environments`, { headers: h })
      if (r.ok) {
        const data: Env[] = await r.json()
        setEnvs(data)
        if (data.length > 0) setEnvId(data[0].id)
      }
    })()
  }, [workspaceId])

  // Load proxy config when environment changes
  useEffect(() => {
    if (!workspaceId || !envId) return
    ;(async () => {
      const h = await headers()
      const r = await fetch(`${API}/guard/proxy-config?environment_id=${envId}`, { headers: h })
      if (r.ok) {
        const data = await r.json()
        setProxyUrl(data.conduct_proxy_url ?? "")
        setUpstream(data.llm_upstream ?? "")
        setHasUpstreamKey(data.has_upstream_key ?? false)
        setUpstreamKey("")
      }
    })()
  }, [workspaceId, envId])

  async function save() {
    if (!envId) return
    setSaving(true)
    const h = { ...(await headers()), "Content-Type": "application/json" }
    await fetch(`${API}/guard/proxy-config`, {
      method: "PUT", headers: h,
      body: JSON.stringify({
        environment_id: envId,
        llm_upstream: upstream,
        llm_upstream_api_key: upstreamKey || undefined,
      }),
    })
    setSaving(false)
    setSaved(true)
    if (upstreamKey) { setHasUpstreamKey(true); setUpstreamKey("") }
    setTimeout(() => setSaved(false), 2000)
  }

  function copy() {
    navigator.clipboard.writeText(proxyUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const GATEWAYS = [
    { name: "Portkey",              url: "https://api.portkey.ai/v1" },
    { name: "Helicone (Anthropic)", url: "https://anthropic.helicone.ai" },
    { name: "Helicone (OpenAI)",    url: "https://oai.helicone.ai/v1" },
    { name: "LiteLLM",             url: "your-litellm-host/v1" },
    { name: "Azure OpenAI",        url: "https://{resource}.openai.azure.com" },
  ]

  return (
    <div style={{ display: "flex", gap: 40, alignItems: "flex-start" }}>
      <div style={{ flex: "0 0 560px" }}>
        <p style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 24, lineHeight: 1.6 }}>
          Guard always intercepts LLM traffic and enforces policies before forwarding.
          Set an upstream to route through your own gateway (Portkey, Azure OpenAI, LiteLLM).
        </p>

        {/* Environment selector */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
            Environment
          </label>
          <select
            value={envId}
            onChange={e => setEnvId(e.target.value)}
            style={{ width: "100%", fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)" }}
          >
            {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
          <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
            Proxy config is stored per environment. Each environment can route to a different upstream.
          </p>
        </div>

        {/* Conduct Proxy URL — read only */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
            Conduct Proxy URL
          </label>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              readOnly value={proxyUrl}
              style={{ flex: 1, fontFamily: "monospace", fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", color: "var(--text-3)" }}
            />
            <button onClick={copy} className="btn btn-ghost btn-sm" style={{ whiteSpace: "nowrap", fontSize: 12 }}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
            Set as <code>ANTHROPIC_BASE_URL</code> / <code>OPENAI_BASE_URL</code> in your AI tools.
          </p>
        </div>

        {/* Enforcement surface */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 10 }}>
            Enforcement Surface
          </label>
          <a href="/guard/policies?persona=proxy" style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--accent-bg, #ede9fe)", color: "var(--accent, #6d28d9)", borderRadius: 6, padding: "4px 10px", fontSize: 12, fontWeight: 600, textDecoration: "none" }}>
            Proxy ↗
          </a>
          <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>All active proxy rules apply to every LLM call routed through this URL.</p>
        </div>

        {/* LLM Upstream */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
            LLM Upstream <span style={{ fontWeight: 400, color: "var(--text-3)", textTransform: "none", letterSpacing: 0 }}>(optional)</span>
          </label>
          <input
            value={upstream} onChange={e => setUpstream(e.target.value)}
            placeholder="https://api.portkey.ai/v1"
            style={{ width: "100%", fontFamily: "monospace", fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)" }}
          />
          <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
            Guard forwards here instead of the vendor API. Stored as <code>PROXY_CONFIG_LLM_UPSTREAM</code> in the environment.
          </p>
        </div>

        {/* LLM Upstream API Key */}
        <div style={{ marginBottom: 28 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
            LLM Upstream API Key <span style={{ fontWeight: 400, color: "var(--text-3)", textTransform: "none", letterSpacing: 0 }}>(optional)</span>
          </label>
          <input
            type="password" value={upstreamKey} onChange={e => setUpstreamKey(e.target.value)}
            placeholder={hasUpstreamKey ? "••••••••  (set — enter new value to rotate)" : "sk-… or portkey API key"}
            style={{ width: "100%", fontFamily: "monospace", fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)" }}
          />
          <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
            Stored as <code>PROXY_CONFIG_LLM_UPSTREAM_API_KEY</code> in the environment.
          </p>
        </div>

        <button onClick={save} disabled={saving || !envId} className="btn btn-primary btn-sm" style={saved ? { background: "var(--green, #22c55e)", borderColor: "var(--green, #22c55e)" } : {}}>
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
        </button>
      </div>

      {/* Right column — gateway reference */}
      <div style={{ flex: "0 0 260px", paddingTop: 4 }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 12 }}>Supported Gateways</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {GATEWAYS.map(g => (
            <div key={g.name}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 2 }}>{g.name}</p>
              <code style={{ fontSize: 11, color: "var(--text-3)", wordBreak: "break-word", overflowWrap: "anywhere" }}>{g.url}</code>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
