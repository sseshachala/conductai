"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useParams, useSearchParams } from "next/navigation"

import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { environments, guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { type DetailTab, LIST_HREF, ProfileDetail } from "../_components/ProfileDetail"
import type { EnvironmentRow } from "../_components/presets"

const TABS: DetailTab[] = ["overview", "edit", "revisions", "rate-limits", "test"]

export default function GatewayProfileDetailPage() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { role } = useGuardRole()
  const workspaceId = activeWorkspace?.id ?? ""
  const params = useParams<{ id: string }>()
  const id = params?.id ?? ""
  const tabParam = useSearchParams()?.get("tab") ?? ""
  const initialTab = (TABS as string[]).includes(tabParam) ? (tabParam as DetailTab) : "overview"

  const [profile, setProfile] = useState<GatewayProfileV2Out | null>(null)
  const [envs, setEnvs] = useState<EnvironmentRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const generation = useRef(0)

  const load = useCallback(async () => {
    const current = ++generation.current
    if (!workspaceId || !id) return
    try {
      const [row, envRows] = await Promise.all([
        guard.gatewayProfilesV2.get(authFetch, workspaceId, id),
        environments.list(authFetch),
      ])
      if (current !== generation.current) return
      setProfile(row); setEnvs(envRows); setError("")
    } catch (err) {
      if (current === generation.current) {
        setProfile(null)
        setError(err instanceof Error ? err.message : "Failed to load profile")
      }
    } finally { if (current === generation.current) setLoading(false) }
  }, [authFetch, workspaceId, id])

  useEffect(() => {
    setLoading(true); setProfile(null); setError("")
    void load()
    return () => { generation.current++ }
  }, [load])

  return (
    <AppShell>
      <div className="page" style={{ minWidth: 0 }}>
        {loading ? (
          <div style={{ height: 96, background: "var(--surface-2)", borderRadius: 8 }} />
        ) : profile ? (
          <ProfileDetail key={profile.id} profile={profile} envs={envs} workspaceId={workspaceId}
            isAdmin={role === "admin"} onReload={() => void load()} initialTab={initialTab} />
        ) : (
          <div className="card card-pad" style={{ background: "var(--surface-2)" }}>
            <p role="alert" style={{ margin: "0 0 8px", fontSize: 13, color: "var(--err)", overflowWrap: "anywhere" }}>
              {error || "Profile not found."}
            </p>
            <Link href={LIST_HREF} style={{ fontSize: 12.5 }}>← Back to gateway profiles</Link>
          </div>
        )}
      </div>
    </AppShell>
  )
}
