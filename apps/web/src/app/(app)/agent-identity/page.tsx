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

interface RunToken {
  id: string
  run_id: string
  token_prefix: string | null
  workflow_name: string | null
  created_at: string | null
  first_used_at: string | null
  invalidated_at: string | null
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
  const [showDrawer, setShowDrawer] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")
  const [newEnvId, setNewEnvId] = useState("")
  const [newToken, setNewToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const [deleting, setDeleting] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [runTokens, setRunTokens] = useState<Record<string, RunToken[]>>({})
  const [loadingTokens, setLoadingTokens] = useState<string | null>(null)

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

  function openDrawer() { setNewName(""); setNewEnvId(""); setError(null); setShowDrawer(true) }
  function closeDrawer() { setShowDrawer(false); setError(null) }

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
        closeDrawer()
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
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities/${id}/regenerate`, { method: "POST", headers: h })
      if (r.ok) { setNewToken((await r.json()).token); await load() }
    } catch {}
    setRegenerating(null)
  }

  async function del(id: string) {
    setDeleteConfirmId(null); setDeleteConfirmValue(""); setDeleting(id)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities/${id}`, { method: "DELETE", headers: h })
      if (r.ok) setIdentities(x => x.filter(i => i.id !== id))
    } catch {}
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

  async function loadRunTokens(identityId: string) {
    if (expandedId === identityId) { setExpandedId(null); return }
    if (!runTokens[identityId]) {
      setLoadingTokens(identityId)
      try {
        const h = await headers()
        const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-identities/${identityId}/run-tokens`, { headers: h })
        if (r.ok) { const data = await r.json(); setRunTokens(prev => ({ ...prev, [identityId]: data })) }
      } catch {}
      setLoadingTokens(null)
    }
    setExpandedId(identityId)
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 28 }}>

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: 0 }}>Agent Identity</h1>
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>
              Issue credentials for your agents. Each agent gets its own token, separate from user accounts.
            </p>
          </div>
          {canCreate && (
            <button className="btn btn-primary btn-sm" style={{ flexShrink: 0 }} onClick={openDrawer}>
              + Issue token
            </button>
          )}
        </div>

        {/* New token banner */}
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

        {/* ── Section 1: Long-lived tokens ───────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>Long-lived tokens</h2>
            <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "3px 0 0" }}>
              <code className="mono" style={{ fontSize: 11 }}>cond_agt_</code> — persist across runs. Set as CONDUCT_AGENT_TOKEN in your environment.
            </p>
          </div>
          <div className="card" style={{ overflow: "hidden" }}>
            {loading ? (
              <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading...</div>
            ) : identities.length === 0 ? (
              <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>No agent tokens yet. Issue one to get started.</div>
            ) : (
              identities.map((identity, i) => (
                <div key={identity.id} style={{ borderBottom: i < identities.length - 1 ? "1px solid var(--border)" : "none" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1.4fr 0.9fr 0.9fr 0.9fr auto", gap: 14, padding: "14px 20px", alignItems: "center" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--text)" }}>{identity.name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>{envName(identity.environment_id)}</div>
                    </div>
                    <code className="mono" style={{ fontSize: 12, color: "var(--text-3)", background: "var(--bg)", padding: "3px 7px", borderRadius: 5, border: "1px solid var(--border)", display: "inline-block" }}>
                      {identity.token_prefix}...
                    </code>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Issued {fmt(identity.created_at)}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Used {fmt(identity.last_used_at)}</div>
                    <button
                      onClick={() => loadRunTokens(identity.id)}
                      style={{ fontSize: 12, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", textAlign: "left", padding: 0, whiteSpace: "nowrap" }}
                    >
                      {loadingTokens === identity.id ? "Loading..." : expandedId === identity.id ? "Hide runs ▲" : "Show runs ▼"}
                    </button>
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
                        >×</button>
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
        </div>

        {/* ── Section 2: Short-lived run tokens ──────────────────────── */}
        {expandedId && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>
                Run tokens — {identities.find(i => i.id === expandedId)?.name}
              </h2>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "3px 0 0" }}>
                <code className="mono" style={{ fontSize: 11 }}>cond_run_</code> — minted per run, invalidated when the run ends.
              </p>
            </div>
            <div className="card" style={{ overflow: "hidden" }}>
              {(runTokens[expandedId] ?? []).length === 0 ? (
                <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                  No run tokens yet. Trigger a workflow assigned to this identity to see tokens here.
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
                    {(runTokens[expandedId] ?? []).map(rt => (
                      <tr key={rt.id} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 16px" }}>
                          <code className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", background: "var(--bg)", padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)" }}>
                            {rt.token_prefix ? `${rt.token_prefix}...` : "—"}
                          </code>
                        </td>
                        <td style={{ padding: "8px 16px", color: "var(--text)" }}>{rt.workflow_name ?? "—"}</td>
                        <td style={{ padding: "8px 16px" }}>
                          <a href={`/runs/${rt.run_id}`} style={{ color: "var(--accent)", textDecoration: "none", fontFamily: "monospace", fontSize: 11.5 }}>
                            {rt.run_id.slice(0, 8)}
                          </a>
                        </td>
                        <td style={{ padding: "8px 16px", color: "var(--text-muted)" }}>{fmt(rt.created_at)}</td>
                        <td style={{ padding: "8px 16px", color: rt.first_used_at ? "var(--ok)" : "var(--text-muted)" }}>
                          {rt.first_used_at ? fmt(rt.first_used_at) : "—"}
                        </td>
                        <td style={{ padding: "8px 16px" }}>
                          {rt.invalidated_at
                            ? <span style={{ color: "var(--text-muted)", fontSize: 11.5 }}>Invalidated {fmt(rt.invalidated_at)}</span>
                            : <span style={{ color: "var(--ok)", fontWeight: 600, fontSize: 11.5 }}>Active</span>
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Tokens are stored encrypted. Conduct never sees plaintext after issuance. Long-lived tokens persist until regenerated or deleted. Run tokens are single-use and invalidated when their run completes.
        </p>
      </div>

      {/* Right drawer */}
      {showDrawer && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.25)", zIndex: 50 }}>
          <div onClick={closeDrawer} style={{ position: "absolute", inset: 0 }} aria-hidden="true" />
          <div style={{
            position: "absolute", top: 0, right: 0, bottom: 0, zIndex: 10,
            width: 440, maxWidth: "100vw", overflowY: "auto",
            background: "var(--surface)", boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
            borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column",
          }}>
            <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "var(--text)" }}>Issue Agent Token</h2>
              <button onClick={closeDrawer} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "var(--text-muted)", lineHeight: 1 }}>×</button>
            </div>
            <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: 18, flex: 1 }}>
              {error && (
                <div style={{ padding: "10px 14px", background: "var(--err-bg)", border: "1px solid var(--err-bd)", borderRadius: 8, fontSize: 12.5, color: "var(--err)" }}>{error}</div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)" }}>Token name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") create(); if (e.key === "Escape") closeDrawer() }}
                  placeholder="e.g. PR Reviewer, BugHunter"
                  autoFocus
                  style={{ border: "1px solid var(--border)", borderRadius: 9, padding: "9px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none", width: "100%", boxSizing: "border-box" }}
                />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)" }}>Environment</label>
                <select
                  value={newEnvId}
                  onChange={e => setNewEnvId(e.target.value)}
                  style={{ border: "1px solid var(--border)", borderRadius: 9, padding: "9px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none", width: "100%", boxSizing: "border-box" }}
                >
                  <option value="">No environment</option>
                  {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  CONDUCT_AGENT_TOKEN will be added to the selected environment automatically.
                </p>
              </div>
            </div>
            <div style={{ padding: "16px 24px", borderTop: "1px solid var(--border)", display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={closeDrawer} className="btn btn-ghost btn-sm">Cancel</button>
              <button onClick={create} disabled={creating || !newName.trim()} className="btn btn-primary btn-sm" style={{ opacity: (creating || !newName.trim()) ? 0.4 : 1 }}>
                {creating ? "Issuing..." : "Issue token"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}
