"use client"

import GatewayProfileV2Editor from "@/components/settings/GatewayProfileV2Editor"
import RateLimitsPanel from "@/components/gateway/RateLimitsPanel"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { validateGatewayProfileFields } from "@/lib/gatewayProfileValidation"

import { type EnvironmentRow, isPublished, conditIdentifier } from "./presets"
import { TestPanel, CopyButton } from "./TestPanel"

export function ProfileListItem({
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


export function ProfileDetail({
  profile, envs, envName, workspaceId, isAdmin,
  onReload, onOpenPublish, onDuplicate,
}: {
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  envName: (envId: string) => string
  workspaceId: string
  isAdmin: boolean
  onReload: () => void
  onOpenPublish: () => void
  onDuplicate: () => void
}) {
  const published = isPublished(profile)
  const publishIssue = Object.values(validateGatewayProfileFields(profile.working_copy ?? {}))[0]
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
              </>
            ) : (
              <button onClick={onOpenPublish} className="btn btn-primary btn-sm"
                disabled={!!publishIssue} title={publishIssue}>Publish…</button>
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

      <RateLimitsPanel key={`${workspaceId}:${profile.id}`} workspaceId={workspaceId}
        profileId={profile.id} isAdmin={isAdmin} />

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


export function HowToUse({ profile }: { profile: GatewayProfileV2Out }) {
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
  // passthrough) users go through ``/gateway/v1/openai/v1``. When a
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
    // /gateway/v1/openai/v1 for those.
    if (t.transport === "http_passthrough") {
      surfaces.add("openai")
    } else if (t.provider === "anthropic" || t.provider === "openai") {
      surfaces.add(t.provider)
    }
  }
  // SDK base URLs. The OpenAI SDK appends ``/chat/completions`` and the
  // Gateway serves ``/gateway/v1/openai/v1/chat/completions``, so its base
  // needs the ``/v1``. The Anthropic SDK appends ``/v1/messages`` itself.
  const sdkBase = (p: string) => `${origin}/gateway/v1/${p}${p === "openai" ? "/v1" : ""}`
  const urls = surfaces.size === 0
    // Fallback for a draft with no targets yet — show both so the
    // admin sees the pattern.
    ? [sdkBase("anthropic"), sdkBase("openai")]
    : [...surfaces].map(sdkBase)

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
        SDK → ``/gateway/v1/anthropic``, OpenAI SDK → ``/gateway/v1/openai/v1``)
        and set <code className="mono">model:</code> to the profile identifier.
      </p>
      <TestPanel profileId={profile.id} urls={urls} />
    </div>
  )
}
