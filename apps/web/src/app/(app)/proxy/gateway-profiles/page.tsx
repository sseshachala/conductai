"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"

import AppShell from "@/components/AppShell"
import GatewayProfileV2DeleteDialog from "@/components/settings/GatewayProfileV2DeleteDialog"
import GatewayProfileV2ImportDialog from "@/components/settings/GatewayProfileV2ImportDialog"
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
// Presets pair same-vendor fallbacks only. The capability catalog
// requires every target to serve every accepted operation — so
// "Anthropic primary + OpenAI fallback" fails publish because OpenAI
// can't serve anthropic_messages. If a customer wants cross-vendor
// failover, that's a follow-up on top of the passthrough executor
// (#2005) which translates between surfaces.
const PRESET_CHIPS: PresetChip[] = [
  {
    label: "Claude Sonnet + Haiku fallback",
    hint: "Primary → Claude Sonnet; fallback → Claude Haiku.",
    name: "claude-sonnet",
    workingCopy: {
      name: "claude-sonnet",
      model_alias: "claude-sonnet",
      timeout_seconds: 60,
      max_attempts: 2,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "anthropic", model: "claude-sonnet-4-6",
          credential_ref: "",
        },
        {
          id: "fallback", transport: "native_http",
          provider: "anthropic", model: "claude-haiku-4-5-20251001",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "Claude Opus (single)",
    hint: "Most capable Anthropic model, no fallback.",
    name: "claude-opus",
    workingCopy: {
      name: "claude-opus",
      model_alias: "claude-opus",
      timeout_seconds: 60,
      max_attempts: 1,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "anthropic", model: "claude-opus-4-7",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "GPT-4o + mini fallback",
    hint: "Primary → GPT-4o; fallback → GPT-4o mini.",
    name: "gpt-4o",
    workingCopy: {
      name: "gpt-4o",
      model_alias: "gpt-4o",
      timeout_seconds: 60,
      max_attempts: 2,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "openai", model: "gpt-4o",
          credential_ref: "",
        },
        {
          id: "fallback", transport: "native_http",
          provider: "openai", model: "gpt-4o-mini",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "o1 reasoning (single)",
    hint: "OpenAI o1, no fallback.",
    name: "o1",
    workingCopy: {
      name: "o1",
      model_alias: "o1",
      timeout_seconds: 120,
      max_attempts: 1,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "openai", model: "o1",
          credential_ref: "",
        },
      ],
    },
  },
]

function isPublished(profile: GatewayProfileV2Out): boolean {
  // v3: served state lives on active_revision_id. Working_copy is
  // locked whenever this is non-null.
  return profile.active_revision_id !== null
}

function conditIdentifier(profile: GatewayProfileV2Out): string {
  const alias = profile.model_alias ?? ""
  return alias ? `cond-${profile.cond_code}-${alias}` : `cond-${profile.cond_code}`
}

type Filter = "all" | "draft" | "published"

export default function GatewayProfilesV2Page() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { role } = useGuardRole()
  const workspaceId = activeWorkspace?.id ?? ""
  const isAdmin = role === "admin"

  // R4 fix: allow ``?select=<uuid>`` to preselect a profile on load.
  // The import endpoint's ``next_url`` uses this so following the
  // link opens the newly-created draft directly (no manual scroll +
  // click through the profile list).
  const searchParams = useSearchParams()
  const selectParam = searchParams?.get("select") ?? null

  const [profiles, setProfiles] = useState<GatewayProfileV2Out[]>([])
  const [envs, setEnvs] = useState<EnvironmentRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>("")
  const [busy, setBusy] = useState<string>("")
  const [filter, setFilter] = useState<Filter>("all")
  const [showPublish, setShowPublish] = useState(false)
  const [showRollback, setShowRollback] = useState(false)
  const [showImport, setShowImport] = useState(false)
  // Type-to-confirm delete dialog target. When non-null, renders the
  // dialog against this profile. Cleared on confirm or cancel.
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

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
      setSelectedId(prev => {
        // Highest priority: caller-provided ?select=<uuid>, but only
        // if the profile actually exists in this workspace (protects
        // against stale bookmarks / cross-workspace links).
        if (selectParam && rows.some(r => r.id === selectParam)) {
          return selectParam
        }
        return prev ?? rows[0]?.id ?? null
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profiles")
    } finally { setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch, workspaceId, selectParam])

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
      const created = await guard.gatewayProfilesV2.create(
        authFetch, workspaceId, { name: candidate, working_copy: wc },
      )
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
      const created = await guard.gatewayProfilesV2.create(
        authFetch, workspaceId, { name: candidate },
      )
      await load()
      if (created?.id) setSelectedId(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally { setBusy("") }
  }

  function requestDelete(profile: GatewayProfileV2Out) {
    // Kept sync — hands off to the type-to-confirm dialog. Actual
    // deletion runs from the dialog's own callback (see the render
    // site for GatewayProfileV2DeleteDialog below).
    if (!workspaceId || !isAdmin) return
    if (isPublished(profile) || profile.revisions.length > 0) {
      setError(`"${profile.name}" has been published — it can't be deleted. Duplicate to iterate.`)
      return
    }
    setError("")
    setPendingDeleteId(profile.id)
  }

  async function duplicateProfile(source: GatewayProfileV2Out) {
    if (!workspaceId || !isAdmin) return
    setBusy(`duplicate:${source.id}`); setError("")
    try {
      const taken = new Set(profiles.map(p => p.name.toLowerCase()))
      let candidate = `${source.name}-copy`
      let n = 2
      while (taken.has(candidate.toLowerCase())) {
        candidate = `${source.name}-copy-${n}`
        n += 1
      }

      // #2034 fix — a duplicated profile MUST carry the source
      // profile's credential_refs so Save doesn't immediately fail on
      // empty vault picks. Two possible sources for the seed:
      //
      //   1. ``source.working_copy`` — populated for drafts. May be
      //      empty or missing targets for a profile that was
      //      published then locked (working_copy is API-locked after
      //      publish; some deployments null it out entirely).
      //   2. Latest revision snapshot — the immutable snapshot from
      //      publish. Always has full targets with credential_refs
      //      because publish's capability check would have failed
      //      otherwise.
      //
      // Prefer (1) when it has non-empty targets, else fetch (2).
      // Keeps drafts editable-in-place while making published-profile
      // duplicates work without a follow-up credential re-pick.
      const wcTargets = (source.working_copy as {
        targets?: Array<Record<string, unknown>>
      } | null | undefined)?.targets ?? []
      const wcHasCredentials = wcTargets.length > 0 && wcTargets.every(
        t => typeof t?.credential_ref === "string" && (t.credential_ref as string).length > 0,
      )

      let seed: Record<string, unknown>
      if (wcHasCredentials) {
        seed = source.working_copy as Record<string, unknown>
      } else if (source.revisions && source.revisions.length > 0) {
        // Latest published revision has the full snapshot. Sorted
        // by version descending on the server; fall back to the
        // first entry if that order ever changes.
        const latest = source.revisions.reduce(
          (a, b) => (a.version >= b.version ? a : b),
        )
        try {
          seed = await guard.gatewayProfilesV2.revisionSnapshot(
            authFetch, workspaceId, source.id, latest.id,
          )
        } catch {
          // Snapshot fetch failed — fall back to the (possibly empty)
          // working_copy so the duplicate at least creates. The
          // editor's Save gate will block until the admin fills
          // credentials, which is the pre-fix behavior anyway.
          seed = (source.working_copy as Record<string, unknown>) ?? {}
        }
      } else {
        // Draft with no revisions and no targets. Duplicate lands
        // an empty draft; admin fills it from scratch. Save gate
        // still blocks a bare save.
        seed = (source.working_copy as Record<string, unknown>) ?? {}
      }

      const wc = {
        ...seed,
        name: candidate,
        model_alias: candidate,
      }
      const created = await guard.gatewayProfilesV2.create(
        authFetch, workspaceId, { name: candidate, working_copy: wc },
      )
      await load()
      if (created?.id) setSelectedId(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Duplicate failed")
    } finally { setBusy("") }
  }

  const visibleProfiles = useMemo(() => {
    if (filter === "all") return profiles
    return profiles.filter(p =>
      filter === "published" ? isPublished(p) : !isPublished(p),
    )
  }, [profiles, filter])

  return (
    <AppShell>
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">Gateway Profiles v2</h1>
          <p className="page-sub">
            A profile pins an ordered list of upstream targets and a set of vault credentials
            behind a stable identifier. Once published, the working copy is locked —
            duplicate to iterate. Clients hit the gateway using the profile's
            <code className="mono" style={{ fontSize: 12 }}> cond-…</code> identifier.
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
              <button className="chip" disabled={busy !== ""}
                onClick={() => setShowImport(true)}
                title="Paste a Gateway Profile v2 JSON to import as a new draft.">
                Import JSON
              </button>
            </div>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20 }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span className="eyebrow">Profiles ({visibleProfiles.length}/{profiles.length})</span>
            </div>
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              {(["all", "draft", "published"] as Filter[]).map(f => (
                <button key={f} onClick={() => setFilter(f)} className="chip"
                  style={{
                    height: 26, fontSize: 12,
                    background: filter === f ? "var(--accent-weak)" : "var(--surface)",
                    borderColor: filter === f ? "var(--accent-ring)" : "var(--border)",
                    color: filter === f ? "var(--accent-text)" : "var(--text-2)",
                  }}>
                  {f === "all" ? "All" : f === "draft" ? "Drafts" : "Published"}
                </button>
              ))}
            </div>

            {loading ? (
              <div style={{ height: 96, background: "var(--surface-2)", borderRadius: 8 }} />
            ) : visibleProfiles.length === 0 ? (
              <div className="card card-pad" style={{ textAlign: "center", background: "var(--surface-2)" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                  {profiles.length === 0
                    ? "No profiles yet. Click a preset above."
                    : `No ${filter} profiles.`}
                </p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {visibleProfiles.map(p => (
                  <ProfileListItem key={p.id} profile={p}
                    active={selectedId === p.id}
                    canDelete={isAdmin}
                    onSelect={() => setSelectedId(p.id)}
                    onDelete={() => requestDelete(p)} />
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
                onDuplicate={() => void duplicateProfile(selected)}
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
            workspaceId={workspaceId} profile={selected}
            onClose={() => setShowPublish(false)}
            onPublished={() => void load()} />
        )}
        {selected && showRollback && (
          <GatewayProfileV2RollbackDialog
            workspaceId={workspaceId} profile={selected}
            onClose={() => setShowRollback(false)}
            onRolledBack={() => void load()} />
        )}
        {pendingDeleteId && (() => {
          const target = profiles.find(p => p.id === pendingDeleteId)
          if (!target) return null
          return (
            <GatewayProfileV2DeleteDialog
              workspaceId={workspaceId}
              profile={target}
              onClose={() => setPendingDeleteId(null)}
              onDeleted={() => {
                if (selectedId === target.id) setSelectedId(null)
                void load()
              }}
            />
          )
        })()}
        {showImport && (
          <GatewayProfileV2ImportDialog
            workspaceId={workspaceId}
            onClose={() => setShowImport(false)}
            onImported={(profileId) => {
              // Reload the list and select the imported profile so
              // the editor opens on it — matches the CLI's next_url
              // behavior (jump straight to the editor page).
              void load().then(() => setSelectedId(profileId))
            }}
          />
        )}
      </div>
    </AppShell>
  )
}


function ProfileListItem({
  profile, active, canDelete, onSelect, onDelete,
}: {
  profile: GatewayProfileV2Out
  active: boolean
  canDelete: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const published = isPublished(profile)
  const canShowDelete = canDelete && !published
  return (
    <div onClick={onSelect} className="card"
      style={{
        display: "flex", flexDirection: "column", alignItems: "stretch",
        gap: 4, padding: "10px 12px", cursor: "pointer",
        background: active ? "var(--accent-weak)" : "var(--surface)",
        borderColor: active ? "var(--accent-ring)" : "var(--border)",
      }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 13.5, fontWeight: 600, color: active ? "var(--accent-text)" : "var(--text)" }}>
          {profile.name}
        </span>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {published ? (
            <span className="sbadge ok">published</span>
          ) : (
            <span className="sbadge warn">draft</span>
          )}
          {canShowDelete && (
            <button
              onClick={e => { e.stopPropagation(); onDelete() }}
              className="btn btn-ghost btn-sm btn-icon"
              style={{ height: 24, width: 24, color: "var(--err)", borderColor: "var(--err-bd)" }}
              title={`Delete draft "${profile.name}"`}
              aria-label={`Delete ${profile.name}`}
            >×</button>
          )}
        </div>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
        alias: <span className="mono">{profile.model_alias ?? "—"}</span>
      </div>
    </div>
  )
}


function ProfileDetail({
  profile, envs, envName, workspaceId, isAdmin,
  onReload, onOpenPublish, onOpenRollback, onDuplicate,
}: {
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  envName: (envId: string) => string
  workspaceId: string
  isAdmin: boolean
  onReload: () => void
  onOpenPublish: () => void
  onOpenRollback: () => void
  onDuplicate: () => void
}) {
  const published = isPublished(profile)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <h2 style={{ margin: 0, fontSize: 17, fontWeight: 650 }}>{profile.name}</h2>
            {published ? (
              <span className="sbadge ok">published · locked</span>
            ) : (
              <span className="sbadge warn">draft</span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
            alias <code className="mono">{profile.model_alias ?? "—"}</code>
            {" · "}created {new Date(profile.created_at).toLocaleDateString()}
          </div>
        </div>
        {isAdmin && (
          <div style={{ display: "flex", gap: 6 }}>
            {published ? (
              <>
                <button onClick={onDuplicate} className="btn btn-primary btn-sm">
                  Duplicate to new draft
                </button>
                <button onClick={onOpenRollback} className="btn btn-ghost btn-sm"
                  disabled={profile.revisions.length < 2}>Rollback…</button>
              </>
            ) : (
              <button onClick={onOpenPublish} className="btn btn-primary btn-sm"
                disabled={!profile.working_copy}>Publish…</button>
            )}
          </div>
        )}
      </div>

      {published && <HowToUse profile={profile} />}

      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          Working copy {published && (
            <span style={{ color: "var(--warn)", textTransform: "none", letterSpacing: 0, fontWeight: 500 }}>
              — read-only (duplicate to edit)
            </span>
          )}
        </div>
        <GatewayProfileV2Editor
          workspaceId={workspaceId}
          profile={profile}
          envs={envs}
          // Editor already treats isAdmin=false as read-only for every
          // input. Passing false when the profile is published locks
          // every field in one line.
          isAdmin={isAdmin && !published}
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


function HowToUse({ profile }: { profile: GatewayProfileV2Out }) {
  const identifier = conditIdentifier(profile)
  // Z4 fix — the Gateway URL must include a provider suffix.
  // Backend router mounts at ``/gateway/v1/<provider>/<vendor-path>``
  // (see ``apps/api/app/modules/guard/routers/gateway_proxy.py`` —
  // prefix ``/gateway/v1``, provider = next path segment). Displaying
  // just ``/gateway/v1`` was still an incomplete URL — SDKs point at
  // it and get 404.
  //
  // Derive the provider suffix from the profile's targets. For a
  // profile with an anthropic target, users need
  // ``/gateway/v1/anthropic``. For OpenAI + OpenRouter (via
  // passthrough) users go through ``/gateway/v1/openai``. When a
  // profile fronts multiple providers (mixed fallback), we list all
  // of them so the admin picks the one matching their SDK.
  // Gateway lives on a different hostname from the dashboard
  // (delegator-gateway service, per #2056/#2066). Do not derive the
  // URL from window.location.origin — the user is browsing on the
  // dashboard host and would get https://app.conductai.ai/gateway/*
  // which 404s. Read from env with a prod default so local dev can
  // point at http://localhost:8000 via NEXT_PUBLIC_GATEWAY_URL.
  const origin = (process.env.NEXT_PUBLIC_GATEWAY_URL || "https://gateway.conductai.ai").replace(/\/$/, "")
  const wc = (profile.working_copy as {
    targets?: Array<{ transport?: string; provider?: string; integration?: string }>
  } | null | undefined) ?? {}
  const surfaces = new Set<string>()
  for (const t of wc.targets ?? []) {
    // Passthrough routes speak OpenAI Chat Completions today
    // (OpenRouter is OpenAI-compatible) — the SDK still points at
    // /gateway/v1/openai for those.
    if (t.transport === "http_passthrough") {
      surfaces.add("openai")
    } else if (t.provider === "anthropic" || t.provider === "openai") {
      surfaces.add(t.provider)
    }
  }
  const urls = surfaces.size === 0
    // Fallback for a draft with no targets yet — show both so the
    // admin sees the pattern.
    ? [`${origin}/gateway/v1/anthropic`, `${origin}/gateway/v1/openai`]
    : [...surfaces].map(p => `${origin}/gateway/v1/${p}`)

  return (
    <div className="card card-pad" style={{ background: "var(--surface-2)" }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>How to use this profile</div>
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", rowGap: 8, columnGap: 12, alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--text-2)" }}>Profile identifier</span>
        <code className="mono" style={{ fontSize: 12.5, wordBreak: "break-all" }}>{identifier}</code>
        <CopyButton value={identifier} />

        <span style={{ fontSize: 12, color: "var(--text-2)" }}>
          Gateway URL{urls.length > 1 ? "s (per SDK)" : ""}
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {urls.map(u => (
            <code
              key={u}
              className="mono"
              style={{ fontSize: 12.5, wordBreak: "break-all" }}
            >{u}</code>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {urls.map(u => (
            <CopyButton key={u} value={u} />
          ))}
        </div>

        <span style={{ fontSize: 12, color: "var(--text-2)" }}>Auth token</span>
        <span style={{ fontSize: 12.5, color: "var(--text-2)" }}>
          Your workspace member token (or an Agent Identity token).
        </span>
        <a className="btn btn-ghost btn-sm" href="/settings" style={{ height: 26, fontSize: 11.5 }}>Manage</a>
      </div>
      <p style={{ fontSize: 11.5, color: "var(--text-3)", margin: "10px 0 0" }}>
        Point your SDK's base URL at the matching entry above (Anthropic
        SDK → ``/gateway/v1/anthropic``, OpenAI SDK → ``/gateway/v1/openai``)
        and set <code className="mono">model:</code> to the profile identifier.
      </p>
    </div>
  )
}


function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button className="btn btn-ghost btn-sm"
      style={{ height: 26, fontSize: 11.5 }}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch { /* clipboard unavailable */ }
      }}>
      {copied ? "Copied" : "Copy"}
    </button>
  )
}
