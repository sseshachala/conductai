"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import AppShell from "@/components/AppShell"
import GatewayProfileV2Editor from "@/components/settings/GatewayProfileV2Editor"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { environments, guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { type EnvironmentRow, type PresetChip, PRESET_CHIPS } from "../_components/presets"

const LIST_HREF = "/proxy/gateway-profiles"

export default function NewGatewayProfilePage() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { role } = useGuardRole()
  const router = useRouter()
  const workspaceId = activeWorkspace?.id ?? ""
  const isAdmin = role === "admin"

  const [envs, setEnvs] = useState<EnvironmentRow[]>([])
  const [names, setNames] = useState<string[]>([])
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    if (!workspaceId) return
    let live = true
    void Promise.all([environments.list(authFetch), guard.gatewayProfilesV2.list(authFetch, workspaceId)])
      .then(([envRows, rows]) => { if (live) { setEnvs(envRows); setNames(rows.map(r => r.name)) } })
      .catch(err => { if (live) setError(err instanceof Error ? err.message : "Failed to load environments") })
    return () => { live = false }
  }, [authFetch, workspaceId])

  // Referentially stable stub: the editor resets its form when `profile` changes.
  const stub = useMemo<GatewayProfileV2Out>(() => ({
    id: "", workspace_id: workspaceId, name: "", model_alias: null, cond_code: "",
    active_revision_id: null, status: "draft", has_unpublished_changes: false,
    working_copy: { name: "", model_alias: "", timeout_seconds: 60, max_attempts: 1, targets: [] },
    revisions: [], created_at: "", updated_at: "",
  }), [workspaceId])

  async function createFromPreset(preset: PresetChip) {
    if (!workspaceId || !isAdmin) return
    setBusy(preset.label); setError("")
    try {
      // The API rejects duplicate names; uniqueify so a preset stays reusable.
      const taken = new Set(names.map(n => n.toLowerCase()))
      let candidate = preset.name
      for (let n = 2; taken.has(candidate.toLowerCase()); n++) candidate = `${preset.name}-${n}`
      const wc = { ...preset.workingCopy, name: candidate, model_alias: candidate }
      const created = await guard.gatewayProfilesV2.create(authFetch, workspaceId, { name: candidate, working_copy: wc })
      router.push(`${LIST_HREF}/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally { setBusy("") }
  }

  return (
    <AppShell>
      <div className="page" style={{ minWidth: 0 }}>
        <Link href={LIST_HREF} style={{ fontSize: 12.5, color: "var(--text-2)" }}>← Back to gateway profiles</Link>
        <div className="page-head">
          <h1 className="page-title">New profile</h1>
          <p className="page-sub">
            Start from a preset, or fill in the form. The profile is created as a draft;
            publish it from its detail page when it is ready.
          </p>
        </div>

        {error && (
          <div className="sbadge err" role="alert" style={{ display: "block", height: "auto", padding: "10px 14px", borderRadius: 8, marginBottom: 16, whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        {!isAdmin ? (
          <p style={{ fontSize: 13, color: "var(--text-3)" }}>Only workspace admins can create gateway profiles.</p>
        ) : (
          <>
            <div style={{ marginBottom: 20 }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Start from a preset</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {PRESET_CHIPS.map(c => (
                  <button key={c.label} className="chip" disabled={busy !== ""} title={c.hint}
                    onClick={() => void createFromPreset(c)} style={{ opacity: busy !== "" ? 0.6 : 1 }}>
                    {busy === c.label ? "Creating…" : c.label}
                  </button>
                ))}
              </div>
            </div>
            <GatewayProfileV2Editor mode="create" workspaceId={workspaceId} profile={stub} envs={envs}
              isAdmin onSaved={saved => { if (saved?.id) router.push(`${LIST_HREF}/${saved.id}`) }} />
          </>
        )}
      </div>
    </AppShell>
  )
}
