"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import RateLimitsPanel from "@/components/gateway/RateLimitsPanel"
import GatewayProfileV2DeleteDialog from "@/components/settings/GatewayProfileV2DeleteDialog"
import GatewayProfileV2Editor from "@/components/settings/GatewayProfileV2Editor"
import GatewayProfileV2PublishDialog from "@/components/settings/GatewayProfileV2PublishDialog"
import GatewayProfileV2UnpublishDialog from "@/components/settings/GatewayProfileV2UnpublishDialog"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { validateGatewayProfileFields } from "@/lib/gatewayProfileValidation"

import { type EnvironmentRow, conditIdentifier, latestRevision, profileStatus } from "./presets"
import { ChangesBadge, StatusBadge } from "./StatusBadge"
import { CopyButton, TestPanel } from "./TestPanel"

export type DetailTab = "overview" | "edit" | "revisions" | "rate-limits" | "test"

export const LIST_HREF = "/proxy/gateway-profiles"

export function ProfileDetail({
  profile, envs, workspaceId, isAdmin, onReload, initialTab = "overview",
}: {
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  workspaceId: string
  isAdmin: boolean
  onReload: () => void
  initialTab?: DetailTab
}) {
  const router = useRouter()
  const status = profileStatus(profile)
  const [tab, setTab] = useState<DetailTab>(initialTab)
  const [dialog, setDialog] = useState<"publish" | "unpublish" | "delete" | null>(null)
  const identifier = conditIdentifier(profile)
  const publishIssue = Object.values(validateGatewayProfileFields(profile.working_copy ?? {}))[0]
  const latest = latestRevision(profile)
  const nothingToPublish = status === "published" && !profile.has_unpublished_changes
  const publishDisabledReason = publishIssue
    ?? (nothingToPublish ? `No changes since v${latest?.version ?? 1}` : undefined)

  const tabs: Array<{ id: DetailTab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "edit", label: "Edit" },
    { id: "revisions", label: `Revisions (${profile.revisions.length})` },
    ...(isAdmin ? [{ id: "rate-limits" as const, label: "Rate limits" }] : []),
    { id: "test", label: "Test" },
  ]
  const activeTab = tabs.some(t => t.id === tab) ? tab : "overview"

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
      <Link href={LIST_HREF} style={{ fontSize: 12.5, color: "var(--text-2)" }}>
        ← Back to gateway profiles
      </Link>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 650, overflowWrap: "anywhere" }}>{profile.name}</h1>
            <StatusBadge profile={profile} />
            <ChangesBadge profile={profile} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
            <code className="mono" style={{ fontSize: 12.5, overflowWrap: "anywhere" }}>{identifier}</code>
            <CopyButton value={identifier} label="Copy model ID" />
          </div>
        </div>
        {isAdmin && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-primary btn-sm" onClick={() => setDialog("publish")}
              disabled={!!publishDisabledReason} title={publishDisabledReason}>Publish…</button>
            {status === "published" && (
              <button className="btn btn-ghost btn-sm" onClick={() => setDialog("unpublish")}>Unpublish…</button>
            )}
            <button className="btn btn-ghost btn-sm" style={{ color: "var(--err)", borderColor: "var(--err-bd)" }}
              onClick={() => setDialog("delete")} disabled={status === "published"}
              title={status === "published" ? "Unpublish before deleting" : undefined}>
              Delete…
            </button>
          </div>
        )}
      </div>

      <div role="tablist" aria-label="Profile sections"
        style={{ display: "flex", gap: 6, overflowX: "auto", borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
        {tabs.map(t => (
          <button key={t.id} role="tab" aria-selected={activeTab === t.id} onClick={() => setTab(t.id)}
            className="chip"
            style={{
              flexShrink: 0, height: 28, fontSize: 12.5,
              background: activeTab === t.id ? "var(--accent-weak)" : "var(--surface)",
              borderColor: activeTab === t.id ? "var(--accent-ring)" : "var(--border)",
              color: activeTab === t.id ? "var(--accent-text)" : "var(--text-2)",
            }}>{t.label}</button>
        ))}
      </div>

      <div role="tabpanel" style={{ minWidth: 0 }}>
        {activeTab === "overview" && <Overview profile={profile} />}
        {activeTab === "edit" && (
          <GatewayProfileV2Editor workspaceId={workspaceId} profile={profile} envs={envs}
            isAdmin={isAdmin} onSaved={onReload} />
        )}
        {activeTab === "revisions" && (
          <Revisions profile={profile} workspaceId={workspaceId} isAdmin={isAdmin} onChanged={onReload} />
        )}
        {activeTab === "rate-limits" && isAdmin && (
          <RateLimitsPanel key={`${workspaceId}:${profile.id}`} workspaceId={workspaceId}
            profileId={profile.id} isAdmin={isAdmin} />
        )}
        {activeTab === "test" && (
          status === "published"
            ? <TestPanel profileId={profile.id} urls={gatewayUrls(profile)} />
            : <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
                Publish this profile to test it — only published profiles are routed.
              </p>
        )}
      </div>

      {dialog === "publish" && (
        <GatewayProfileV2PublishDialog workspaceId={workspaceId} profile={profile}
          onClose={() => setDialog(null)} onPublished={onReload} />
      )}
      {dialog === "unpublish" && (
        <GatewayProfileV2UnpublishDialog workspaceId={workspaceId} profile={profile}
          onClose={() => setDialog(null)} onUnpublished={onReload} />
      )}
      {dialog === "delete" && (
        <GatewayProfileV2DeleteDialog workspaceId={workspaceId} profile={profile}
          onClose={() => setDialog(null)} onDeleted={() => router.push(LIST_HREF)} />
      )}
    </div>
  )
}

