"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"

/**
 * Draft-delete confirmation with type-to-confirm.
 *
 * Standard used elsewhere in the app (see workflows/[id]/settings) —
 * ``window.confirm()`` was inconsistent with the rest of the product
 * and looked "hacked in" per the design bar. Type-to-confirm forces
 * a deliberate action (no oops-clicks) and matches the same visual
 * shape as the Publish + Rollback dialogs on this page.
 *
 * Only offered for drafts. Published profiles route through
 * ``duplicate`` instead (the API rejects deletion of anything with
 * revision history so admin can't lose audit lineage).
 */
export default function GatewayProfileV2DeleteDialog({
  workspaceId, profile, onClose, onDeleted,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  onClose: () => void
  onDeleted: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [deleting, setDeleting] = useState(false)
  const [err, setErr] = useState("")
  const [confirmValue, setConfirmValue] = useState("")

  const matches = confirmValue === profile.name

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  async function del() {
    if (!matches) return
    setDeleting(true); setErr("")
    try {
      await guard.gatewayProfilesV2.remove(authFetch, workspaceId, profile.id)
      onDeleted()
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed")
    } finally { setDeleting(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.35)" }} onClick={onClose}>
      <div className="card card-pad" style={{ width: "100%", maxWidth: 480, margin: "0 16px" }}
        onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 650 }}>Delete draft</h3>
        <p style={{ margin: "4px 0 16px", color: "var(--text-3)", fontSize: 12.5 }}>
          Removes this draft profile. This can't be undone — the draft +
          any unsaved working-copy edits are gone. Published revisions
          (if any) stay intact.
        </p>

        <div style={{ padding: "10px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)" }}>
          <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
            Profile name
          </div>
          <code className="mono" style={{ fontSize: 13, wordBreak: "break-all" }}>
            {profile.name}
          </code>
        </div>

        <div style={{ margin: "14px 0 6px" }}>
          <label style={{ fontSize: 12, color: "var(--text-2)" }}>
            Type <strong>{profile.name}</strong> to confirm
          </label>
        </div>
        <input
          value={confirmValue}
          onChange={e => setConfirmValue(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && matches) void del()
          }}
          placeholder={profile.name}
          autoFocus
          style={{
            width: "100%",
            border: `1px solid ${matches ? "var(--err-bd)" : "var(--border)"}`,
            borderRadius: 8,
            padding: "9px 11px",
            fontSize: 13,
            background: "var(--surface)",
            color: "var(--text)",
            outline: "none",
          }}
        />

        {err && (
          <p style={{ marginTop: 10, color: "var(--err)", fontSize: 12 }}>{err}</p>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose} disabled={deleting}>
            Cancel
          </button>
          <button
            onClick={() => void del()}
            disabled={!matches || deleting}
            style={{
              fontSize: 12.5,
              fontWeight: 500,
              color: "#fff",
              background: "var(--err)",
              border: "none",
              borderRadius: 8,
              padding: "8px 16px",
              cursor: !matches || deleting ? "not-allowed" : "pointer",
              opacity: !matches || deleting ? 0.4 : 1,
              transition: "opacity 0.15s",
            }}
          >
            {deleting ? "Deleting…" : "Delete draft"}
          </button>
        </div>
      </div>
    </div>
  )
}
