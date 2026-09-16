"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { guard, environments } from "@/lib/api"
import type {
  GatewayProfileV2Binding,
  GatewayProfileV2Out,
} from "@/lib/api/guard"

// #2007 Phase 1 — v2 admin surface, read + list only. Draft editor and
// publish/rollback dialogs land in follow-up commits. Rendered at
// /proxy/gateway-profiles so it lives adjacent to the v1 /proxy page
// without clobbering it; both stay in the sidebar until the v2 flag
// flips on for the workspace.

type EnvironmentRow = { id: string; name: string }

function _isPublished(profile: GatewayProfileV2Out): boolean {
  return profile.revisions.length > 0 || profile.bindings.length > 0
}

function _hasDraftDiff(profile: GatewayProfileV2Out): boolean {
  // A profile has "unpublished changes" if the working_copy is a superset
  // of nothing OR the working_copy differs from the latest published
  // revision. We can't do a snapshot diff on the list view (that would
  // fetch every revision), so key off the two indicators the API returns:
  // there IS a working_copy but no bindings yet, OR bindings exist but
  // updated_at on the profile is newer than the latest binding.
  if (!profile.working_copy) return false
  if (!profile.bindings.length) return true
  const latestBindingTs = Math.max(
    ...profile.bindings.map(b => new Date(b.updated_at).getTime()),
  )
  return new Date(profile.updated_at).getTime() > latestBindingTs
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
  const [newName, setNewName] = useState("")

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    setError("")
    try {
      const [rows, envRows] = await Promise.all([
        guard.gatewayProfilesV2.list(authFetch, workspaceId),
        environments.list(authFetch),
      ])
      setProfiles(rows)
      setEnvs(envRows)
      if (rows.length && !selectedId) {
        setSelectedId(rows[0].id)
      }
    } catch (err) {
      setError((err as Error).message || "Failed to load profiles")
    } finally {
      setLoading(false)
    }
    // selectedId intentionally excluded so a manual re-load doesn't fight
    // the user's current selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch, workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  const selected = useMemo(
    () => profiles.find(p => p.id === selectedId) ?? null,
    [profiles, selectedId],
  )

  const envName = useCallback(
    (envId: string) => envs.find(e => e.id === envId)?.name ?? envId.slice(0, 8),
    [envs],
  )

  const handleCreate = useCallback(async () => {
    if (!workspaceId || !newName.trim()) return
    try {
      setCreating(true)
      await guard.gatewayProfilesV2.create(authFetch, workspaceId, {
        name: newName.trim(),
      })
      setNewName("")
      await load()
    } catch (err) {
      setError((err as Error).message || "Failed to create profile")
    } finally {
      setCreating(false)
    }
  }, [authFetch, workspaceId, newName, load])

  return (
    <AppShell>
      <div style={{ maxWidth: 1200, padding: "20px 24px" }}>
        <h2 style={{ fontSize: 18, fontWeight: 650, margin: "8px 0 4px" }}>
          Gateway Profiles v2
        </h2>
        <p style={{ fontSize: 13, color: "var(--text-3)", margin: "0 0 20px", lineHeight: 1.5 }}>
          One profile, one model alias, an ordered list of upstream targets. Publish binds
          a revision to an environment × alias; requests using that alias route through the
          published revision. Draft edits are safe — clients continue serving the previously
          published revision until you publish again.
          <br />
          <span style={{ color: "var(--text-4)", fontSize: 12 }}>
            Runtime execution requires the <code>guard_gateway_profile_v2</code> flag to be enabled
            on your workspace. Non-streaming Anthropic Messages / OpenAI Chat / OpenAI Responses
            supported in Phase 1; streaming falls through to v1.
          </span>
        </p>

        {error ? (
          <div
            style={{
              padding: "10px 12px",
              marginBottom: 16,
              border: "1px solid var(--danger-4)",
              background: "var(--danger-2)",
              color: "var(--danger-11)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            {error}
          </div>
        ) : null}

        <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20 }}>
          {/* LIST COLUMN */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.4 }}>
                Profiles ({profiles.length})
              </div>
            </div>

            {loading ? (
              <div style={{ fontSize: 13, color: "var(--text-4)" }}>Loading…</div>
            ) : profiles.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-4)", padding: "10px 0" }}>
                No v2 profiles yet.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {profiles.map(p => {
                  const active = selectedId === p.id
                  const published = _isPublished(p)
                  const draftDiff = _hasDraftDiff(p)
                  return (
                    <button
                      key={p.id}
                      onClick={() => setSelectedId(p.id)}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-start",
                        padding: "10px 12px",
                        border: `1px solid ${active ? "var(--accent-6)" : "var(--surface-4)"}`,
                        background: active ? "var(--accent-2)" : "var(--surface-1)",
                        borderRadius: 6,
                        textAlign: "left",
                        cursor: "pointer",
                        gap: 4,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                        {published ? (
                          <span style={{
                            fontSize: 10,
                            padding: "1px 6px",
                            borderRadius: 10,
                            background: "var(--success-3)",
                            color: "var(--success-11)",
                          }}>
                            {p.bindings.length} bound
                          </span>
                        ) : (
                          <span style={{
                            fontSize: 10,
                            padding: "1px 6px",
                            borderRadius: 10,
                            background: "var(--warning-3)",
                            color: "var(--warning-11)",
                          }}>
                            draft
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-4)" }}>
                        alias: {p.model_alias ?? "—"} · rev {p.revisions.length}
                        {draftDiff ? " · unpublished changes" : ""}
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {isAdmin ? (
              <div style={{ marginTop: 16, borderTop: "1px solid var(--surface-4)", paddingTop: 12 }}>
                <label style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.4 }}>
                  New draft
                </label>
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <input
                    type="text"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder="profile name"
                    style={{
                      flex: 1,
                      padding: "6px 8px",
                      border: "1px solid var(--surface-4)",
                      borderRadius: 4,
                      fontSize: 13,
                      background: "var(--surface-1)",
                    }}
                    disabled={creating}
                  />
                  <button
                    onClick={() => void handleCreate()}
                    disabled={creating || !newName.trim()}
                    style={{
                      padding: "6px 12px",
                      background: "var(--accent-9)",
                      color: "var(--accent-contrast)",
                      border: "none",
                      borderRadius: 4,
                      fontSize: 13,
                      cursor: newName.trim() ? "pointer" : "not-allowed",
                      opacity: newName.trim() ? 1 : 0.5,
                    }}
                  >
                    Create
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          {/* DETAIL COLUMN */}
          <div>
            {selected ? (
              <ProfileDetail profile={selected} envName={envName} />
            ) : (
              <div style={{ fontSize: 13, color: "var(--text-4)", padding: "40px 0", textAlign: "center" }}>
                Select a profile to see its details.
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}


function ProfileDetail({
  profile,
  envName,
}: {
  profile: GatewayProfileV2Out
  envName: (envId: string) => string
}) {
  const wc = profile.working_copy as {
    accepts?: string[]
    timeout_seconds?: number
    max_attempts?: number
    targets?: Array<Record<string, unknown>>
  } | null

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <div style={{ fontSize: 16, fontWeight: 650, marginBottom: 2 }}>{profile.name}</div>
        <div style={{ fontSize: 12, color: "var(--text-4)" }}>
          alias <code>{profile.model_alias ?? "—"}</code> · created {new Date(profile.created_at).toLocaleDateString()}
        </div>
      </div>

      <Section title="Bindings">
        {profile.bindings.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-4)" }}>Not published yet.</div>
        ) : (
          <BindingsTable bindings={profile.bindings} envName={envName} />
        )}
      </Section>

      <Section title="Working copy">
        {wc ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", fontSize: 13 }}>
              <span style={{ color: "var(--text-3)" }}>accepts</span>
              <span>{(wc.accepts ?? []).join(", ") || "—"}</span>
              <span style={{ color: "var(--text-3)" }}>timeout_seconds</span>
              <span>{wc.timeout_seconds ?? "—"}</span>
              <span style={{ color: "var(--text-3)" }}>max_attempts</span>
              <span>{wc.max_attempts ?? "—"}</span>
              <span style={{ color: "var(--text-3)" }}>targets</span>
              <span>{(wc.targets ?? []).length}</span>
            </div>
            {(wc.targets ?? []).length > 0 ? (
              <TargetsTable targets={wc.targets ?? []} />
            ) : null}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "var(--text-4)" }}>No working copy set.</div>
        )}
      </Section>

      <Section title={`Revisions (${profile.revisions.length})`}>
        {profile.revisions.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-4)" }}>No revisions yet.</div>
        ) : (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--surface-4)", color: "var(--text-3)" }}>
                <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>version</th>
                <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>published_by</th>
                <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>published_at</th>
                <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>id</th>
              </tr>
            </thead>
            <tbody>
              {profile.revisions.map(r => (
                <tr key={r.id} style={{ borderBottom: "1px solid var(--surface-3)" }}>
                  <td style={{ padding: "6px 8px" }}>v{r.version}</td>
                  <td style={{ padding: "6px 8px" }}>{r.published_by}</td>
                  <td style={{ padding: "6px 8px" }}>{new Date(r.published_at).toLocaleString()}</td>
                  <td style={{ padding: "6px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--text-4)" }}>
                    {r.id.slice(0, 8)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  )
}


function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 8 }}>
        {title}
      </div>
      {children}
    </div>
  )
}


