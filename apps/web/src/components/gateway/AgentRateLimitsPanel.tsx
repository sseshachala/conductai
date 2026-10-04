"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { RotateCw } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import RateLimitsPanel from "./RateLimitsPanel"
import styles from "./RateLimitsPanel.module.css"

export default function AgentRateLimitsPanel({ workspaceId, isAdmin }: {
  workspaceId: string; isAdmin: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [agents, setAgents] = useState<Array<{ id: string; name: string }>>([])
  const [selected, setSelected] = useState("")
  const [loadedWorkspace, setLoadedWorkspace] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let current = true
    setLoading(true); setError(null); setLoadedWorkspace(""); setAgents([]); setSelected("")
    if (!workspaceId || !isAdmin) return
    guard.rateLimits.agents(authFetch, workspaceId).then(rows => {
      if (!current) return
      setAgents(rows); setLoadedWorkspace(workspaceId)
    }).catch(reason => {
      if (current) setError(reason instanceof Error ? reason.message : "Could not load agent identities.")
    }).finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [authFetch, workspaceId, isAdmin, reload])

  if (!isAdmin) return <p className={styles.empty}>Rate limits are managed by workspace admins.</p>
  if (error) return <div role="alert" className={styles.error}>{error}
    <button type="button" className="btn btn-ghost btn-sm" title="Retry loading agents"
      aria-label="Retry loading agents" onClick={() => setReload(value => value + 1)}><RotateCw size={14} /></button>
  </div>
  if (loading || loadedWorkspace !== workspaceId) return <p role="status" className={styles.empty}>Loading...</p>
  if (!agents.length) return <div className={styles.empty}>
    <p>No agent identities.</p><Link href="/agent-identity?tab=identities">Agent identities</Link>
  </div>
  const agent = agents.find(row => row.id === selected)

  return <div className={styles.body}>
    <label className={`${styles.profilePicker} ${styles.agentPicker}`}>Agent identity
      <select aria-label="Agent identity" title={agent && `${agent.name} (${agent.id})`}
        value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">Select agent</option>
        {agents.map(row => <option key={row.id} value={row.id} title={`${row.name} (${row.id})`}>
          {row.name} ({row.id.length > 16 ? `${row.id.slice(0, 8)}...${row.id.slice(-4)}` : row.id})
        </option>)}
      </select>
    </label>
    {agent && <>
      <div className={styles.identity}><strong>{agent.name}</strong><code>{agent.id}</code></div>
      <RateLimitsPanel key={`${workspaceId}:${selected}`} workspaceId={workspaceId} agentId={selected} isAdmin={isAdmin} />
    </>}
  </div>
}