function Overview({ profile }: { profile: GatewayProfileV2Out }) {
  const status = profileStatus(profile)
  const latest = latestRevision(profile)
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {status === "unpublished" && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 14px", borderRadius: 8, whiteSpace: "normal" }}>
          This profile is unpublished — requests to its model ID are failing. Publish it to resume routing.
        </div>
      )}
      <div className="card card-pad" style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", fontSize: 13 }}>
        <span style={{ color: "var(--text-3)" }}>Alias</span>
        <code className="mono">{profile.model_alias ?? "—"}</code>
        <span style={{ color: "var(--text-3)" }}>Created</span>
        <span>{new Date(profile.created_at).toLocaleDateString()}</span>
        <span style={{ color: "var(--text-3)" }}>Revisions</span>
        <span>{profile.revisions.length}</span>
        <span style={{ color: "var(--text-3)" }}>Last published</span>
        <span>{latest ? `v${latest.version} · ${new Date(latest.published_at).toLocaleString()}` : "Never"}</span>
      </div>
      <HowToUse profile={profile} />
    </div>
  )
}

function Revisions({
  profile, workspaceId, isAdmin, onChanged,
}: {
  profile: GatewayProfileV2Out
  workspaceId: string
  isAdmin: boolean
  onChanged: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")
  const status = profileStatus(profile)
  const canRollback = isAdmin && status !== "draft"
  const rows = [...profile.revisions].sort((a, b) => b.version - a.version)
  const confirmTarget = rows.find(r => r.id === confirmId)

  async function rollback(revisionId: string) {
    setBusy(true); setErr("")
    try {
      await guard.gatewayProfilesV2.rollback(authFetch, workspaceId, profile.id, revisionId)
      setConfirmId(null)
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Rollback failed")
    } finally { setBusy(false) }
  }

  if (rows.length === 0) {
    return <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>No revisions yet. Publish to create v1.</p>
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {err && <p role="alert" style={{ margin: 0, color: "var(--err)", fontSize: 12, overflowWrap: "anywhere" }}>{err}</p>}
      {confirmTarget && (status === "unpublished" || profile.has_unpublished_changes) && (
        <p role="status" style={{ margin: 0, color: "var(--warn)", fontSize: 12 }}>
          {status === "unpublished" && `Rolling back publishes v${confirmTarget.version} — requests to this alias start routing again. `}
          {profile.has_unpublished_changes && `Your unpublished edits will be replaced by v${confirmTarget.version}.`}
        </p>
      )}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--surface-2)", color: "var(--text-3)" }}>
              <th scope="col" style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Version</th>
              <th scope="col" style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published by</th>
              <th scope="col" style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600 }}>Published at</th>
              <th scope="col" style={{ padding: "6px 10px" }}><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const active = r.id === profile.active_revision_id
              return (
                <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "6px 10px", whiteSpace: "nowrap" }}>
                    <span className="sbadge info">v{r.version}</span>{" "}
                    {active && <span className="sbadge ok">Active</span>}
                  </td>
                  <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{r.published_by}</td>
                  <td style={{ padding: "6px 10px", color: "var(--text-2)" }}>{new Date(r.published_at).toLocaleString()}</td>
                  <td style={{ padding: "6px 10px", textAlign: "right", whiteSpace: "nowrap" }}>
                    {canRollback && !active && (confirmId === r.id ? (
                      <span style={{ display: "inline-flex", gap: 6 }}>
                        <button className="btn btn-primary btn-sm" disabled={busy}
                          onClick={() => void rollback(r.id)}>
                          {busy ? "Rolling back…" : `Confirm rollback to v${r.version}`}
                        </button>
                        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => setConfirmId(null)}>Cancel</button>
                      </span>
                    ) : (
                      <button className="btn btn-ghost btn-sm" aria-label={`Roll back to v${r.version}`}
                        onClick={() => { setErr(""); setConfirmId(r.id) }}>Roll back</button>
                    ))}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** SDK base URLs for the provider surfaces this profile's targets expose. */
