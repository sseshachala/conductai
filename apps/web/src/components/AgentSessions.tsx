"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, RefreshCw, ShieldOff } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

interface AgentSession {
  id: string
  created_at: string
  expires_at: string
  refresh_token_expires_at: string
  revoked_at: string | null
  status: "active" | "refreshable" | "expired" | "revoked" | "blocked"
  is_current: boolean
}

const labels = { active: "Active", refreshable: "Refreshable", expired: "Expired", revoked: "Revoked", blocked: "Blocked" }
const date = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })

export function AgentSessions({ workspaceId, identityId }: { workspaceId: string; identityId: string }) {
  const { authFetch } = useAuthFetch()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [rows, setRows] = useState<AgentSession[]>([])
  const [page, setPage] = useState(0)
  const [version, setVersion] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const base = `${API}/workspaces/${encodeURIComponent(workspaceId)}/agent-identities/${encodeURIComponent(identityId)}/sessions`

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setExpanded(null)
    fetchRef.current(`${base}?limit=50&offset=${page * 50}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 403 ? "You do not have permission to manage agent sessions." : "Unable to load agent sessions.")
        return response.json()
      })
      .then(data => {
        if (controller.signal.aborted) return
        setRows(data.sessions)
        setHasMore(data.has_more)
      })
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [base, page, version])

  async function revoke(session: AgentSession) {
    const warning = session.is_current ? " This disconnects your current authenticated connection." : " The connected client will need to sign in again."
    if (!window.confirm(`Revoke session ${session.id.slice(0, 8)}?${warning}`)) return
    setRevoking(session.id)
    setError(null)
    try {
      const response = await fetchRef.current(`${base}/${encodeURIComponent(session.id)}/revoke`, { method: "POST" })
      if (!response.ok) throw new Error("Unable to revoke this session.")
      const updated: AgentSession = await response.json()
      setRows(current => current.map(row => row.id === updated.id ? updated : row))
    } catch {
      setError("Unable to revoke this session.")
    } finally {
      setRevoking(null)
    }
  }

  const selected = rows.find(row => row.id === expanded)
  return (
    <section aria-label="Authentication sessions">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] pb-3">
        <h3 className="text-sm font-semibold">Authentication sessions</h3>
        <button type="button" className="btn btn-sm min-h-8 min-w-8 disabled:opacity-40" title="Refresh sessions" aria-label="Refresh sessions" disabled={loading || !!revoking} onClick={() => setVersion(v => v + 1)}><RefreshCw size={15} /></button>
      </div>
      {error && <div role="alert" className="py-3 text-sm text-[var(--err)]">{error}</div>}
      {loading ? <p role="status" className="py-5 text-sm text-[var(--text-muted)]">Loading sessions...</p> : (
        <>
          {!error && rows.length === 0 && <p className="py-5 text-sm text-[var(--text-muted)]">No authentication sessions for this agent.</p>}
          {rows.length > 0 && <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] border-collapse text-left text-xs">
              <thead className="text-[var(--text-muted)]"><tr>
                {['Session', 'Created', 'Access expires', 'Status', ''].map((label, i) => <th key={i} className="px-3 py-3 font-medium">{label || <span className="sr-only">Actions</span>}</th>)}
              </tr></thead>
              <tbody>{rows.map(session => <tr key={session.id} className="border-t border-[var(--border)]">
                <td className="px-3 py-3">
                  <button type="button" className="font-mono underline underline-offset-4" aria-expanded={expanded === session.id} title={session.id} onClick={() => setExpanded(expanded === session.id ? null : session.id)}>{session.id.slice(0, 8)}</button>
                  {session.is_current && <div className="mt-1 text-[var(--text-muted)]">This session</div>}
                </td>
                <td className="px-3 py-3"><time dateTime={session.created_at}>{date(session.created_at)}</time></td>
                <td className="px-3 py-3"><time dateTime={session.expires_at}>{date(session.expires_at)}</time></td>
                <td className="px-3 py-3"><span className={session.status === 'active' ? 'text-[var(--ok)]' : session.status === 'refreshable' ? 'text-[var(--warn)]' : 'text-[var(--text-muted)]'}>{labels[session.status]}</span></td>
                <td className="px-3 py-3 text-right"><button type="button" className="btn btn-sm inline-flex min-w-24 items-center justify-center gap-1.5 disabled:opacity-40" disabled={!!revoking || session.status === 'revoked' || session.status === 'expired'} aria-label={`Revoke session ${session.id.slice(0, 8)}`} onClick={() => revoke(session)}><ShieldOff size={14} />{revoking === session.id ? 'Revoking...' : 'Revoke'}</button></td>
              </tr>)}</tbody>
            </table>
          </div>}
          {selected && <dl className="grid gap-2 border-t border-[var(--border)] py-4 text-xs sm:grid-cols-[120px_1fr]">
            <dt className="text-[var(--text-muted)]">Session ID</dt><dd className="break-all font-mono">{selected.id}</dd>
            <dt className="text-[var(--text-muted)]">Refresh expires</dt><dd>{date(selected.refresh_token_expires_at)}</dd>
            {selected.revoked_at && <><dt className="text-[var(--text-muted)]">Revoked</dt><dd>{date(selected.revoked_at)}</dd></>}
          </dl>}
        </>
      )}
      <div className="flex items-center justify-end gap-3 border-t border-[var(--border)] pt-3 text-xs">
        <button type="button" className="btn btn-sm" aria-label="Previous sessions" title="Previous sessions" disabled={loading || !!revoking || page === 0} onClick={() => setPage(p => p - 1)}><ChevronLeft size={15} /></button>
        <span>Page {page + 1}</span>
        <button type="button" className="btn btn-sm" aria-label="Next sessions" title="Next sessions" disabled={loading || !!revoking || !hasMore || !!error} onClick={() => setPage(p => p + 1)}><ChevronRight size={15} /></button>
      </div>
    </section>
  )
}
