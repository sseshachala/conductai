"use client"

import { useEffect, useState } from "react"

interface AuditEntry {
  id: string
  actor_id: string | null
  actor_email: string | null
  actor_role: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  metadata: Record<string, string | number | boolean | null | object> | null
  created_at: string | null
}

interface Props {
  workspaceId: string
  getToken?: (() => Promise<string | null>) | null
}

type ActionStyle = { background: string; color: string }

const ACTION_STYLES: Record<string, ActionStyle> = {
  "credential.upserted": { background: "rgba(59,130,246,0.08)", color: "#1d4ed8" },
  "credential.deleted":  { background: "rgba(239,68,68,0.08)",  color: "#b91c1c" },
  "workflow.created":    { background: "rgba(34,197,94,0.08)",   color: "#15803d" },
  "workflow.deleted":    { background: "rgba(239,68,68,0.08)",   color: "#b91c1c" },
  "run.triggered":       { background: "rgba(168,85,247,0.08)",  color: "#7e22ce" },
  "member.invited":      { background: "rgba(245,158,11,0.08)",  color: "#b45309" },
  "member.removed":      { background: "rgba(239,68,68,0.08)",   color: "#b91c1c" },
  "member.role_changed": { background: "rgba(249,115,22,0.08)",  color: "#c2410c" },
}

const ACTION_STYLE_DEFAULT: ActionStyle = { background: "var(--surface-3)", color: "var(--text-2)" }

function fmt(ts: string | null) {
  if (!ts) return "—"
  return new Date(ts).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
}

function actionLabel(action: string) {
  return action.replace(".", " ").replace(/_/g, " ")
}

function getCookieWorkspaceId(): string {
  if (typeof document === "undefined") return ""
  return document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] ?? ""
}

