"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"

/**
 * Unpublish confirmation. Routing stops immediately; revisions are kept
 * and the profile can be republished later.
 */
export default function GatewayProfileV2UnpublishDialog({
  workspaceId, profile, onClose, onUnpublished,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  onClose: () => void
  onUnpublished: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  async function unpublish() {
    setBusy(true); setErr("")
    try {
      await guard.gatewayProfilesV2.unpublish(authFetch, workspaceId, profile.id)
      onUnpublished()
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Unpublish failed")
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.35)" }} onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Unpublish profile" className="card card-pad"
        style={{ width: "100%", maxWidth: 480, margin: "0 16px" }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 650 }}>Unpublish {profile.name}</h3>
        <p style={{ margin: "4px 0 16px", color: "var(--text-3)", fontSize: 12.5 }}>
          Requests to <code className="mono">cond-{profile.cond_code}-{profile.model_alias ?? ""}</code> will
          start failing immediately. Revisions are kept and you can publish again at any time.
        </p>
        {err && <p role="alert" style={{ margin: "0 0 10px", color: "var(--err)", fontSize: 12, overflowWrap: "anywhere" }}>{err}</p>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} className="btn btn-ghost btn-sm" disabled={busy}>Cancel</button>
          <button onClick={() => void unpublish()} disabled={busy} className="btn btn-primary btn-sm">
            {busy ? "Unpublishing…" : "Unpublish"}
          </button>
        </div>
      </div>
    </div>
  )
}
