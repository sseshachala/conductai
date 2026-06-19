"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardRole } from "@/hooks/useGuardRole"

interface ApiKey {
  id: string
  name: string
  key_prefix: string
  role: string
  created_at: string
  last_used_at: string | null
  expires_at: string | null
}

export default function ApiKeysManager() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  const { role } = useGuardRole(null, workspaceId || null)
  const isAdmin = role === "admin"
  const canGenerateKey = role === "admin" || role === "developer"

  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")
  const [newKey, setNewKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [revokeConfirmId, setRevokeConfirmId] = useState<string | null>(null)
  const [revokeConfirmValue, setRevokeConfirmValue] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const headers = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    if (workspaceId) h["X-Workspace-Id"] = workspaceId
    return h
  }, [getToken, workspaceId])

  const load = useCallback(async () => {
    if (!workspaceId || !apiUrl) return
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/api-keys`, { headers: h })
      if (r.ok) setKeys(await r.json())
    } catch {}
    setLoading(false)
  }, [workspaceId, apiUrl, headers])

  useEffect(() => { load() }, [load])

  async function create() {
    if (!newName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/api-keys`, {
        method: "POST",
        headers: h,
        body: JSON.stringify({ name: newName.trim() }),
      })
      if (r.ok) {
        const data = await r.json()
        setNewKey(data.key)
        setNewName("")
        setShowCreate(false)
        await load()
      } else {
        const body = await r.json().catch(() => ({}))
        setError(body.detail ?? "Could not generate key — please try again.")
      }
    } catch { setError("Could not generate key — check your connection.") }
    setCreating(false)
  }

  async function revoke(id: string) {
    setRevokeConfirmId(null)
    setRevokeConfirmValue("")
    setRevoking(id)
    setError(null)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/api-keys/${id}`, { method: "DELETE", headers: h })
      if (r.ok) setKeys(k => k.filter(x => x.id !== id))
      else {
        const body = await r.json().catch(() => ({}))
        setError(body.detail ?? "Could not revoke key — please try again.")
      }
    } catch { setError("Could not revoke key — check your connection.") }
    setRevoking(null)
  }

  function copy() {
    if (!newKey) return
    navigator.clipboard.writeText(newKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function fmt(dateStr: string | null) {
    if (!dateStr) return "—"
    return new Date(dateStr).toLocaleDateString("en-GB", { month: "short", day: "numeric", year: "numeric" })
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {error && (
        <div className="card" style={{ padding: "12px 16px", background: "var(--err-bg)", borderColor: "var(--err-bd)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <p style={{ fontSize: 12.5, color: "var(--err)" }}>{error}</p>
          <button onClick={() => setError(null)} style={{ fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer", opacity: 0.7 }}>✕</button>
        </div>
      )}

      {newKey && (
        <div className="card" style={{ padding: "16px 18px", background: "var(--warn-bg)", borderColor: "var(--warn-bd)", display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--warn)" }}>Copy your API key — it won&apos;t be shown again.</p>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <code className="mono" style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--warn-bd)", borderRadius: 7, padding: "8px 12px", fontSize: 12, color: "var(--text)", wordBreak: "break-all", userSelect: "all" }}>
              {newKey}
            </code>
            <button onClick={copy} className="btn btn-sm" style={{ flexShrink: 0, background: copied ? "var(--ok)" : "var(--warn)", color: "#fff", border: "none" }}>
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-2)" }}>
            Use this key with <code className="mono" style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>X-Api-Key</code> header or{" "}
            <code className="mono" style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>conduct login --api-key</code>.
          </p>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button onClick={() => setNewKey(null)} style={{ fontSize: 12, color: "var(--warn)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", textAlign: "left", padding: 0 }}>
              I&apos;ve saved it, dismiss
            </button>
            <button onClick={() => setNewKey(null)} aria-label="Dismiss" className="btn btn-ghost btn-sm btn-icon" style={{ color: "var(--warn)" }}>✕</button>
          </div>
        </div>
      )}

      {canGenerateKey && showCreate && (
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") create(); if (e.key === "Escape") setShowCreate(false) }}
            placeholder="Key name (e.g. My laptop, CI pipeline)"
            autoFocus
            style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none" }}
          />
          <button onClick={create} disabled={creating || !newName.trim()} className="btn btn-primary btn-sm" style={{ opacity: (creating || !newName.trim()) ? 0.4 : 1 }}>
            {creating ? "Generating…" : "Generate key"}
          </button>
          <button onClick={() => setShowCreate(false)} className="btn btn-ghost btn-sm">Cancel</button>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontSize: 13.5, color: "var(--text-3)" }}>
          Keys authenticate the CLI and CI. Scope <code className="mono">cond_live_…</code> per use, rotate freely.
        </span>
        {canGenerateKey && !showCreate && (
          <button className="btn btn-primary btn-sm" style={{ marginLeft: "auto" }} onClick={() => setShowCreate(true)}>
            + Create key
          </button>
        )}
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
        ) : keys.length === 0 ? (
          <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>No API keys yet.</div>
        ) : (
          keys.map((k, i) => (
            <div key={k.id} style={{ borderBottom: i < keys.length - 1 ? "1px solid var(--border)" : "none" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1.2fr 1fr 0.9fr 30px", gap: 14, padding: "14px 20px", alignItems: "center" }}>
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{k.name}</div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{k.key_prefix}••••••••</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Created {fmt(k.created_at)}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Used {fmt(k.last_used_at)}</div>
                <div>
                  {isAdmin && (
                    <button
                      className="btn btn-ghost btn-sm btn-icon"
                      style={{ color: "var(--err)" }}
                      onClick={() => {
                        if (revokeConfirmId === k.id) {
                          setRevokeConfirmId(null)
                          setRevokeConfirmValue("")
                        } else {
                          setRevokeConfirmId(k.id)
                          setRevokeConfirmValue("")
                        }
                      }}
                      disabled={revoking === k.id}
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>

              {isAdmin && revokeConfirmId === k.id && (
                <div style={{ margin: "0 20px 12px", padding: "10px 12px", border: "1px solid var(--err-bd)", borderRadius: 10, background: "var(--err-bg)", display: "flex", flexDirection: "column", gap: 8 }}>
                  <p style={{ fontSize: 11.5, color: "var(--err)", margin: 0 }}>
                    Type <strong>{k.name}</strong> to confirm key revocation.
                  </p>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input
                      value={revokeConfirmValue}
                      onChange={e => setRevokeConfirmValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && revokeConfirmValue === k.name) revoke(k.id)
                        if (e.key === "Escape") { setRevokeConfirmId(null); setRevokeConfirmValue("") }
                      }}
                      placeholder={k.name}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        fontSize: 12,
                        border: "1px solid var(--err-bd, #fecaca)",
                        borderRadius: 8,
                        padding: "6px 10px",
                        outline: "none",
                        background: "var(--surface)",
                        color: "var(--text)",
                      }}
                    />
                    <button
                      onClick={() => revoke(k.id)}
                      disabled={revoking === k.id || revokeConfirmValue !== k.name}
                      className="btn btn-sm"
                      style={{ background: "var(--err)", color: "#fff", border: "none", opacity: (revoking === k.id || revokeConfirmValue !== k.name) ? 0.4 : 1 }}
                    >
                      {revoking === k.id ? "Revoking…" : "Confirm"}
                    </button>
                    <button onClick={() => { setRevokeConfirmId(null); setRevokeConfirmValue("") }} className="btn btn-ghost btn-sm">
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
        Keys are stored as SHA-256 hashes — Conduct never sees your key again after generation.
        Admins and developers can generate keys. Only admins can revoke keys.
      </p>
    </div>
  )
}
