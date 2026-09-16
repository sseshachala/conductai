"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out, GatewayProfileV2Revision } from "@/lib/api/guard"

// Rollback picker for #2007. Lists this profile's revisions, lets the
// admin repoint a binding at a historical revision. Snapshot preview is
// lazy-loaded when a revision row is selected so the list load stays
// cheap on profiles with many revisions.

type EnvironmentRow = { id: string; name: string }

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px",
  border: "1px solid var(--border)", borderRadius: 7,
  background: "var(--surface)", color: "var(--text)", fontSize: 13,
}

export default function GatewayProfileV2RollbackDialog({
  workspaceId, profile, envs, onClose, onRolledBack,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  onClose: () => void
  onRolledBack: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [envId, setEnvId] = useState<string>(profile.bindings[0]?.environment_id ?? envs[0]?.id ?? "")
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
    if (!envId || !revisionId) { setErr("Pick environment and revision"); return }
    setRolling(true); setErr("")
    try {
      await guard.gatewayProfilesV2.rollback(authFetch, workspaceId, profile.id, {
        environment_id: envId, revision_id: revisionId,
      })
      onRolledBack()
      onClose()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Rollback failed")
    } finally { setRolling(false) }
  }

  const currentBinding = profile.bindings.find(b => b.environment_id === envId)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.35)" }} onClick={onClose}>
      <div className="card card-pad" style={{ width: "100%", maxWidth: 720, margin: "0 16px", maxHeight: "80vh", overflow: "auto" }}
        onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 650 }}>Rollback to previous revision</h3>
        <p style={{ margin: "4px 0 16px", color: "var(--text-3)", fontSize: 12.5 }}>
          Repoints an environment × alias binding at a historical revision.
          The current working copy is untouched.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <label style={{ fontSize: 12 }}>Environment
            <select value={envId} onChange={e => setEnvId(e.target.value)} style={inputStyle}>
              {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </label>
          <div>
            <div style={{ fontSize: 12, marginBottom: 4 }}>Currently bound to</div>
            {currentBinding ? (
              <span className="sbadge info">
                v{profile.revisions.find(r => r.id === currentBinding.revision_id)?.version ?? "?"}
              </span>
            ) : (
              <span style={{ fontSize: 12, color: "var(--text-3)" }}>No binding yet</span>
            )}
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, marginBottom: 6, color: "var(--text-2)" }}>Revisions</div>
          {profile.revisions.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-3)" }}>No revisions yet — nothing to roll back to.</div>
          ) : (
            <RevisionsTable
              revisions={profile.revisions}
              currentRevisionId={currentBinding?.revision_id}
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
          <button onClick={rollback} disabled={rolling || !envId || !revisionId}
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
  currentRevisionId?: string
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
                <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{new Date(r.published_at).toLocaleString()}</td>
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
