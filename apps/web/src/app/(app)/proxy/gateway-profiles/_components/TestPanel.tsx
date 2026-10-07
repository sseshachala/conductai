"use client"

import { useCallback, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { API } from "@/lib/api/client"

// #2026 — smoke-test a published profile end-to-end without leaving the page.
// Backend endpoint mints a short-lived ``test-gateway-token``, calls the
// gateway server-side (browsers can't reach the gateway origin — CORS is
// closed by design), and revokes the token before returning.
export function TestPanel({ profileId, urls }: { profileId: string; urls: string[] }) {
  // Derive picker options from the URLs the panel already shows above.
  // Two providers today (anthropic, openai) map 1:1 to the two gateway
  // vendor paths — that's why the identity of the picker is just the
  // provider string, not the full URL.
  const providers: Array<"anthropic" | "openai"> = urls.map(u =>
    u.includes("/gateway/v1/anthropic") ? "anthropic" : "openai",
  ) as Array<"anthropic" | "openai">
  const [open, setOpen] = useState(false)
  const [provider, setProvider] = useState<"anthropic" | "openai">(providers[0] ?? "openai")
  const [prompt, setPrompt] = useState(CANNED_PROMPTS[0].value)
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "error">("idle")
  const [output, setOutput] = useState<string>("")
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""

  const closePanel = useCallback(() => {
    setStatus("idle")
    setOutput("")
    setOpen(false)
  }, [])

  const send = useCallback(async () => {
    if (!prompt.trim() || !workspaceId) return
    setStatus("sending")
    setOutput("")
    try {
      const res = await authFetch(
        `${API}/workspaces/${workspaceId}/gateway-profiles-v2/${profileId}/test?workspace_id=${workspaceId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, provider }),
        },
      )
      const raw = await res.text()
      if (!res.ok) {
        setStatus("error")
        setOutput(friendlyError(res.status, raw))
        return
      }
      const parsed = JSON.parse(raw) as { ok: boolean; status: number; content: string | null; body: string }
      if (!parsed.ok) {
        setStatus("error")
        setOutput(friendlyError(parsed.status, parsed.content ?? parsed.body))
        return
      }
      setOutput(parsed.content ?? parsed.body)
      setStatus("ok")
    } catch (err) {
      setStatus("error")
      setOutput(String(err))
    }
  }, [authFetch, workspaceId, profileId, provider, prompt])

  if (!open) {
    return (
      <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setOpen(true)}
          style={{ height: 26, fontSize: 11.5 }}
        >Test</button>
      </div>
    )
  }

  return (
    <div className="card card-pad" style={{ marginTop: 12, background: "var(--surface-1)" }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10,
      }}>
        <div className="eyebrow">Test this profile</div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={closePanel}
          style={{ height: 22, fontSize: 11 }}
        >Close</button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {providers.length > 1 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 11.5, color: "var(--text-2)" }}>Provider</span>
            {providers.map(p => {
              const selected = p === provider
              return (
                <button
                  key={p}
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setProvider(p)}
                  style={{
                    height: 22, fontSize: 11,
                    background: selected ? "var(--surface-3)" : "transparent",
                    fontWeight: selected ? 600 : 500,
                  }}
                >{p === "anthropic" ? "Anthropic" : "OpenAI"}</button>
              )
            })}
          </div>
        )}

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 11.5, color: "var(--text-2)" }}>Prompt</span>
          {CANNED_PROMPTS.map(c => (
            <button
              key={c.label}
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setPrompt(c.value)}
              style={{ height: 22, fontSize: 11 }}
            >{c.label}</button>
          ))}
        </div>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          spellCheck={false}
          style={{
            fontSize: 12.5, fontFamily: "inherit", padding: 8, borderRadius: 6,
            border: "1px solid var(--border)", background: "var(--surface-2)",
            color: "var(--text)", resize: "vertical",
          }}
        />

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "var(--text-3)" }}>
            Mints a fresh <code className="mono">test-gateway-token</code>; revoked automatically.
          </span>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => void send()}
            disabled={status === "sending" || !prompt.trim()}
            style={{ height: 26, fontSize: 11.5 }}
          >{status === "sending" ? "Sending…" : "Send"}</button>
        </div>

        {output && (
          <div>
            <div style={{ marginBottom: 6 }}>
              <span className={`sbadge ${status === "error" ? "err" : "ok"}`}>
                {status === "error" ? "Error" : "Response"}
              </span>
            </div>
            <pre className="mono" style={{
              margin: 0, padding: 10, borderRadius: 6, fontSize: 12,
              background: "var(--surface-2)", color: "var(--text)",
              border: "1px solid var(--border)",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
              maxHeight: 320, overflow: "auto",
            }}>{output}</pre>
          </div>
        )}
      </div>
    </div>
  )
}

export const CANNED_PROMPTS: Array<{ label: string; value: string }> = [
  { label: "Say hi", value: "Say hi in one short sentence." },
  { label: "Summarise", value: "Summarise in two sentences: The mitochondrion is the powerhouse of the cell." },
  { label: "Return JSON", value: 'Return only this JSON, no prose: {"ok": true, "provider": "?"}' },
]

export function friendlyError(status: number, raw: string): string {
  if (status === 401 || status === 403) return "Auth token was rejected by the gateway."
  if (status === 404) return "Profile not routable — check that it's published and the URL matches."
  if (status === 424 || /vault|credential/i.test(raw)) {
    return `Provider credential problem (missing, unreachable, or rejected by the provider).\n\n${raw}`
  }
  return raw || `HTTP ${status}`
}

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button className="btn btn-ghost btn-sm"
      style={{ height: 26, fontSize: 11.5 }}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch { /* clipboard unavailable */ }
      }}>
      {copied ? "Copied" : "Copy"}
    </button>
  )
}
