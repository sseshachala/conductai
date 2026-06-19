"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ── Types ─────────────────────────────────────────────────────────────────────

interface McpServer {
  id: string
  workspace_id: string
  environment_id: string | null
  name: string
  url: string
  transport: "sse" | "http" | "stdio"
  has_auth: boolean
  is_system: boolean
  created_at: string
}

interface Environment {
  id: string
  name: string
}

interface FormState {
  name: string
  url: string
  transport: "sse" | "http" | "stdio"
  auth_token: string
  environment_id: string
}

const EMPTY_FORM: FormState = {
  name: "",
  url: "",
  transport: "sse",
  auth_token: "",
  environment_id: "",
}

const TRANSPORT_LABELS: Record<string, string> = {
  sse: "SSE",
  http: "HTTP",
  stdio: "stdio",
}

const TRANSPORT_COLORS: Record<string, { bg: string; color: string }> = {
  sse:   { bg: "var(--accent)",   color: "var(--accent-text)" },
  http:  { bg: "var(--surface-2)", color: "var(--text-2)" },
  stdio: { bg: "var(--surface-2)", color: "var(--text-2)" },
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
  } catch {
    return iso
  }
}

// ── Clerk guard ───────────────────────────────────────────────────────────────

export default function IntegrationsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <IntegrationsPageWithAuth />
  return <IntegrationsPageInner getToken={null} wsId="" />
}

