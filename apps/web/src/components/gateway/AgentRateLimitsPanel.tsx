"use client"

import { useEffect, useState } from "react"
import { RotateCw } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import RateLimitsPanel from "./RateLimitsPanel"
import styles from "./RateLimitsPanel.module.css"

export default function AgentRateLimitsPanel({ workspaceId, isAdmin }: {
  workspaceId: string; isAdmin: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [profiles, setProfiles] = useState<GatewayProfileV2Out[]>([])
  const [selected, setSelected] = useState("")
  const [loadedWorkspace, setLoadedWorkspace] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let current = true
    setLoading(true); setError(null); setLoadedWorkspace(""); setProfiles([]); setSelected("")
    if (!workspaceId || !isAdmin) return
    guard.gatewayProfilesV2.list(authFetch, workspaceId).then(rows => {
      if (!current) return
      setProfiles(rows); setSelected(rows[0]?.id ?? ""); setLoadedWorkspace(workspaceId)
    }).catch(reason => {
      if (current) setError(reason instanceof Error ? reason.message : "Could not load Gateway profiles.")
    }).finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [authFetch, workspaceId, isAdmin, reload])

  if (!isAdmin) return <p className={styles.empty}>Rate limits are managed by workspace admins.</p>
  if (error) return <div role="alert" className={styles.error}>{error}
    <button type="button" className="btn btn-ghost btn-sm" title="Retry loading profiles"
      aria-label="Retry loading profiles" onClick={() => setReload(value => value + 1)}><RotateCw size={14} /></button>
  </div>
  if (loading || loadedWorkspace !== workspaceId) return <p role="status" className={styles.empty}>Loading...</p>
  if (!profiles.length) return <div className={styles.empty}>
    <p>No Gateway profiles.</p><a href="/proxy/gateway-profiles">Gateway profiles</a>
  </div>

  return <div className={styles.body}>
    <label className={styles.profilePicker}>Gateway profile
      <select aria-label="Gateway profile" value={selected} onChange={event => setSelected(event.target.value)}>
        {profiles.map(profile => <option key={profile.id} value={profile.id}>
          {profile.name} - cond-{profile.cond_code}{profile.model_alias ? `-${profile.model_alias}` : ""}
        </option>)}
      </select>
    </label>
    <RateLimitsPanel key={`${workspaceId}:${selected}`} workspaceId={workspaceId}
      profileId={selected} isAdmin={isAdmin} agentOnly />
  </div>
}
