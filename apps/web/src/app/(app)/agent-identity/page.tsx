"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardRole } from "@/hooks/useGuardRole"

interface AgentIdentity {
  id: string
  name: string
  provider: string
  token_prefix: string
  created_at: string
  last_used_at: string | null
  environment_id: string | null
}

interface Env {
  id: string
  name: string
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
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  const { role } = useGuardRole(null, workspaceId || null)
  const isAdmin = role === "admin"
  const canCreate = role === "admin" || role === "developer"

  const [identities, setIdentities] = useState<AgentIdentity[]>([])
  const [envs, setEnvs] = useState<Env[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState("")
  const [newEnvId, setNewEnvId] = useState("")
  const [newToken, setNewToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const [deleting, setDeleting] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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
      const [idRes, envRes] = await Promise.all([
        fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities`, { headers: h }),
        fetch(`${apiUrl}/environments`, { headers: h }),
      ])
      if (idRes.ok) setIdentities(await idRes.json())
      if (envRes.ok) setEnvs(await envRes.json())
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
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities`, {
        method: "POST",
        headers: h,
        body: JSON.stringify({ name: newName.trim(), environment_id: newEnvId || null }),
      })
      if (r.ok) {
        const data = await r.json()
        setNewToken(data.token)
        setNewName("")
        setNewEnvId("")
        setShowCreate(false)
        await load()
      } else {
        const body = await r.json().catch(() => ({}))
        setError(body.detail ?? "Could not create token — please try again.")
      }
    } catch { setError("Could not create token — check your connection.") }
    setCreating(false)
  }

  async function regenerate(id: string) {
    setRegenerating(id)
    setError(null)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities/${id}/regenerate`, {
        method: "POST", headers: h,
      })
      if (r.ok) { setNewToken((await r.json()).token); await load() }
      else setError((await r.json().catch(() => ({}))).detail ?? "Could not regenerate token.")
    } catch { setError("Could not regenerate token — check your connection.") }
    setRegenerating(null)
  }

  async function del(id: string) {
    setDeleteConfirmId(null)
    setDeleteConfirmValue("")
    setDeleting(id)
    setError(null)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities/${id}`, { method: "DELETE", headers: h })
      if (r.ok) setIdentities(x => x.filter(i => i.id !== id))
      else setError((await r.json().catch(() => ({}))).detail ?? "Could not delete.")
    } catch { setError("Could not delete — check your connection.") }
    setDeleting(null)
  }

  function copy() {
    if (!newToken) return
    navigator.clipboard.writeText(newToken)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function fmt(d: string | null) {
    if (!d) return "—"
    return new Date(d).toLocaleDateString("en-GB", { month: "short", day: "numeric", year: "numeric" })
  }

  function envName(id: string | null) {
    if (!id) return "—"
    return envs.find(e => e.id === id)?.name ?? "—"
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: 0 }}>Agent Identity</h1>
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>
              Issue tokens for your agents. Each agent gets its own credential, not shared with users.
            </p>
          </div>
          {canCreate && !showCreate && (
            <button className="btn btn-primary btn-sm" style={{ flexShrink: 0 }} onClick={() => setShowCreate(true)}>
              + Issue token
            </button>
          )}
        </div>

        {error && (
          <div className="card" style={{ padding: "12px 16px", background: "var(--err-bg)", borderColor: "var(--err-bd)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <p style={{ fontSize: 12.5, color: "var(--err)", margin: 0 }}>{error}</p>
            <button onClick={() => setError(null)} style={{ fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer", opacity: 0.7 }}>x</button>
          </div>
        )}

        {newToken && (
          <div className="card" style={{ padding: "16px 18px", background: "var(--warn-bg)", borderColor: "var(--warn-bd)", display: "flex", flexDirection: "column", gap: 10 }}>
            <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--warn)", margin: 0 }}>Copy your agent token — it will not be shown again.</p>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <code className="mono" style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--warn-bd)", borderRadius: 7, padding: "8px 12px", fontSize: 12, color: "var(--text)", wordBreak: "break-all", userSelect: "all" }}>
                {newToken}
              </code>
              <button onClick={copy} className="btn btn-sm" style={{ flexShrink: 0, background: copied ? "var(--ok)" : "var(--warn)", color: "#fff", border: "none" }}>
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-2)", margin: 0 }}>
              Added as CONDUCT_AGENT_TOKEN to the selected environment automatically.
            </p>
            <button onClick={() => setNewToken(null)} style={{ fontSize: 12, color: "var(--warn)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", textAlign: "left", padding: 0 }}>
              Saved it, dismiss
            </button>
          </div>
        )}

        {canCreate && showCreate && (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") create(); if (e.key === "Escape") setShowCreate(false) }}
              placeholder="Token name (e.g. PR Reviewer, BugHunter)"
              autoFocus
              style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none" }}
            />
            <select
              value={newEnvId}
              onChange={e => setNewEnvId(e.target.value)}
              style={{ border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none", minWidth: 160 }}
            >
              <option value="">No environment</option>
              {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            <button onClick={create} disabled={creating || !newName.trim()} className="btn btn-primary btn-sm" style={{ opacity: (creating || !newName.trim()) ? 0.4 : 1 }}>
              {creating ? "Issuing..." : "Issue token"}
            </button>
            <button onClick={() => setShowCreate(false)} className="btn btn-ghost btn-sm">Cancel</button>
          </div>
        )}

        <div className="card" style={{ overflow: "hidden" }}>
          {loading ? (
            <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading...</div>
          ) : identities.length === 0 ? (
            <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>No agent tokens yet.</div>
          ) : (
            identities.map((identity, i) => (
              <div key={identity.id} style={{ borderBottom: i < identities.length - 1 ? "1px solid var(--border)" : "none" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1.2fr 0.9fr 0.8fr 0.8fr auto", gap: 14, padding: "14px 20px", alignItems: "center" }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--text)" }}>{identity.name}</div>
                  <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{identity.token_prefix}...</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{envName(identity.environment_id)}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Created {fmt(identity.created_at)}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Used {fmt(identity.last_used_at)}</div>
                  <div style={{ display: "flex", gap: 4 }}>
                    {canCreate && (
                      <button className="btn btn-ghost btn-sm" style={{ fontSize: 11.5 }} onClick={() => regenerate(identity.id)} disabled={regenerating === identity.id}>
                        {regenerating === identity.id ? "..." : "Regenerate"}
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        className="btn btn-ghost btn-sm btn-icon"
                        style={{ color: "var(--err)" }}
                        onClick={() => {
                          if (deleteConfirmId === identity.id) { setDeleteConfirmId(null); setDeleteConfirmValue("") }
                          else { setDeleteConfirmId(identity.id); setDeleteConfirmValue("") }
                        }}
                        disabled={deleting === identity.id}
                      >x</button>
                    )}
                  </div>
                </div>

                {isAdmin && deleteConfirmId === identity.id && (
                  <div style={{ margin: "0 20px 12px", padding: "10px 12px", border: "1px solid var(--err-bd)", borderRadius: 10, background: "var(--err-bg)", display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ fontSize: 11.5, color: "var(--err)", margin: 0 }}>Type <strong>{identity.name}</strong> to confirm deletion.</p>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input
                        value={deleteConfirmValue}
                        onChange={e => setDeleteConfirmValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter" && deleteConfirmValue === identity.name) del(identity.id)
                          if (e.key === "Escape") { setDeleteConfirmId(null); setDeleteConfirmValue("") }
                        }}
                        placeholder={identity.name}
                        style={{ flex: 1, minWidth: 0, fontSize: 12, border: "1px solid var(--err-bd)", borderRadius: 8, padding: "6px 10px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
                      />
                      <button onClick={() => del(identity.id)} disabled={deleting === identity.id || deleteConfirmValue !== identity.name} className="btn btn-sm" style={{ background: "var(--err)", color: "#fff", border: "none", opacity: (deleting === identity.id || deleteConfirmValue !== identity.name) ? 0.4 : 1 }}>
                        {deleting === identity.id ? "Deleting..." : "Delete"}
                      </button>
                      <button onClick={() => { setDeleteConfirmId(null); setDeleteConfirmValue("") }} className="btn btn-ghost btn-sm">Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Tokens are stored encrypted. Conduct never sees the plaintext again after issuance. When assigned to an environment, CONDUCT_AGENT_TOKEN is added automatically. Admins and developers can issue tokens. Only admins can delete.
        </p>
      </div>
    </AppShell>
  )
}
