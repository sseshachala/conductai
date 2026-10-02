"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ChevronLeft, ChevronRight, Link2, RefreshCw, Unlink } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { discoveryLabel, discoveryTime } from "@/lib/discovery"
import styles from "./McpInventoryLinks.module.css"

type Registration = { id: string; name: string; review_status: string }
type Finding = {
  reference_id: string; name: string; scope: string | null; transport: string | null
  discovery_status: string; registration_status: string; registration: Registration | null
  association_source: string | null; linked_at: string | null
  endpoint_identity: string; enforcement_status: string
}
type Installation = {
  agent_id: string; framework: string; device_id: string; installation_id: string
  last_seen_at: string; revision: number; servers: Finding[]
}
type Inventory = { registrations: Registration[]; installations: Installation[]; next_offset: number | null }
const labels: Record<string, string> = {
  discovered: "Discovered", disabled: "Disabled", stale: "Stale scan", unreadable: "Config unreadable", not_reported: "No longer reported",
  unlinked: "Not linked", registration_missing: "Registration removed", linked: "Linked by admin",
  not_enrolled: "Not enrolled", needs_review: "Needs review", approved: "Approved catalog",
  quarantined: "Quarantined", revoked: "Revoked", invalid: "Invalid review state",
}

function Association({ finding, installation, registrations, isAdmin, busy, save }: {
  finding: Finding; installation: Installation; registrations: Registration[]; isAdmin: boolean; busy: boolean
  save: (installation: Installation, reference: string, server: string | null) => void
}) {
  const [selected, setSelected] = useState(finding.registration?.id ?? "")
  const canLink = ["discovered", "disabled"].includes(finding.discovery_status)
  return <div className={styles.association}>
    <span>{finding.registration?.name ?? labels[finding.registration_status]}</span>
    {finding.association_source && <small title={discoveryTime(finding.linked_at)}>Admin association</small>}
    {isAdmin && <div className={styles.linkControls}>
      {canLink && <>
        <select aria-label={`Registration for ${finding.name}`} value={selected} disabled={busy}
          onChange={event => setSelected(event.target.value)}>
          <option value="">Select registration</option>
          {registrations.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
        </select>
        <button className="btn btn-ghost btn-sm btn-icon" title="Link registration" aria-label={`Link ${finding.name}`}
          disabled={busy || !selected || selected === finding.registration?.id}
          onClick={() => save(installation, finding.reference_id, selected)}><Link2 size={16} /></button>
      </>}
      {finding.association_source && <button className="btn btn-ghost btn-sm btn-icon" title="Remove association"
        aria-label={`Unlink ${finding.name}`} disabled={busy}
        onClick={() => save(installation, finding.reference_id, null)}><Unlink size={16} /></button>}
    </div>}
  </div>
}

export default function McpInventoryLinks({ workspaceId, isAdmin }: { workspaceId: string; isAdmin: boolean }) {
  const { authFetch } = useAuthFetch()
  const [data, setData] = useState<Inventory | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [offset, setOffset] = useState(0)
  useEffect(() => {
    let cancelled = false
    setData(null); setError(""); setBusy(true)
    void (async () => {
      try {
        const res = await authFetch(`${API}/guard/discover/mcp-reconciliation?workspace_id=${encodeURIComponent(workspaceId)}&limit=100&offset=${offset}`)
        if (!res.ok) throw new Error(res.status === 403 ? "MCP inventory access denied." : "MCP inventory unavailable.")
        const body = await res.json()
        if (!cancelled) setData(body)
      } catch (err) { if (!cancelled) setError(err instanceof Error ? err.message : "MCP inventory unavailable.") }
      finally { if (!cancelled) setBusy(false) }
    })()
    return () => { cancelled = true }
  }, [authFetch, workspaceId, offset, refresh])

  async function save(installation: Installation, reference: string, server: string | null) {
    setBusy(true); setError("")
    try {
      const res = await authFetch(`${API}/guard/discover/agents/${installation.agent_id}/mcp-links/${reference}?workspace_id=${encodeURIComponent(workspaceId)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ server_id: server, revision: installation.revision }),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Association update failed.")
      setData(current => current ? { ...current, installations: current.installations.map(row => row.agent_id === body.agent_id ? body : row) } : current)
    } catch (err) { setError(err instanceof Error ? err.message : "Association update failed.") }
    finally { setBusy(false) }
  }

  return <div className={styles.inventory}>
    <div className={styles.header}>
      <Link href="/integrations">Review registered servers</Link>
      <button className="btn btn-ghost btn-sm btn-icon" title="Refresh MCP inventory" aria-label="Refresh MCP inventory"
        disabled={busy} onClick={() => setRefresh(n => n + 1)}><RefreshCw size={16} /></button>
    </div>
    {busy && <p role="status">Loading...</p>}
    {error && <p role="alert">{error}</p>}
    {data && <>
      <div className={styles.table}><table aria-label="MCP inventory associations">
        <thead><tr><th>Tool / device</th><th>MCP reference</th><th>Discovery</th><th>Registration</th><th>Registration review</th><th>Device traffic</th></tr></thead>
        <tbody>{data.installations.flatMap(installation => installation.servers.map(finding => <tr key={`${installation.agent_id}:${finding.reference_id}`}>
          <td title={`Device ${installation.device_id}; installation ${installation.installation_id}`}>
            {discoveryLabel(installation.framework)}<br /><code>{installation.device_id.slice(0, 8)} / {installation.installation_id.slice(0, 8)}</code>
          </td>
          <td>{finding.name}<br /><small>{finding.scope} / {finding.transport}</small></td>
          <td title={discoveryTime(installation.last_seen_at)}>{labels[finding.discovery_status]}</td>
          <td><Association key={`${installation.revision}:${finding.reference_id}`} finding={finding} installation={installation}
            registrations={data.registrations} isAdmin={isAdmin} busy={busy} save={save} /></td>
          <td>{finding.registration ? labels[finding.registration.review_status] : "Unknown"}</td>
          <td>Not observed<br /><small>Endpoint identity unverified</small></td>
        </tr>))}
          {!data.installations.some(row => row.servers.length) && <tr><td colSpan={6}>No MCP references on this page</td></tr>}
        </tbody>
      </table></div>
      <div className={styles.linkControls}>
        <button className="btn btn-ghost btn-sm btn-icon" title="Previous page" aria-label="Previous MCP page" disabled={busy || offset === 0}
          onClick={() => setOffset(n => Math.max(0, n - 100))}><ChevronLeft size={16} /></button>
        <span>Page {Math.floor(offset / 100) + 1}</span>
        <button className="btn btn-ghost btn-sm btn-icon" title="Next page" aria-label="Next MCP page" disabled={busy || data.next_offset === null}
          onClick={() => setOffset(data.next_offset!)}><ChevronRight size={16} /></button>
      </div>
    </>}
  </div>
}