export function gatewayUrls(profile: GatewayProfileV2Out): string[] {
  // Gateway lives on a different hostname from the dashboard
  // (delegator-gateway service, per #2056/#2066). Do not derive the
  // URL from window.location.origin. Local dev can point at
  // http://localhost:8000 via NEXT_PUBLIC_GATEWAY_URL.
  const origin = (process.env.NEXT_PUBLIC_GATEWAY_URL || "https://gateway.conductai.ai").replace(/\/$/, "")
  const wc = (profile.working_copy as {
    targets?: Array<{ transport?: string; provider?: string }>
  } | null | undefined) ?? {}
  const surfaces = new Set<string>()
  for (const t of wc.targets ?? []) {
    // Passthrough routes speak OpenAI Chat Completions today.
    if (t.transport === "http_passthrough") surfaces.add("openai")
    else if (t.provider === "anthropic" || t.provider === "openai") surfaces.add(t.provider)
  }
  // The OpenAI SDK appends ``/chat/completions`` so its base needs ``/v1``;
  // the Anthropic SDK appends ``/v1/messages`` itself.
  const sdkBase = (p: string) => `${origin}/gateway/v1/${p}${p === "openai" ? "/v1" : ""}`
  return surfaces.size === 0 ? [sdkBase("anthropic"), sdkBase("openai")] : [...surfaces].map(sdkBase)
}

export function HowToUse({ profile }: { profile: GatewayProfileV2Out }) {
  const identifier = conditIdentifier(profile)
  const urls = gatewayUrls(profile)
  return (
    <div className="card card-pad" style={{ background: "var(--surface-2)" }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>How to use this profile</div>
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", rowGap: 8, columnGap: 12, alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "var(--text-2)" }}>Profile identifier</span>
        <code className="mono" style={{ fontSize: 12.5, wordBreak: "break-all" }}>{identifier}</code>
        <CopyButton value={identifier} label="Copy profile identifier" />

        <span style={{ fontSize: 12, color: "var(--text-2)" }}>
          Gateway URL{urls.length > 1 ? "s (per SDK)" : ""}
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {urls.map(u => (
            <code key={u} className="mono" style={{ fontSize: 12.5, wordBreak: "break-all" }}>{u}</code>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {urls.map(u => <CopyButton key={u} value={u} label={`Copy ${u}`} />)}
        </div>

        <span style={{ fontSize: 12, color: "var(--text-2)" }}>Auth token</span>
        <span style={{ fontSize: 12.5, color: "var(--text-2)" }}>
          Your workspace member token (or an Agent Identity token).
        </span>
        <a className="btn btn-ghost btn-sm" href="/settings" style={{ height: 26, fontSize: 11.5 }}>Manage</a>
      </div>
      <p style={{ fontSize: 11.5, color: "var(--text-3)", margin: "10px 0 0" }}>
        Point your SDK's base URL at the matching entry above (Anthropic
        SDK → <code className="mono">/gateway/v1/anthropic</code>, OpenAI SDK → <code className="mono">/gateway/v1/openai/v1</code>)
        and set <code className="mono">model:</code> to the profile identifier.
      </p>
    </div>
  )
}