function BindingsTable({
  bindings,
  envName,
}: {
  bindings: GatewayProfileV2Binding[]
  envName: (envId: string) => string
}) {
  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ borderBottom: "1px solid var(--surface-4)", color: "var(--text-3)" }}>
          <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>environment</th>
          <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>alias</th>
          <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>revision</th>
          <th style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>updated_at</th>
        </tr>
      </thead>
      <tbody>
        {bindings.map(b => (
          <tr key={`${b.environment_id}:${b.model_alias}`} style={{ borderBottom: "1px solid var(--surface-3)" }}>
            <td style={{ padding: "6px 8px" }}>{envName(b.environment_id)}</td>
            <td style={{ padding: "6px 8px" }}>{b.model_alias}</td>
            <td style={{ padding: "6px 8px", fontFamily: "monospace", fontSize: 11 }}>{b.revision_id.slice(0, 8)}…</td>
            <td style={{ padding: "6px 8px" }}>{new Date(b.updated_at).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}


function TargetsTable({ targets }: { targets: Array<Record<string, unknown>> }) {
  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", border: "1px solid var(--surface-4)", borderRadius: 4 }}>
      <thead>
        <tr style={{ borderBottom: "1px solid var(--surface-4)", background: "var(--surface-2)", color: "var(--text-3)" }}>
          <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>#</th>
          <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>id</th>
          <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>transport</th>
          <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>provider / integration</th>
          <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 500 }}>model</th>
        </tr>
      </thead>
      <tbody>
        {targets.map((t, i) => (
          <tr key={String(t.id ?? i)} style={{ borderBottom: "1px solid var(--surface-3)" }}>
            <td style={{ padding: "6px 8px", color: "var(--text-4)" }}>{i + 1}</td>
            <td style={{ padding: "6px 8px" }}>{String(t.id ?? "")}</td>
            <td style={{ padding: "6px 8px" }}>{String(t.transport ?? "")}</td>
            <td style={{ padding: "6px 8px" }}>{String(t.provider ?? t.integration ?? "")}</td>
            <td style={{ padding: "6px 8px" }}>{String(t.model ?? "")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
