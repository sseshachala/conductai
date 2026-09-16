"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out, GatewayProfileV2Revision } from "@/lib/api/guard"

// v3 (#2007 follow-up): no environment picker — rollback repoints the
// single active_revision_id on the profile row.

export default function GatewayProfileV2RollbackDialog({
  workspaceId, profile, onClose, onRolledBack,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  onClose: () => void
  onRolledBack: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [revisionId, setRevisionId] = useState<string>("")
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null)
  const [loadingSnap, setLoadingSnap] = useState(false)
  const [rolling, setRolling] = useState(false)
  const [err, setErr] = useState("")

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose])

  async function selectRevision(id: string) {
    setRevisionId(id)
    setSnapshot(null)
    setLoadingSnap(true)
    try {
      const snap = await guard.gatewayProfilesV2.revisionSnapshot(
        authFetch, workspaceId, profile.id, id,
      )
      setSnapshot(snap)
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load snapshot")
    } finally { setLoadingSnap(false) }
  }

  async function rollback() {
    if (!revisionId) { setErr("Pick a revision"); return }
    setRolling(true); setErr("")
    try {
      await guard.gatewayProfilesV2.rollback(authFetch, workspaceId, profile.id, revisionId)
      onRolledBack()
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Rollback failed")
    } finally { setRolling(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.35)" }} onClick={onClose}>
      <div className="card card-pad" style={{ width: "100%", maxWidth: 720, margin: "0 16px", maxHeight: "80vh", overflow: "auto" }}
        onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 650 }}>Roll back to previous revision</h3>
        <p style={{ margin: "4px 0 16px", color: "var(--text-3)", fontSize: 12.5 }}>
          Sets the profile's active revision to the one you pick — clients using this
          profile's cond code will resume the older shape on their next request.
          The working copy stays locked (still published).
        </p>

        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 12, marginBottom: 6, color: "var(--text-2)" }}>Revisions</div>
          {profile.revisions.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-3)" }}>
              No revisions yet — nothing to roll back to.
            </div>
          ) : (
            <RevisionsTable
              revisions={profile.revisions}
              currentRevisionId={profile.active_revision_id}
              selectedId={revisionId}
              onSelect={selectRevision}
            />
          )}
        </div>

        {revisionId && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, marginBottom: 6, color: "var(--text-2)" }}>Snapshot preview</div>
            <div className="card" style={{ padding: 12, background: "var(--surface-2)", maxHeight: 260, overflow: "auto" }}>
              {loadingSnap ? (
                <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>Loading…</div>
              ) : snapshot ? (
                <pre className="mono" style={{ margin: 0, fontSize: 11.5, color: "var(--text)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                  {JSON.stringify(snapshot, null, 2)}
                </pre>
              ) : (
                <div style={{ fontSize: 12.5, color: "var(--err)" }}>Snapshot failed to load</div>
              )}
            </div>
          </div>
        )}

        {err && <p style={{ margin: "10px 0 0", color: "var(--err)", fontSize: 12 }}>{err}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button onClick={onClose} className="btn btn-ghost btn-sm">Cancel</button>
          <button onClick={rollback}
            disabled={rolling || !revisionId || revisionId === profile.active_revision_id}
            className="btn btn-primary btn-sm">
            {rolling ? "Rolling back…" : "Roll back"}
          </button>
        </div>
      </div>
    </div>
  )
}


function RevisionsTable({
  revisions, currentRevisionId, selectedId, onSelect,
}: {
  revisions: GatewayProfileV2Revision[]
  currentRevisionId: string | null
  selectedId: string
  onSelect: (id: string) => void
}) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--surface-2)", color: "var(--text-3)" }}>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Version</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published by</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published at</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}></th>
          </tr>
        </thead>
        <tbody>
          {revisions.map(r => {
            const current = r.id === currentRevisionId
            const selected = r.id === selectedId
            return (
              <tr key={r.id}
                onClick={() => onSelect(r.id)}
                style={{
                  borderTop: "1px solid var(--border)",
                  background: selected ? "var(--accent-weak)" : "transparent",
                  cursor: "pointer",
                }}>
                <td style={{ padding: "6px 10px" }}>v{r.version}</td>
                <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{r.published_by}</td>
                <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>
                  {new Date(r.published_at).toLocaleString()}
                </td>
                <td style={{ padding: "6px 10px" }}>
                  {current && <span className="sbadge ok">current</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
