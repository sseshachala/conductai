"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import AppShell from "@/components/AppShell"
import { LensEmbed } from "@/components/glens/LensEmbed"
import GatewayProfileV2PublishDialog from "@/components/settings/GatewayProfileV2PublishDialog"
import GatewayProfileV2RollbackDialog from "@/components/settings/GatewayProfileV2RollbackDialog"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { environments, guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"

// #2007 — Gateway Profiles v2 admin surface, Lens-first (#1830 embed).
//
// Lens is the primary composer: preset chips populate an initial query,
// admins refine in chat, the profile preview below reflects the current
// server state. No editable form — overrides happen through chat.
// Publish + Rollback stay as classic dialogs because they're actions,
// not fields.
//
// Chips currently populate the composer with a canned prompt; Lens
// answers conversationally. Actual mutation ("create draft named X",
// "add fallback target Y") lands when the Lens v2-config tool set
// ships. Kept the chips ready-shaped so wiring is a one-line change.

type EnvironmentRow = { id: string; name: string }

const PRESET_CHIPS: Array<{ label: string; prompt: string }> = [
  {
    label: "Route \"coding\" via Claude, GPT-4 backup",
    prompt: "Create a Gateway Profile v2 where the alias 'coding' routes to Claude Sonnet 4 (Anthropic) with GPT-4o (OpenAI) as fallback.",
  },
  {
    label: "Anthropic only, no fallback",
    prompt: "Create a Gateway Profile v2 that routes the alias 'anthropic-only' to Claude Sonnet 4 with no fallback.",
  },
  {
    label: "Cheap alias (Haiku + gpt-4o-mini)",
    prompt: "Create a Gateway Profile v2 named 'cheap' that tries Claude Haiku first and falls back to gpt-4o-mini.",
  },
  {
    label: "Publish current draft to Production",
    prompt: "Publish the currently selected Gateway Profile draft to the Production environment.",
  },
  {
    label: "What can this page do?",
    prompt: "Explain what Gateway Profiles v2 are and what I can do on this page. Keep it short.",
  },
]

function summarizeTargets(profile: GatewayProfileV2Out): Array<{
  id: string; role: "primary" | "fallback"; where: string; model: string; credential: string
}> {
  const wc = profile.working_copy as {
    targets?: Array<Record<string, unknown>>
  } | null
  const targets = wc?.targets ?? []
  return targets.map((t, i) => ({
    id: String(t.id ?? `target-${i + 1}`),
    role: i === 0 ? "primary" : "fallback",
    where: t.transport === "http_passthrough"
      ? `${String(t.integration ?? "")}`
      : `${String(t.provider ?? "")}`,
    model: String(t.model ?? ""),
    credential: String(t.credential_ref ?? ""),
  }))
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

  const [lensQuery, setLensQuery] = useState<string | null>(null)
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

  function askLens(prompt: string) { setLensQuery(prompt) }

  return (
    <AppShell>
      <div className="page">
        <div className="page-head">
          <h1 className="page-title">Gateway Profiles v2</h1>
          <p className="page-sub">
            Tell Lens where you want an alias to route. Everything an admin
            would fill in a form — provider, model, credential, fallback,
            environment — comes out of the conversation.
          </p>
        </div>

        {error && (
          <div className="sbadge err" style={{ display: "block", height: "auto", padding: "10px 14px", borderRadius: 8, marginBottom: 16, whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        <ChipStrip
          chips={PRESET_CHIPS}
          onPick={askLens}
          disabled={!isAdmin}
        />

        <div style={{ marginTop: 14 }}>
          <LensEmbed
            initialQuery={lensQuery}
            height="52vh"
            title="Lens · Gateway Profiles"
            emptyText="Pick a chip above, or type what you want (e.g. “route ‘coding’ through Claude, GPT-4 as backup”)."
            placeholder="Ask Lens to create, edit, or publish a profile…"
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20, marginTop: 22 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>
              Profiles ({profiles.length})
            </div>
            {loading ? (
              <div style={{ height: 96, background: "var(--surface-2)", borderRadius: 8 }} />
            ) : profiles.length === 0 ? (
              <div className="card card-pad" style={{ textAlign: "center", background: "var(--surface-2)" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                  No profiles yet. Ask Lens to create one.
                </p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {profiles.map(p => (
                  <ProfileListItem
                    key={p.id}
                    profile={p}
                    active={selectedId === p.id}
                    onSelect={() => setSelectedId(p.id)}
                  />
                ))}
              </div>
            )}
          </div>

          <div>
            {selected ? (
              <ProfilePreview
                profile={selected}
                envName={envName}
                isAdmin={isAdmin}
                onExplain={() => askLens(`Explain the profile "${selected.name}" in one paragraph.`)}
                onOpenPublish={() => setShowPublish(true)}
                onOpenRollback={() => setShowRollback(true)}
              />
            ) : (
              <div className="card card-pad" style={{ background: "var(--surface-2)", textAlign: "center" }}>
                <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                  Select a profile to see its live shape.
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


function ChipStrip({
  chips, onPick, disabled,
}: {
  chips: Array<{ label: string; prompt: string }>
  onPick: (prompt: string) => void
  disabled: boolean
}) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {chips.map(c => (
        <button key={c.label} className="chip" disabled={disabled}
          title={c.prompt}
          onClick={() => onPick(c.prompt)}
          style={{ opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer" }}>
          {c.label}
        </button>
      ))}
    </div>
  )
}


function ProfileListItem({
  profile, active, onSelect,
}: {
  profile: GatewayProfileV2Out
  active: boolean
  onSelect: () => void
}) {
  const published = profile.revisions.length > 0 || profile.bindings.length > 0
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
      </div>
    </button>
  )
}


function ProfilePreview({
  profile, envName, isAdmin, onExplain, onOpenPublish, onOpenRollback,
}: {
  profile: GatewayProfileV2Out
  envName: (envId: string) => string
  isAdmin: boolean
  onExplain: () => void
  onOpenPublish: () => void
  onOpenRollback: () => void
}) {
  const targets = summarizeTargets(profile)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 650 }}>{profile.name}</h2>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
            alias <span className="mono">{profile.model_alias ?? "—"}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={onExplain} className="btn btn-ghost btn-sm">Ask Lens</button>
          {isAdmin && (
            <>
              <button onClick={onOpenPublish} className="btn btn-primary btn-sm"
                disabled={!profile.working_copy}>Publish…</button>
              <button onClick={onOpenRollback} className="btn btn-ghost btn-sm"
                disabled={profile.revisions.length === 0}>Rollback…</button>
            </>
          )}
        </div>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Where it goes</div>
        {targets.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
            No targets yet — ask Lens to add one.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {targets.map(t => (
              <div key={t.id} className="card" style={{ padding: "8px 12px", display: "flex", gap: 10, alignItems: "center" }}>
                <span className={`sbadge ${t.role === "primary" ? "info" : "warn"}`}>{t.role}</span>
                <span className="mono" style={{ fontSize: 12.5 }}>{t.where}</span>
                <span style={{ color: "var(--text-3)" }}>·</span>
                <span className="mono" style={{ fontSize: 12.5 }}>{t.model || "(no model)"}</span>
                <span style={{ color: "var(--text-3)", marginLeft: "auto", fontSize: 11.5 }}>
                  {t.credential || "no credential"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Live in</div>
        {profile.bindings.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
            Not published yet.
          </p>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {profile.bindings.map(b => (
              <span key={`${b.environment_id}:${b.model_alias}`}
                className="sbadge ok"
                title={`revision ${b.revision_id.slice(0, 8)}… since ${new Date(b.updated_at).toLocaleString()}`}>
                {envName(b.environment_id)}
              </span>
            ))}
          </div>
        )}
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
