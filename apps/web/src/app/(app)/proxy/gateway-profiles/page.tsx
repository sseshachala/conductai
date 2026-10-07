"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "next/navigation"

import AppShell from "@/components/AppShell"
import GatewayProfileV2DeleteDialog from "@/components/settings/GatewayProfileV2DeleteDialog"
import GatewayProfileV2ImportDialog from "@/components/settings/GatewayProfileV2ImportDialog"
import GatewayProfileV2PublishDialog from "@/components/settings/GatewayProfileV2PublishDialog"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { environments, guard } from "@/lib/api"
import { API } from "@/lib/api/client"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { type EnvironmentRow, type PresetChip, PRESET_CHIPS, isPublished } from "./_components/presets"
import { ProfileListItem, ProfileDetail } from "./_components/ProfileDetail"

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
  const [showImport, setShowImport] = useState(false)
  // Type-to-confirm delete dialog target. When non-null, renders the
  // dialog against this profile. Cleared on confirm or cancel.
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const loadGeneration = useRef(0)

  const load = useCallback(async () => {
    const current = ++loadGeneration.current
    if (!workspaceId) return
    setLoading(true); setError(""); setProfiles([]); setEnvs([])
    try {
      const [rows, envRows] = await Promise.all([
        guard.gatewayProfilesV2.list(authFetch, workspaceId),
        environments.list(authFetch),
      ])
      if (current !== loadGeneration.current) return
      setProfiles(rows)
      setEnvs(envRows)
      setSelectedId(prev => {
        // Highest priority: caller-provided ?select=<uuid>, but only
        // if the profile actually exists in this workspace (protects
        // against stale bookmarks / cross-workspace links).
        if (selectParam && rows.some(r => r.id === selectParam)) {
          return selectParam
        }
        return rows.some(r => r.id === prev) ? prev : rows[0]?.id ?? null
      })
    } catch (err) {
      if (current === loadGeneration.current) setError(err instanceof Error ? err.message : "Failed to load profiles")
    } finally { if (current === loadGeneration.current) setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch, workspaceId, selectParam])

  useEffect(() => { void load(); return () => { loadGeneration.current++ } }, [load])

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
          <h1 className="page-title">Gateways</h1>
          <p className="page-sub">
            A profile pins an ordered list of upstream targets and a set of vault credentials
            behind a stable identifier. Once published, the working copy is locked —
            duplicate to iterate. Clients hit the gateway using the profile's
            <code className="mono" style={{ fontSize: 12 }}> cond-…</code> identifier.
          </p>
        </div>

        <div>

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
      </div>
    </AppShell>
  )
}


