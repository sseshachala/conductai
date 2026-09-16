"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"

// v3 (#2007 follow-up): publish is a single click — no environment
// picker. The credential vault lives inside each target's
// credential_ref inside the working copy, so publish just marks the
// working copy as the active revision.

export default function GatewayProfileV2PublishDialog({
  workspaceId, profile, onClose, onPublished,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  onClose: () => void
  onPublished: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [publishing, setPublishing] = useState(false)
  const [err, setErr] = useState("")

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  const wc = (profile.working_copy as { model_alias?: string; targets?: Array<Record<string, unknown>> } | null) ?? null
  const modelAlias = wc?.model_alias ?? profile.model_alias ?? ""
  const targetCount = wc?.targets?.length ?? 0

  async function publish() {
    setPublishing(true); setErr("")
    try {
      await guard.gatewayProfilesV2.publish(authFetch, workspaceId, profile.id)
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
          Freezes the working copy as the profile's active revision. Once published,
          the working copy is locked — duplicate the profile to make further changes.
        </p>

        <div style={{ padding: "10px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)" }}>
          <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
            Profile identifier
          </div>
          <div className="mono" style={{ fontSize: 13, marginBottom: 8 }}>
            cond-{profile.cond_code}-{modelAlias || "(no alias)"}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
            Targets in this revision
          </div>
          <div style={{ fontSize: 12.5 }}>
            {targetCount} target{targetCount === 1 ? "" : "s"} (order = priority)
          </div>
        </div>

        {err && <p style={{ margin: "10px 0 0", color: "var(--err)", fontSize: 12 }}>{err}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button onClick={onClose} className="btn btn-ghost btn-sm">Cancel</button>
          <button onClick={publish} disabled={publishing || !modelAlias || targetCount === 0}
            className="btn btn-primary btn-sm">
            {publishing ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>
    </div>
  )
}
