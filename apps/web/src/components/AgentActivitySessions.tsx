"use client"

import { useEffect, useRef, useState } from "react"
import { Activity, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

interface ActivitySession {
  session_id: string
  tools: string[]
  first_seen: string
  last_seen: string
  event_count: number
  warned_count: number
  blocked_count: number
}

const time = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })

export function AgentActivitySessions({ workspaceId, identityId }: { workspaceId: string; identityId: string }) {
  const { authFetch } = useAuthFetch()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const [rows, setRows] = useState<ActivitySession[]>([])
  const [page, setPage] = useState(0)
  const [version, setVersion] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setRows([])
    fetchRef.current(`${API}/workspaces/${encodeURIComponent(workspaceId)}/agent-identities/${encodeURIComponent(identityId)}/activity-sessions?limit=50&offset=${page * 50}`, { signal: controller.signal })
      .then(async res => {
        if (!res.ok) throw new Error(res.status === 403 ? "You do not have permission to view these sessions." : "Unable to load recorded sessions.")
        return res.json()
      })
      .then(data => { if (!controller.signal.aborted) { setRows(data.sessions); setHasMore(data.has_more) } })
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [workspaceId, identityId, page, version])
  return <section aria-label="Recorded activity sessions">
    <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] pb-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold"><Activity size={16} />Recorded activity</h3>
      <button type="button" className="btn btn-sm" title="Refresh activity sessions" aria-label="Refresh activity sessions" disabled={loading} onClick={() => setVersion(v => v + 1)}><RefreshCw size={15} /></button>
    </div>
    {loading ? <p role="status" className="py-5 text-sm text-[var(--text-muted)]">Loading recorded sessions...</p> : error ? <p role="alert" className="py-5 text-sm text-[var(--err)]">{error}</p> : <>
      {!rows.length ? <p className="py-5 text-sm text-[var(--text-muted)]">No activity sessions attributed to this agent yet.</p> : <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] text-left text-xs">
          <thead><tr>{["Session", "Tool", "First seen", "Last activity", "Events", "Warned", "Blocked"].map(label => <th key={label} className="px-3 py-3 font-medium text-[var(--text-muted)]">{label}</th>)}</tr></thead>
          <tbody>{rows.map(row => <tr key={row.session_id} className="border-t border-[var(--border)]">
            <td className="px-3 py-3"><a className="font-mono underline underline-offset-4" title={row.session_id} href={`/logs/guard?view=events&hook_session_id=${encodeURIComponent(row.session_id)}&agent_identity_id=${encodeURIComponent(identityId)}`}>{row.session_id.slice(0, 8)}</a></td>
            <td className="px-3 py-3">{row.tools.join(", ") || "Unknown"}</td>
            <td className="px-3 py-3"><time dateTime={row.first_seen}>{time(row.first_seen)}</time></td>
            <td className="px-3 py-3"><time dateTime={row.last_seen}>{time(row.last_seen)}</time></td>
            <td className="px-3 py-3 tabular-nums">{row.event_count}</td>
            <td className="px-3 py-3 tabular-nums text-[var(--warn)]">{row.warned_count || "-"}</td>
            <td className="px-3 py-3 tabular-nums text-[var(--err)]">{row.blocked_count || "-"}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      {(page > 0 || hasMore) && <div className="flex items-center justify-end gap-3 border-t border-[var(--border)] py-3 text-xs">
        <button className="btn btn-sm" aria-label="Previous activity page" title="Previous page" disabled={page === 0} onClick={() => setPage(p => p - 1)}><ChevronLeft size={15} /></button>
        <span>Page {page + 1}</span>
        <button className="btn btn-sm" aria-label="Next activity page" title="Next page" disabled={!hasMore} onClick={() => setPage(p => p + 1)}><ChevronRight size={15} /></button>
      </div>}
    </>}
  </section>
}
