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

const ACTION_COLORS: Record<string, string> = {
  "credential.upserted": "bg-blue-50 text-blue-700",
  "credential.deleted":  "bg-red-50 text-red-700",
  "workflow.created":    "bg-green-50 text-green-700",
  "workflow.deleted":    "bg-red-50 text-red-700",
  "run.triggered":       "bg-purple-50 text-purple-700",
  "member.invited":      "bg-amber-50 text-amber-700",
  "member.removed":      "bg-red-50 text-red-700",
  "member.role_changed": "bg-orange-50 text-orange-700",
}

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
    const a = document.createElement("a"); a.href = url; a.download = "audit-log.csv"; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="text-sm font-semibold text-stone-800">Audit Log</h3>
        <div className="flex items-center gap-2">
          <select
            value={actionFilter}
            onChange={e => { setActionFilter(e.target.value); setPage(0) }}
            className="text-xs border border-stone-200 rounded-lg px-2 py-1.5 text-stone-600 bg-white"
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
          <button
            onClick={exportCsv}
            className="text-xs text-stone-500 hover:text-stone-800 border border-stone-200 rounded-lg px-3 py-1.5 transition-colors"
          >
            Export
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {loading ? (
        <p className="text-xs text-stone-400 py-4 text-center">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-xs text-stone-400 py-6 text-center">No audit events yet. Credential changes, agent runs, and member changes will appear here.</p>
      ) : (
        <div className="divide-y divide-stone-100 border border-stone-200 rounded-xl overflow-hidden">
          {entries.map(e => {
            const isOpen = expandedId === e.id
            const meta = e.metadata ?? {}
            const metaEntries = Object.entries(meta)
            return (
              <div key={e.id}>
                <button
                  onClick={() => setExpandedId(isOpen ? null : e.id)}
                  className="w-full flex items-start gap-3 px-4 py-2.5 text-xs hover:bg-stone-50 text-left transition-colors"
                >
                  <span className="text-stone-400 whitespace-nowrap shrink-0 pt-0.5">{fmt(e.created_at)}</span>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded font-medium text-[10px] ${ACTION_COLORS[e.action] ?? "bg-stone-100 text-stone-600"}`}>
                    {actionLabel(e.action)}
                  </span>
                  <span className="text-stone-600 truncate flex-1">
                    {e.actor_email ?? e.actor_id ?? "system"}
                    {meta.name != null ? (
                      <span className="ml-1.5 font-medium text-stone-800">— {String(meta.name)}</span>
                    ) : e.resource_id ? (
                      <span className="ml-1.5 text-stone-400 font-mono">
                        {e.resource_type} {e.resource_id.slice(0, 8)}
                      </span>
                    ) : null}
                  </span>
                  <span className="ml-auto shrink-0 text-stone-300">{isOpen ? "▲" : "▼"}</span>
                </button>

                {isOpen && (
                  <div className="px-4 pb-3 pt-1 bg-stone-50 border-t border-stone-100 text-xs space-y-2">
                    <div className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5">
                      <span className="text-stone-400 font-medium">Action</span>
                      <span className="text-stone-700">{e.action}</span>

                      {e.actor_email && <>
                        <span className="text-stone-400 font-medium">Actor</span>
                        <span className="text-stone-700">{e.actor_email}{e.actor_role ? ` (${e.actor_role})` : ""}</span>
                      </>}

                      {e.resource_type && <>
                        <span className="text-stone-400 font-medium">Resource</span>
                        <span className="text-stone-700 font-mono">{e.resource_type}</span>
                      </>}

                      {e.resource_id && <>
                        <span className="text-stone-400 font-medium">Resource ID</span>
                        <span className="text-stone-700 font-mono break-all">{e.resource_id}</span>
                      </>}

                      {e.created_at && <>
                        <span className="text-stone-400 font-medium">Timestamp</span>
                        <span className="text-stone-700">{new Date(e.created_at).toLocaleString()}</span>
                      </>}

                      {metaEntries.length > 0 && <>
                        <span className="text-stone-400 font-medium col-span-2 pt-1 border-t border-stone-200">Details</span>
                        {metaEntries.map(([k, v]) => (
                          <>
                            <span key={`k-${k}`} className="text-stone-400 pl-2">{k}</span>
                            <span key={`v-${k}`} className="text-stone-700 font-mono break-all">{typeof v === "object" ? JSON.stringify(v) : String(v ?? "")}</span>
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
      <div className="flex items-center gap-3 justify-end text-xs text-stone-400">
        <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
          className="disabled:opacity-40 hover:text-stone-700">← prev</button>
        <span>page {page + 1}</span>
        <button onClick={() => setPage(p => p + 1)} disabled={entries.length < limit}
          className="disabled:opacity-40 hover:text-stone-700">next →</button>
      </div>
    </div>
  )
}
