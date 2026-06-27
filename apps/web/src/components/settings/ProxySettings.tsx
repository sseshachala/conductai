"use client"

import { useState, useEffect } from "react"

const API = process.env.NEXT_PUBLIC_API_URL ?? ""

interface Props {
  workspaceId: string
  getToken: (() => Promise<string | null>) | null
}

export default function ProxySettings({ workspaceId, getToken }: Props) {
  const [proxyUrl, setProxyUrl] = useState("")
  const [upstream, setUpstream] = useState("")
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [copied, setCopied] = useState(false)

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
    })()
  }, [workspaceId])

  async function save() {
    setSaving(true)
    const headers: Record<string, string> = { "Content-Type": "application/json", "X-Workspace-ID": workspaceId }
    if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
    await fetch(`${API}/guard/proxy-config`, { method: "PUT", headers, body: JSON.stringify({ llm_upstream: upstream }) })
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  function copy() {
    navigator.clipboard.writeText(proxyUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div style={{ maxWidth: 600 }}>
      <p style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 24, lineHeight: 1.6 }}>
        Guard always intercepts LLM traffic. Set an upstream to forward to your own gateway
        (Portkey, Azure OpenAI, LiteLLM) instead of the vendor directly.
        Policies are enforced regardless of upstream.
      </p>

      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
          Conduct Proxy URL
        </label>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            readOnly
            value={proxyUrl}
            style={{ flex: 1, fontFamily: "monospace", fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", color: "var(--text-3)" }}
          />
          <button
            onClick={copy}
            className="btn btn-ghost btn-sm"
            style={{ whiteSpace: "nowrap", fontSize: 12 }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
          Set this as <code>ANTHROPIC_BASE_URL</code> / <code>OPENAI_BASE_URL</code> in your AI tools.
          Run <code>conduct guard sync</code> to apply automatically.
        </p>
      </div>

      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".06em", display: "block", marginBottom: 8 }}>
          LLM Upstream <span style={{ fontWeight: 400, color: "var(--text-3)", textTransform: "none", letterSpacing: 0 }}>(optional)</span>
        </label>
        <input
          value={upstream}
          onChange={e => setUpstream(e.target.value)}
          placeholder="https://api.portkey.ai/v1"
          style={{ width: "100%", fontFamily: "monospace", fontSize: 13, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)" }}
        />
        <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
          Guard forwards to this URL instead of the vendor API. Leave empty to use Anthropic / OpenAI / Perplexity directly.
        </p>
      </div>

      <button
        onClick={save}
        disabled={saving}
        className="btn btn-primary btn-sm"
      >
        {saving ? "Saving…" : saved ? "Saved" : "Save"}
      </button>
    </div>
  )
}
