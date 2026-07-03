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
  const [proxyUrl, setProxyUrl]             = useState("")
  const [upstream, setUpstream]             = useState("")
  const [upstreamKey, setUpstreamKey]       = useState("")
  const [hasUpstreamKey, setHasUpstreamKey] = useState(false)
  const [saving, setSaving]                 = useState(false)
  const [saved, setSaved]                   = useState(false)
  const [copied, setCopied]                 = useState(false)

  const [envs, setEnvs]       = useState<Env[]>([])
  const [pushEnvId, setPushEnvId] = useState("")
  const [pushing, setPushing] = useState(false)
  const [pushed, setPushed]   = useState(false)

  async function headers(): Promise<Record<string, string>> {
    const h: Record<string, string> = { "X-Workspace-ID": workspaceId }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    return h
  }

  // Load workspace-level proxy config
  useEffect(() => {
    if (!workspaceId) return
    ;(async () => {
      const h = await headers()
      const r = await fetch(`${API}/guard/proxy-config`, { headers: h })
      if (r.ok) {
        const data = await r.json()
        setProxyUrl(data.conduct_proxy_url ?? "")
        setUpstream(data.llm_upstream ?? "")
        setHasUpstreamKey(data.has_upstream_key ?? false)
      }
    })()
  }, [workspaceId])

  // Load environments for push target
  useEffect(() => {
    if (!workspaceId) return
    ;(async () => {
      const h = await headers()
      const r = await fetch(`${API}/environments`, { headers: h })
      if (r.ok) {
        const data: Env[] = await r.json()
        setEnvs(data)
        if (data.length > 0) setPushEnvId(data[0].id)
      }
    })()
  }, [workspaceId])

  async function save() {
    setSaving(true)
    const h = { ...(await headers()), "Content-Type": "application/json" }
    await fetch(`${API}/guard/proxy-config`, {
      method: "PUT", headers: h,
      body: JSON.stringify({
        llm_upstream: upstream,
        llm_upstream_api_key: upstreamKey || undefined,
      }),
    })
    setSaving(false)
    setSaved(true)
    if (upstreamKey) { setHasUpstreamKey(true); setUpstreamKey("") }
    setTimeout(() => setSaved(false), 2000)
  }

  async function push() {
    if (!pushEnvId) return
    setPushing(true)
    const h = { ...(await headers()), "Content-Type": "application/json" }
    await fetch(`${API}/guard/proxy-config/push`, {
      method: "POST", headers: h,
      body: JSON.stringify({ environment_id: pushEnvId }),
    })
    setPushing(false)
    setPushed(true)
    setTimeout(() => setPushed(false), 2000)
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
          Guard intercepts LLM traffic and enforces policies before forwarding.
          Configure your upstream gateway once, then push to any environment.
        </p>

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
            Guard forwards here instead of the vendor API.
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
        </div>

        <button onClick={save} disabled={saving} className="btn btn-primary btn-sm" style={saved ? { background: "var(--green, #22c55e)", borderColor: "var(--green, #22c55e)" } : {}}>
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
        </button>

        {/* Divider */}
        <hr style={{ margin: "32px 0", borderColor: "var(--border)" }} />

        {/* Push to environment */}
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
            Push to Environment
          </label>
          <p style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 12 }}>
            Copies the upstream URL and key into an environment's variables so workflows running in that environment use this gateway.
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select
              value={pushEnvId}
              onChange={e => setPushEnvId(e.target.value)}
              style={{ flex: 1, fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)" }}
            >
              {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            <button
              onClick={push}
              disabled={pushing || !pushEnvId}
              className="btn btn-secondary btn-sm"
              style={pushed ? { background: "var(--green, #22c55e)", borderColor: "var(--green, #22c55e)", color: "#fff" } : {}}
            >
              {pushing ? "Pushing…" : pushed ? "Pushed ✓" : "Push"}
            </button>
          </div>
        </div>
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