function IntegrationsPageWithAuth() {
  const { getToken } = useAuth()
  // Read wsId from cookie — same pattern as EnvironmentsManager
  // useWorkspace() won't work here because WorkspaceProvider lives inside AppShell (a child)
  const wsId = typeof document !== "undefined"
    ? document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? ""
    : ""
  return <IntegrationsPageInner getToken={getToken} wsId={wsId} />
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function McpModal({
  mode,
  initial,
  environments,
  onSave,
  onClose,
  isSystem,
}: {
  mode: "add" | "edit"
  initial: FormState
  environments: Environment[]
  onSave: (form: FormState) => Promise<void>
  onClose: () => void
  isSystem?: boolean
}) {
  const [form, setForm] = useState<FormState>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const readOnly = !!isSystem

  function set(key: keyof FormState, value: string) {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) { setError("Name is required."); return }
    if (!form.url.trim())  { setError("URL is required.");  return }
    setSaving(true)
    setError("")
    try {
      await onSave(form)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save — please try again.")
    } finally {
      setSaving(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "8px 12px",
    fontSize: 13,
    color: "var(--text)",
    background: "var(--surface)",
    outline: "none",
    boxSizing: "border-box",
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 500,
    color: "var(--text-3)",
    display: "block",
    marginBottom: 4,
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="card"
        style={{
          width: "100%", maxWidth: 480,
          borderRadius: 12,
          background: "var(--surface)",
          padding: 24,
          display: "flex", flexDirection: "column", gap: 16,
        }}
      >
        <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", margin: 0 }}>
          {mode === "add" ? "Add MCP server" : "Edit MCP server"}
        </h2>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Name */}
          <div>
            <label style={labelStyle}>Name</label>
            <input
              autoFocus
              type="text"
              value={form.name}
              onChange={e => !readOnly && set("name", e.target.value)}
              placeholder="e.g. GitHub tools"
              readOnly={readOnly}
              style={{ ...inputStyle, opacity: readOnly ? 0.6 : 1 }}
            />
          </div>

          {/* URL */}
          <div>
            <label style={labelStyle}>URL</label>
            <input
              type="text"
              value={form.url}
              onChange={e => !readOnly && set("url", e.target.value)}
              placeholder="https://mcp.example.com/sse"
              readOnly={readOnly}
              style={{ ...inputStyle, opacity: readOnly ? 0.6 : 1 }}
            />
          </div>

          {/* Transport */}
          <div>
            <label style={labelStyle}>Transport</label>
            <select
              value={form.transport}
              onChange={e => set("transport", e.target.value as FormState["transport"])}
              style={inputStyle}
            >
              <option value="sse">SSE</option>
              <option value="http">HTTP</option>
              <option value="stdio">stdio</option>
            </select>
          </div>

          {/* Auth token */}
          <div>
            <label style={labelStyle}>
              Auth token{" "}
              <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>optional</span>
            </label>
            <input
              type="password"
              value={form.auth_token}
              onChange={e => !readOnly && set("auth_token", e.target.value)}
              placeholder="Bearer token or API key"
              readOnly={readOnly}
              style={{ ...inputStyle, opacity: readOnly ? 0.6 : 1 }}
            />
          </div>

          {/* Environment */}
          <div>
            <label style={labelStyle}>Environment</label>
            <select
              value={form.environment_id}
              onChange={e => !readOnly && set("environment_id", e.target.value)}
              disabled={readOnly}
              style={{ ...inputStyle, opacity: readOnly ? 0.6 : 1 }}
            >
              <option value="">All environments</option>
              {environments.map(env => (
                <option key={env.id} value={env.id}>{env.name}</option>
              ))}
            </select>
          </div>

          {error && (
            <p style={{ fontSize: 12, color: "var(--err)", margin: 0 }}>{error}</p>
          )}

          <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
            <button type="submit" disabled={saving} className="btn btn-primary btn-sm">
              {saving ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={onClose} className="btn btn-ghost btn-sm">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main inner component ──────────────────────────────────────────────────────

function IntegrationsPageInner({
  getToken,
  wsId,
}: {
  getToken: (() => Promise<string | null>) | null
  wsId: string
}) {
  const [servers, setServers] = useState<McpServer[]>([])
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [loading, setLoading] = useState(true)
  const [modalMode, setModalMode] = useState<"add" | "edit" | null>(null)
  const [editTarget, setEditTarget] = useState<McpServer | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [globalError, setGlobalError] = useState("")

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  async function buildHeaders(contentType = false): Promise<Record<string, string>> {
    const headers: Record<string, string> = {}
    if (contentType) headers["Content-Type"] = "application/json"
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    if (wsId) headers["X-Workspace-ID"] = wsId
    return headers
  }

  const load = useCallback(async () => {
    setLoading(true)
    setGlobalError("")
    const headers = await buildHeaders()
    // Fetch independently so environments always loads even if mcp-servers table is pending migration
    const [serversRes, envsRes] = await Promise.allSettled([
      fetch(`${base}/mcp-servers${wsId ? `?workspace_id=${wsId}` : ""}`, { headers }),
      fetch(`${base}/environments${wsId ? `?workspace_id=${wsId}` : ""}`, { headers }),
    ])
    if (serversRes.status === "fulfilled" && serversRes.value.ok) {
      const data = await serversRes.value.json().catch(() => [])
      if (Array.isArray(data)) setServers(data)
    }
    if (envsRes.status === "fulfilled" && envsRes.value.ok) {
      const data = await envsRes.value.json().catch(() => [])
      if (Array.isArray(data)) setEnvironments(data)
    }
    setLoading(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsId])

  useEffect(() => { if (wsId) load(); else setLoading(false) }, [load, wsId])

  function envName(envId: string | null): string {
    if (!envId) return "All environments"
    return environments.find(e => e.id === envId)?.name ?? "All environments"
  }

  function openAdd() {
    setEditTarget(null)
    setModalMode("add")
  }

  function openEdit(server: McpServer) {
    setEditTarget(server)
    setModalMode("edit")
  }

  function closeModal() {
    setModalMode(null)
    setEditTarget(null)
  }

  async function handleSave(form: FormState) {
    const headers = await buildHeaders(true)
    const body: Record<string, string | undefined> = {
      name: form.name.trim(),
      url: form.url.trim(),
      transport: form.transport,
    }
    if (form.auth_token.trim()) body.auth_token = form.auth_token.trim()
    if (form.environment_id)    body.environment_id = form.environment_id

    const isEdit = modalMode === "edit" && editTarget
    const url  = isEdit ? `${base}/mcp-servers/${editTarget.id}` : `${base}/mcp-servers`
    const method = isEdit ? "PATCH" : "POST"

    const res = await fetch(url, { method, headers, body: JSON.stringify(body) })
    if (!res.ok) {
      const b = await res.json().catch(() => ({}))
      throw new Error(b.detail ?? "Failed to save.")
    }
    await load()
    closeModal()
  }

  async function handleDelete(server: McpServer) {
    if (!window.confirm(`Delete MCP server "${server.name}"? This cannot be undone.`)) return
    setDeletingId(server.id)
    setGlobalError("")
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/mcp-servers/${server.id}`, { method: "DELETE", headers })
      if (!res.ok) {
        const b = await res.json().catch(() => ({}))
        setGlobalError(b.detail ?? "Failed to delete.")
        return
      }
      setServers(prev => prev.filter(s => s.id !== server.id))
    } finally {
      setDeletingId(null)
    }
  }

  const initialForm: FormState = editTarget
    ? {
        name: editTarget.name,
        url: editTarget.url,
        transport: editTarget.transport,
        auth_token: "",
        environment_id: editTarget.environment_id ?? "",
      }
    : EMPTY_FORM

  return (
    <AppShell>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 24px" }}>
        {/* Page header */}
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: 25, fontWeight: 680, letterSpacing: "-.02em", color: "var(--text)", margin: 0 }}>
            Integrations
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-3)", marginTop: 5, margin: "5px 0 0" }}>
            Connect MCP servers to your workspace.
          </p>
        </div>

        {globalError && (
          <p style={{ fontSize: 13, color: "var(--err)", marginBottom: 16 }}>{globalError}</p>
        )}

        {/* MCP Servers section */}
        <div>
          {/* Section header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-2)", margin: 0 }}>
              MCP Servers
            </h2>
            <button onClick={openAdd} className="btn btn-primary btn-sm">
              Add MCP server
            </button>
          </div>

          {/* Server list */}
          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[1, 2].map(i => (
                <div key={i} className="card" style={{ height: 68, opacity: 0.4, borderRadius: 10 }} />
              ))}
            </div>
          ) : servers.length === 0 ? (
            <div
              className="card"
              style={{
                textAlign: "center",
                padding: "40px 24px",
                color: "var(--text-muted)",
                fontSize: 13,
              }}
            >
              No MCP servers connected yet. Add one to get started.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {servers.map(server => {
                const tc = TRANSPORT_COLORS[server.transport] ?? TRANSPORT_COLORS.http
                return (
                  <div key={server.id} className="card" style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                      {/* Left: info */}
                      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                        {/* Transport badge */}
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            padding: "3px 8px",
                            borderRadius: 6,
                            background: tc.bg,
                            color: tc.color,
                            flexShrink: 0,
                            letterSpacing: "0.02em",
                            border: server.transport !== "sse" ? "1px solid var(--border)" : "none",
                          }}
                        >
                          {TRANSPORT_LABELS[server.transport]}
                        </span>

                        <div style={{ minWidth: 0 }}>
                          <p style={{ fontSize: 13, fontWeight: 500, color: "var(--text)", margin: 0 }}>
                            {server.name}
                            {server.has_auth && (
                              <span
                                title="Auth token configured"
                                style={{
                                  marginLeft: 6,
                                  fontSize: 10,
                                  fontWeight: 600,
                                  padding: "2px 6px",
                                  borderRadius: 5,
                                  background: "var(--surface-2)",
                                  color: "var(--text-3)",
                                  border: "1px solid var(--border)",
                                }}
                              >
                                AUTH
                              </span>
                            )}
                          </p>
                          <p
                            style={{
                              fontSize: 12,
                              color: "var(--text-muted)",
                              margin: "2px 0 0",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              maxWidth: 400,
                            }}
                          >
                            {server.url}
                          </p>
                        </div>
                      </div>

                      {/* Right: meta + actions */}
                      <div style={{ display: "flex", alignItems: "center", gap: 16, flexShrink: 0 }}>
                        <div style={{ textAlign: "right" }}>
                          <p style={{ fontSize: 12, color: "var(--text-3)", margin: 0 }}>
                            {envName(server.environment_id)}
                          </p>
                          <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "2px 0 0" }}>
                            Added {formatDate(server.created_at)}
                          </p>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <button
                            onClick={() => openEdit(server)}
                            className="btn btn-ghost btn-sm"
                            style={{ color: "var(--text-2)" }}
                          >
                            Edit
                          </button>
                          {!server.is_system && (
                            <button
                              onClick={() => handleDelete(server)}
                              disabled={deletingId === server.id}
                              className="btn btn-ghost btn-sm"
                              style={{ color: "var(--err)" }}
                            >
                              {deletingId === server.id ? "Deleting…" : "Delete"}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Add / Edit modal */}
      {modalMode && (
        <McpModal
          mode={modalMode}
          isSystem={!!editTarget?.is_system}
          initial={initialForm}
          environments={environments}
          onSave={handleSave}
          onClose={closeModal}
        />
      )}
    </AppShell>
  )
}
