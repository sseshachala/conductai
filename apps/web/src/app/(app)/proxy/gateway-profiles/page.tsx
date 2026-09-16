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

// #2007 — Gateway Profiles v2 admin surface.
//
// Form-first: chips create a draft with a fully-shaped working copy so
// the admin only has to point each target at a Vault + credential and
// click Save. Lens-driven creation via natural language landed in the
// backend actor tools (#2012), but the LLM's reliability at emitting
// correct model IDs and matching vault UUIDs isn't good enough to be
// the primary path yet — form stays the trunk, Lens comes back as an
// optional assistant once the model-ID + capability-catalog handshake
// is tighter.

type EnvironmentRow = { id: string; name: string }

interface PresetChip {
  label: string
  hint: string
  name: string
  workingCopy: Record<string, unknown>
}

// Model IDs pulled from the runtime pins we know work today:
// Anthropic 4.x family, OpenAI GA models. Adjust in one place when
// the pinned catalog moves.
const PRESET_CHIPS: PresetChip[] = [
  {
    label: "Coding · Claude Sonnet + GPT-4o fallback",
    hint: "Primary → anthropic/claude-sonnet-4-6; fallback → openai/gpt-4o.",
    name: "coding",
    workingCopy: {
      name: "coding",
      model_alias: "coding",
      accepts: ["anthropic_messages"],
      timeout_seconds: 60,
      max_attempts: 2,
      targets: [
        {
          id: "primary", transport: "litellm_sdk",
          provider: "anthropic", model: "claude-sonnet-4-6",
          credential_ref: "",
        },
        {
          id: "fallback", transport: "litellm_sdk",
          provider: "openai", model: "gpt-4o",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "Anthropic only · Claude Sonnet",
    hint: "Single Anthropic target, no fallback.",
    name: "anthropic-only",
    workingCopy: {
      name: "anthropic-only",
      model_alias: "anthropic-only",
      accepts: ["anthropic_messages"],
      timeout_seconds: 60,
      max_attempts: 1,
      targets: [
        {
          id: "primary", transport: "litellm_sdk",
          provider: "anthropic", model: "claude-sonnet-4-6",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "Cheap · Haiku + gpt-4o-mini fallback",
    hint: "Primary → anthropic/claude-haiku; fallback → openai/gpt-4o-mini.",
    name: "cheap",
    workingCopy: {
      name: "cheap",
      model_alias: "cheap",
      accepts: ["anthropic_messages"],
      timeout_seconds: 45,
      max_attempts: 2,
      targets: [
        {
          id: "primary", transport: "litellm_sdk",
          provider: "anthropic", model: "claude-haiku-4-5-20251001",
          credential_ref: "",
        },
        {
          id: "fallback", transport: "litellm_sdk",
          provider: "openai", model: "gpt-4o-mini",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "OpenAI · gpt-4o Chat + Responses",
    hint: "Single OpenAI target for both chat completions and responses.",
    name: "openai-4o",
    workingCopy: {
      name: "openai-4o",
      model_alias: "openai-4o",
      accepts: ["openai_chat_completions", "openai_responses"],
      timeout_seconds: 60,
      max_attempts: 1,
      targets: [
        {
          id: "primary", transport: "litellm_sdk",
          provider: "openai", model: "gpt-4o",
          credential_ref: "",
        },
      ],
    },
  },
]

function isPublished(profile: GatewayProfileV2Out): boolean {
  return profile.revisions.length > 0 || profile.bindings.length > 0
}

function hasUnpublishedChanges(profile: GatewayProfileV2Out): boolean {
  if (!profile.working_copy) return false
  if (!profile.bindings.length) return true
  const latestBinding = Math.max(...profile.bindings.map(b => new Date(b.updated_at).getTime()))
  return new Date(profile.updated_at).getTime() > latestBinding
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
  const [busy, setBusy] = useState<string>("")
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

  async function createFromPreset(preset: PresetChip) {
    if (!workspaceId || !isAdmin) return
    setBusy(preset.label); setError("")
    try {
      // Uniqueify the name if a profile with this preset name already
      // exists — API rejects duplicates, and we don't want to burn the
      // chip's usefulness on the second click.
      const taken = new Set(profiles.map(p => p.name.toLowerCase()))
      let candidate = preset.name
      let n = 2
      while (taken.has(candidate.toLowerCase())) {
        candidate = `${preset.name}-${n}`
        n += 1
      }
      const wc = { ...preset.workingCopy, name: candidate, model_alias: candidate }
      const res = await guard.gatewayProfilesV2.create(
        authFetch, workspaceId, { name: candidate, working_copy: wc },
      )
      const created = await res.json()
      await load()
      if (created?.id) setSelectedId(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally { setBusy("") }
  }

  async function createBlank() {
    if (!workspaceId || !isAdmin) return
    setBusy("blank"); setError("")
    try {
      const taken = new Set(profiles.map(p => p.name.toLowerCase()))
      let candidate = "draft"
      let n = 2
      while (taken.has(candidate.toLowerCase())) {
        candidate = `draft-${n}`; n += 1
      }
      const res = await guard.gatewayProfilesV2.create(
        authFetch, workspaceId, { name: candidate },
      )
      const created = await res.json()
      await load()
      if (created?.id) setSelectedId(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally { setBusy("") }
  }

  return (
    <AppShell>
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">Gateway Profiles v2</h1>
          <p className="page-sub">
            Route a friendly alias (e.g. <code>coding</code>) through one or more upstream
            targets. Click a preset below to pre-fill a draft, then pick a Vault for
            each target's credential and Save. Publish binds the revision to an
            environment × alias so requests using that alias route through the pinned targets.
          </p>
        </div>

        {error && (
          <div className="sbadge err" style={{ display: "block", height: "auto", padding: "10px 14px", borderRadius: 8, marginBottom: 16, whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        {isAdmin && (
          <div style={{ marginBottom: 20 }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Start from a preset</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {PRESET_CHIPS.map(c => (
                <button key={c.label} className="chip"
                  disabled={busy !== ""}
                  title={c.hint}
                  onClick={() => void createFromPreset(c)}
                  style={{ opacity: busy !== "" ? 0.6 : 1 }}>
                  {busy === c.label ? "Creating…" : c.label}
                </button>
              ))}
              <button className="chip" disabled={busy !== ""}
                onClick={() => void createBlank()}
                title="Empty draft you fill in from scratch.">
                {busy === "blank" ? "Creating…" : "+ Blank draft"}
              </button>
            </div>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Profiles ({profiles.length})</div>
            {loading ? (
              <div style={{ height: 96, background: "var(--surface-2)", borderRadius: 8 }} />
            ) : profiles.length === 0 ? (
              <div className="card card-pad" style={{ textAlign: "center", background: "var(--surface-2)" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                  No profiles yet. Click a preset above.
                </p>
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
          </div>

          <div>
            {selected ? (
              <ProfileDetail
                profile={selected}
                envs={envs}
                envName={envName}
                workspaceId={workspaceId}
                isAdmin={isAdmin}
                onReload={load}
                onOpenPublish={() => setShowPublish(true)}
                onOpenRollback={() => setShowRollback(true)}
              />
            ) : (
              <div className="card card-pad" style={{ background: "var(--surface-2)", textAlign: "center" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                  Select a profile — or click a preset above to make one.
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
          <span className="sbadge ok">{profile.bindings.length} live</span>
        ) : (
          <span className="sbadge warn">draft</span>
        )}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
        alias: <span className="mono">{profile.model_alias ?? "—"}</span>
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
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 650 }}>{profile.name}</h2>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
            alias <code className="mono">{profile.model_alias ?? "—"}</code>
            {" · "}created {new Date(profile.created_at).toLocaleDateString()}
          </div>
        </div>
        {isAdmin && (
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={onOpenPublish} className="btn btn-primary btn-sm"
              disabled={!profile.working_copy}>Publish…</button>
            <button onClick={onOpenRollback} className="btn btn-ghost btn-sm"
              disabled={profile.revisions.length === 0}>Rollback…</button>
          </div>
        )}
      </div>

      {profile.bindings.length > 0 && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Live in</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {profile.bindings.map(b => (
              <span key={`${b.environment_id}:${b.model_alias}`}
                className="sbadge ok"
                title={`revision ${b.revision_id.slice(0, 8)}… since ${new Date(b.updated_at).toLocaleString()}`}>
                {envName(b.environment_id)}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Working copy</div>
        <GatewayProfileV2Editor
          workspaceId={workspaceId}
          profile={profile}
          envs={envs}
          isAdmin={isAdmin}
          onSaved={onReload}
        />
      </div>

      {profile.revisions.length > 0 && (
        <details>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-2)" }}>
            History ({profile.revisions.length})
          </summary>
          <div className="card" style={{ padding: 0, overflow: "hidden", marginTop: 8 }}>
            <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "var(--surface-2)", color: "var(--text-3)" }}>
                  <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Version</th>
                  <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published by</th>
                  <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published at</th>
                </tr>
              </thead>
              <tbody>
                {profile.revisions.map(r => (
                  <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "6px 10px" }}><span className="sbadge info">v{r.version}</span></td>
                    <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{r.published_by}</td>
                    <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>
                      {new Date(r.published_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}
