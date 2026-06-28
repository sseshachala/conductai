"use client"

import { useState, useEffect } from "react"

const API = process.env.NEXT_PUBLIC_API_URL ?? ""

interface Props {
  workspaceId: string
  getToken: (() => Promise<string | null>) | null
}

export default function ProxySettings({ workspaceId, getToken }: Props) {
  const [proxyUrl, setProxyUrl]         = useState("")
  const [upstream, setUpstream]         = useState("")
  const [upstreamKey, setUpstreamKey]   = useState("")
  const [hasUpstreamKey, setHasUpstreamKey] = useState(false)
  const [proxyPersona, setProxyPersona] = useState<"conservative" | "standard" | "developer">("standard")
  const [saving, setSaving]             = useState(false)
  const [saved, setSaved]               = useState(false)
  const [copied, setCopied]             = useState(false)

  useEffect(() => {
    if (!workspaceId) return
    ;(async () => {
      const headers: Record<string, string> = { "X-Workspace-ID": workspaceId }
      if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
      const res = await fetch(`${API}/guard/proxy-config`, { headers })
      if (!res.ok) return
      const data = await res.json()
      setProxyUrl(data.conduct_proxy_url ?? "")
      setUpstream(data.llm_upstream ?? "")
      setHasUpstreamKey(data.has_upstream_key ?? false)
      setProxyPersona(data.proxy_persona ?? "standard")
    })()
  }, [workspaceId])

  async function save() {
    setSaving(true)
    const headers: Record<string, string> = { "Content-Type": "application/json", "X-Workspace-ID": workspaceId }
    if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
    await fetch(`${API}/guard/proxy-config`, {
      method: "PUT", headers,
      body: JSON.stringify({ llm_upstream: upstream, llm_upstream_api_key: upstreamKey || undefined, proxy_persona: proxyPersona }),
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
    { name: "Portkey",           url: "https://api.portkey.ai/v1" },
    { name: "Helicone (Anthropic)", url: "https://anthropic.helicone.ai" },
    { name: "Helicone (OpenAI)", url: "https://oai.helicone.ai/v1" },
    { name: "LiteLLM",          url: "your-litellm-host/v1" },
    { name: "Azure OpenAI",     url: "https://{resource}.openai.azure.com" },
  ]

  return (
    <div style={{ display: "flex", gap: 40, alignItems: "flex-start" }}>
    <div style={{ flex: "0 0 560px" }}>
      <p style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 24, lineHeight: 1.6 }}>
        Guard always intercepts LLM traffic and enforces policies before forwarding.
        Set an upstream to route through your own gateway (Portkey, Azure OpenAI, LiteLLM).
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
          Set as <code>ANTHROPIC_BASE_URL</code> / <code>OPENAI_BASE_URL</code> in your AI tools. Run <code>conduct guard sync</code> to apply automatically.
        </p>
      </div>

      {/* Proxy Enforcement Persona */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 10 }}>
          Proxy Enforcement Persona
        </label>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {([
            { value: "conservative", label: "Conservative", desc: "Strictest rules — blocks most activity" },
            { value: "standard",     label: "Standard",     desc: "Balanced enforcement (default)" },
            { value: "developer",    label: "Developer",    desc: "Permissive — audit only, rarely blocks" },
          ] as const).map(opt => (
            <label key={opt.value} style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input
                type="radio" name="proxy_persona" value={opt.value}
                checked={proxyPersona === opt.value}
                onChange={() => setProxyPersona(opt.value)}
                style={{ accentColor: "var(--accent)", width: 15, height: 15, flexShrink: 0 }}
              />
              <span>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{opt.label}</span>
                <span style={{ fontSize: 12, color: "var(--text-3)", marginLeft: 8 }}>{opt.desc}</span>
              </span>
            </label>
          ))}
        </div>
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
          Guard forwards here instead of the vendor API. Leave empty to use Anthropic / OpenAI / Perplexity directly.
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
          Sent as the auth header to your upstream gateway. If empty, Guard uses the vendor key from your Environments vault.
        </p>
      </div>

      <button onClick={save} disabled={saving} className="btn btn-primary btn-sm" style={saved ? { background: "var(--green, #22c55e)", borderColor: "var(--green, #22c55e)" } : {}}>
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
