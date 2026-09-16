"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import AppShell from "@/components/AppShell"
import GatewayProfileV2Editor from "@/components/settings/GatewayProfileV2Editor"
import GatewayProfileV2PublishDialog from "@/components/settings/GatewayProfileV2PublishDialog"
import GatewayProfileV2RollbackDialog from "@/components/settings/GatewayProfileV2RollbackDialog"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { environments, guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"

// #2007 — Gateway Profiles v2 admin surface at /proxy/gateway-profiles.
// Coexists with the v1 /proxy page until the v2 runtime flag flips on.

type EnvironmentRow = { id: string; name: string }

function isPublished(profile: GatewayProfileV2Out): boolean {
  return profile.revisions.length > 0 || profile.bindings.length > 0
}

function hasUnpublishedChanges(profile: GatewayProfileV2Out): boolean {
  if (!profile.working_copy) return false
  if (!profile.bindings.length) return true
  const latestBinding = Math.max(...profile.bindings.map(b => new Date(b.updated_at).getTime()))
  return new Date(profile.updated_at).getTime() > latestBinding
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px",
  border: "1px solid var(--border)", borderRadius: 7,
  background: "var(--surface)", color: "var(--text)", fontSize: 13,
}

export default function GatewayProfilesV2Page() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { role } = useGuardRole()
  const workspaceId = activeWorkspace?.id ?? ""
  const isAdmin = role === "admin"

  const [profiles, setProfiles] = useState<GatewayProfileV2Out[]>([])
  const [envs, setEnvs] = useState<EnvironmentRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>("")
  const [creating, setCreating] = useState(false)
  const [showNewProfile, setShowNewProfile] = useState(false)
  const [newName, setNewName] = useState("")
  const [showPublish, setShowPublish] = useState(false)
  const [showRollback, setShowRollback] = useState(false)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true); setError("")
    try {
      const [rows, envRows] = await Promise.all([
        guard.gatewayProfilesV2.list(authFetch, workspaceId),
        environments.list(authFetch),
      ])
      setProfiles(rows)
      setEnvs(envRows)
      setSelectedId(prev => prev ?? rows[0]?.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profiles")
    } finally { setLoading(false) }
    // selectedId intentionally excluded — a reload should not fight the user's selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch, workspaceId])

  useEffect(() => { void load() }, [load])

  const selected = useMemo(
    () => profiles.find(p => p.id === selectedId) ?? null,
    [profiles, selectedId],
  )

  const envName = useCallback(
    (envId: string) => envs.find(e => e.id === envId)?.name ?? envId.slice(0, 8),
    [envs],
  )

  async function handleCreate() {
    if (!workspaceId || !newName.trim()) return
    setCreating(true); setError("")
    try {
      const res = await guard.gatewayProfilesV2.create(authFetch, workspaceId, { name: newName.trim() })
      const created = await res.json()
      setNewName("")
      setShowNewProfile(false)
      await load()
      setSelectedId(created.id ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally { setCreating(false) }
  }

  return (
    <AppShell>
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">Gateway Profiles v2</h1>
          <p className="page-sub">
            One profile, one model alias, an ordered list of upstream targets.
            Publish binds a revision to an environment × alias; requests using
            that alias route through the pinned revision. Draft edits are safe —
            clients keep serving the last published revision until you publish again.
          </p>
          <p className="page-sub" style={{ marginTop: 4, fontSize: 12.5, color: "var(--text-3)" }}>
            Runtime execution requires the <code className="mono">guard_gateway_profile_v2</code> flag
            on your workspace. Phase 1 supports non-streaming Anthropic Messages / OpenAI Chat /
            OpenAI Responses; streaming falls through to v1.
          </p>
        </div>

        {error && (
          <div className="sbadge err" style={{ display: "block", height: "auto", padding: "10px 14px", borderRadius: 8, marginBottom: 16, whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20 }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span className="eyebrow">Profiles ({profiles.length})</span>
              {isAdmin && !showNewProfile && (
                <button className="btn btn-ghost btn-sm" onClick={() => setShowNewProfile(true)}>
                  + New
                </button>
              )}
            </div>

            {loading ? (
              <div style={{ height: 96, background: "var(--surface-2)", borderRadius: 8 }} />
            ) : profiles.length === 0 && !showNewProfile ? (
              <div className="card card-pad" style={{ textAlign: "center", background: "var(--surface-2)" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: "0 0 10px" }}>
                  No v2 profiles yet.
                </p>
                {isAdmin && (
                  <button className="btn btn-primary btn-sm" onClick={() => setShowNewProfile(true)}>
                    Create the first draft
                  </button>
                )}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {profiles.map(p => (
                  <ProfileListItem key={p.id} profile={p}
                    active={selectedId === p.id}
                    onSelect={() => setSelectedId(p.id)} />
                ))}
              </div>
            )}

            {isAdmin && showNewProfile && (
              <div className="card card-pad" style={{ marginTop: 12 }}>
                <label style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
                  New profile name
                </label>
                <input autoFocus value={newName} onChange={e => setNewName(e.target.value)}
                  placeholder="e.g. coding-alias-prod"
                  onKeyDown={e => {
                    if (e.key === "Enter") void handleCreate()
                    if (e.key === "Escape") { setShowNewProfile(false); setNewName("") }
                  }}
                  style={inputStyle} />
                <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                  <button onClick={() => void handleCreate()}
                    disabled={creating || !newName.trim()}
                    className="btn btn-primary btn-sm">
                    {creating ? "Creating…" : "Create"}
                  </button>
                  <button onClick={() => { setShowNewProfile(false); setNewName("") }}
                    className="btn btn-ghost btn-sm">Cancel</button>
                </div>
              </div>
            )}
          </div>

          <div>
            {selected ? (
              <ProfileDetail profile={selected} envs={envs} envName={envName}
                workspaceId={workspaceId} isAdmin={isAdmin}
                onReload={load}
                onOpenPublish={() => setShowPublish(true)}
                onOpenRollback={() => setShowRollback(true)} />
            ) : (
              <div className="card card-pad" style={{ background: "var(--surface-2)", textAlign: "center" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                  Select a profile to see its details.
                </p>
              </div>
            )}
          </div>
        </div>

        {selected && showPublish && (
          <GatewayProfileV2PublishDialog
            workspaceId={workspaceId} profile={selected} envs={envs}
            onClose={() => setShowPublish(false)}
            onPublished={() => void load()} />
        )}
        {selected && showRollback && (
          <GatewayProfileV2RollbackDialog
            workspaceId={workspaceId} profile={selected} envs={envs}
            onClose={() => setShowRollback(false)}
            onRolledBack={() => void load()} />
        )}
      </div>
    </AppShell>
  )
}


function ProfileListItem({
  profile, active, onSelect,
}: {
  profile: GatewayProfileV2Out
  active: boolean
  onSelect: () => void
}) {
  const published = isPublished(profile)
  const dirty = hasUnpublishedChanges(profile)
  return (
    <button onClick={onSelect} className="card"
      style={{
        display: "flex", flexDirection: "column", alignItems: "stretch",
        gap: 4, padding: "10px 12px", textAlign: "left", cursor: "pointer",
        background: active ? "var(--accent-weak)" : "var(--surface)",
        borderColor: active ? "var(--accent-ring)" : "var(--border)",
      }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 13.5, fontWeight: 600, color: active ? "var(--accent-text)" : "var(--text)" }}>
          {profile.name}
        </span>
        {published ? (
          <span className="sbadge ok">{profile.bindings.length} bound</span>
        ) : (
          <span className="sbadge warn">draft</span>
        )}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
        alias: <span className="mono">{profile.model_alias ?? "—"}</span>
        {" · "}rev {profile.revisions.length}
        {dirty && <> · <span style={{ color: "var(--warn)" }}>unpublished</span></>}
      </div>
    </button>
  )
}


function ProfileDetail({
  profile, envs, envName, workspaceId, isAdmin,
  onReload, onOpenPublish, onOpenRollback,
}: {
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  envName: (envId: string) => string
  workspaceId: string
  isAdmin: boolean
  onReload: () => void
  onOpenPublish: () => void
  onOpenRollback: () => void
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 650 }}>{profile.name}</h2>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
            alias <code className="mono">{profile.model_alias ?? "—"}</code>
            {" · "}created {new Date(profile.created_at).toLocaleDateString()}
          </div>
        </div>
        {isAdmin && (
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={onOpenPublish} className="btn btn-primary btn-sm"
              disabled={!profile.working_copy}>
              Publish…
            </button>
            <button onClick={onOpenRollback} className="btn btn-ghost btn-sm"
              disabled={profile.revisions.length === 0}>
              Rollback…
            </button>
          </div>
        )}
      </div>

      <Section title="Bindings">
        {profile.bindings.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>Not published yet.</p>
        ) : (
          <BindingsTable bindings={profile.bindings} revisions={profile.revisions} envName={envName} />
        )}
      </Section>

      <Section title="Working copy">
        <GatewayProfileV2Editor
          workspaceId={workspaceId}
          profile={profile}
          envs={envs}
          isAdmin={isAdmin}
          onSaved={onReload}
        />
      </Section>

      <Section title={`Revisions (${profile.revisions.length})`}>
        {profile.revisions.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>No revisions yet.</p>
        ) : (
          <RevisionsTable revisions={profile.revisions} />
        )}
      </Section>
    </div>
  )
}


function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}


function BindingsTable({
  bindings, revisions, envName,
}: {
  bindings: GatewayProfileV2Out["bindings"]
  revisions: GatewayProfileV2Out["revisions"]
  envName: (envId: string) => string
}) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--surface-2)", color: "var(--text-3)" }}>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Environment</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Alias</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Revision</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Updated</th>
          </tr>
        </thead>
        <tbody>
          {bindings.map(b => {
            const rev = revisions.find(r => r.id === b.revision_id)
            return (
              <tr key={`${b.environment_id}:${b.model_alias}`}
                style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 10px" }}>{envName(b.environment_id)}</td>
                <td style={{ padding: "6px 10px" }} className="mono">{b.model_alias}</td>
                <td style={{ padding: "6px 10px" }}>
                  {rev ? <span className="sbadge info">v{rev.version}</span> : (
                    <span className="mono" style={{ fontSize: 11 }}>{b.revision_id.slice(0, 8)}…</span>
                  )}
                </td>
                <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>
                  {new Date(b.updated_at).toLocaleString()}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}


function RevisionsTable({ revisions }: { revisions: GatewayProfileV2Out["revisions"] }) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "var(--surface-2)", color: "var(--text-3)" }}>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Version</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published by</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published at</th>
            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>ID</th>
          </tr>
        </thead>
        <tbody>
          {revisions.map(r => (
            <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "6px 10px" }}><span className="sbadge info">v{r.version}</span></td>
              <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{r.published_by}</td>
              <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{new Date(r.published_at).toLocaleString()}</td>
              <td style={{ padding: "6px 10px" }} className="mono">{r.id.slice(0, 8)}…</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
