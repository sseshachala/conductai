"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"

// Publish dialog for #2007. Pick an environment, see the prior binding
// (if any) that would be replaced, confirm. Matches NewProjectModal's
// overlay pattern but the inner content uses the sibling settings pages'
// CSS-var + .btn conventions so it feels like the same product.

type EnvironmentRow = { id: string; name: string }

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px",
  border: "1px solid var(--border)", borderRadius: 7,
  background: "var(--surface)", color: "var(--text)", fontSize: 13,
}

export default function GatewayProfileV2PublishDialog({
  workspaceId, profile, envs, onClose, onPublished,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  onClose: () => void
  onPublished: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [envId, setEnvId] = useState<string>(envs[0]?.id ?? "")
  const [publishing, setPublishing] = useState(false)
  const [err, setErr] = useState("")

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  const modelAlias = (profile.working_copy as { model_alias?: string } | null)?.model_alias
    ?? profile.model_alias ?? ""
  const existingBinding = profile.bindings.find(b =>
    b.environment_id === envId
    && (!modelAlias || b.model_alias === modelAlias))
  const priorRevision = existingBinding
    ? profile.revisions.find(r => r.id === existingBinding.revision_id)
    : null

  async function publish() {
    if (!envId) { setErr("Pick an environment"); return }
    setPublishing(true); setErr("")
    try {
      await guard.gatewayProfilesV2.publish(authFetch, workspaceId, profile.id, envId)
      onPublished()
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Publish failed")
    } finally { setPublishing(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.35)" }} onClick={onClose}>
      <div className="card card-pad" style={{ width: "100%", maxWidth: 480, margin: "0 16px" }}
        onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 650 }}>Publish revision</h3>
        <p style={{ margin: "4px 0 16px", color: "var(--text-3)", fontSize: 12.5 }}>
          Pins the current working copy to an environment × alias binding.
          Draft edits after publish don't affect the served revision.
        </p>

        <label style={{ fontSize: 12, display: "block" }}>Environment
          <select value={envId} onChange={e => setEnvId(e.target.value)} style={inputStyle}>
            <option value="">— pick —</option>
            {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </label>

        {envId && (
          <div style={{ marginTop: 12, padding: "10px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
              Alias
            </div>
            <div className="mono" style={{ fontSize: 13, marginBottom: 8 }}>
              {modelAlias || "(no alias set — save working copy first)"}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
              Prior binding
            </div>
            {priorRevision ? (
              <div style={{ fontSize: 12 }}>
                <span className="sbadge info" style={{ marginRight: 6 }}>v{priorRevision.version}</span>
                published by {priorRevision.published_by} on{" "}
                {new Date(priorRevision.published_at).toLocaleDateString()}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>None — this is the first publish.</div>
            )}
          </div>
        )}

        {err && <p style={{ margin: "10px 0 0", color: "var(--err)", fontSize: 12 }}>{err}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button onClick={onClose} className="btn btn-ghost btn-sm">Cancel</button>
          <button onClick={publish} disabled={publishing || !envId || !modelAlias}
            className="btn btn-primary btn-sm">
            {publishing ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>
    </div>
  )
}