export default function AuditLog({ workspaceId, getToken }: Props) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionFilter, setActionFilter] = useState("")
  const [page, setPage] = useState(0)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const limit = 50

  async function load(offset = 0) {
    setLoading(true)
    setError(null)
    try {
      const h: Record<string, string> = {}
      if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
      const ws = getCookieWorkspaceId()
      const effectiveWorkspaceId = workspaceId || ws
      if (!effectiveWorkspaceId) {
        setEntries([])
        return
      }
      if (ws) h["X-Workspace-Id"] = ws

      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
      if (actionFilter) params.set("action", actionFilter)

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workspaces/${effectiveWorkspaceId}/audit-log?${params}`,
        { headers: h }
      )
      if (!res.ok) throw res
      setEntries(await res.json())
    } catch (e) {
      if (e instanceof Response && e.status === 403) {
        setError("You don't have permission to view the activity log.")
      } else {
        setError("Could not load audit log. Check workspace access or refresh.")
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(page * limit) }, [workspaceId, page, actionFilter])

  function exportCsv() {
    const cols = ["created_at", "action", "actor_email", "actor_role", "resource_type", "resource_id"]
    const rows = [cols.join(",")]
    for (const e of entries) {
      rows.push(cols.map(c => JSON.stringify((e as unknown as Record<string, unknown>)[c] ?? "")).join(","))
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a"); a.href = url; a.download = "audit-log.csv"
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Audit Log</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <select
            value={actionFilter}
            onChange={e => { setActionFilter(e.target.value); setPage(0) }}
            style={{ fontSize: 12, border: "1px solid var(--border)", borderRadius: 8, padding: "5px 8px", color: "var(--text-2)", background: "var(--surface)", outline: "none" }}
          >
            <option value="">Action</option>
            <optgroup label="Credentials">
              <option value="credential.upserted">Credential added / updated</option>
              <option value="credential.deleted">Credential deleted</option>
            </optgroup>
            <optgroup label="Agents">
              <option value="workflow.created">Agent created</option>
              <option value="workflow.deleted">Agent deleted</option>
            </optgroup>
            <optgroup label="Runs">
              <option value="run.triggered">Run triggered</option>
            </optgroup>
            <optgroup label="Members">
              <option value="member.invited">Member invited</option>
              <option value="member.removed">Member removed</option>
              <option value="member.role_changed">Role changed</option>
            </optgroup>
          </select>
          <button onClick={exportCsv} className="btn btn-ghost btn-sm">
            Export
          </button>
        </div>
      </div>

      {error && <p style={{ fontSize: 12, color: "var(--err)" }}>{error}</p>}

      {loading ? (
        <p style={{ fontSize: 12, color: "var(--text-muted)", padding: "16px 0", textAlign: "center" }}>Loading…</p>
      ) : entries.length === 0 ? (
        <p style={{ fontSize: 12, color: "var(--text-muted)", padding: "16px 0", textAlign: "center" }}>No audit events yet. Credential changes, agent runs, and member changes will appear here.</p>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {entries.map(e => {
            const isOpen = expandedId === e.id
            const isHovered = hoveredId === e.id
            const meta = e.metadata ?? {}
            const metaEntries = Object.entries(meta)
            const badgeStyle = ACTION_STYLES[e.action] ?? ACTION_STYLE_DEFAULT
            return (
              <div key={e.id}>
                <button
                  onClick={() => setExpandedId(isOpen ? null : e.id)}
                  onMouseEnter={() => setHoveredId(e.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 12,
                    padding: "10px 16px",
                    fontSize: 12,
                    textAlign: "left",
                    borderBottom: "1px solid var(--border)",
                    background: isHovered ? "var(--surface-2)" : "none",
                    border: "none",
                    borderBottomWidth: 1,
                    borderBottomStyle: "solid",
                    borderBottomColor: "var(--border)",
                    cursor: "pointer",
                    transition: "background 0.15s",
                  }}
                >
                  <span style={{ color: "var(--text-muted)", whiteSpace: "nowrap", flexShrink: 0, paddingTop: 2 }}>
                    {fmt(e.created_at)}
                  </span>
                  <span style={{
                    flexShrink: 0,
                    padding: "2px 6px",
                    borderRadius: 4,
                    fontWeight: 500,
                    fontSize: 10,
                    background: badgeStyle.background,
                    color: badgeStyle.color,
                  }}>
                    {actionLabel(e.action)}
                  </span>
                  <span style={{ color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                    {e.actor_email ?? e.actor_id ?? "system"}
                    {meta.name != null ? (
                      <span style={{ marginLeft: 6, fontWeight: 500, color: "var(--text)" }}>— {String(meta.name)}</span>
                    ) : e.resource_id ? (
                      <span className="mono" style={{ marginLeft: 6, color: "var(--text-muted)" }}>
                        {e.resource_type} {e.resource_id.slice(0, 8)}
                      </span>
                    ) : null}
                  </span>
                  <span style={{ marginLeft: "auto", flexShrink: 0, color: "var(--text-muted)" }}>
                    {isOpen ? "▲" : "▼"}
                  </span>
                </button>

                {isOpen && (
                  <div style={{ padding: "4px 16px 12px", background: "var(--surface-2)", borderTop: "1px solid var(--border)", fontSize: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", columnGap: 12, rowGap: 6 }}>
                      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Action</span>
                      <span style={{ color: "var(--text-2)" }}>{e.action}</span>

                      {e.actor_email && <>
                        <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Actor</span>
                        <span style={{ color: "var(--text-2)" }}>{e.actor_email}{e.actor_role ? ` (${e.actor_role})` : ""}</span>
                      </>}

                      {e.resource_type && <>
                        <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Resource</span>
                        <span className="mono" style={{ color: "var(--text-2)" }}>{e.resource_type}</span>
                      </>}

                      {e.resource_id && <>
                        <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Resource ID</span>
                        <span className="mono" style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{e.resource_id}</span>
                      </>}

                      {e.created_at && <>
                        <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Timestamp</span>
                        <span style={{ color: "var(--text-2)" }}>{new Date(e.created_at).toLocaleString()}</span>
                      </>}

                      {metaEntries.length > 0 && <>
                        <span style={{ gridColumn: "1 / -1", paddingTop: 4, borderTop: "1px solid var(--border)", color: "var(--text-muted)", fontWeight: 500 }}>Details</span>
                        {metaEntries.map(([k, v]) => (
                          <>
                            <span key={`k-${k}`} style={{ color: "var(--text-muted)", paddingLeft: 8 }}>{k}</span>
                            <span key={`v-${k}`} className="mono" style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{typeof v === "object" ? JSON.stringify(v) : String(v ?? "")}</span>
                          </>
                        ))}
                      </>}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "flex-end", fontSize: 12, color: "var(--text-muted)" }}>
        <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
          className="btn btn-ghost btn-sm">← prev</button>
        <span>page {page + 1}</span>
        <button onClick={() => setPage(p => p + 1)} disabled={entries.length < limit}
          className="btn btn-ghost btn-sm">next →</button>
      </div>
    </div>
  )
}
