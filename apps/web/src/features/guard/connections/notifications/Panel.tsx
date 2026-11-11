"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard, environments as environmentsApi, credentials } from "@/lib/api"
import AlertsCard, { parseSourceFilter } from "./AlertsCard"
import VaultEntryPicker from "./VaultEntryPicker"
import {
  channelVaultLabel, EMPTY_VAULT_ENTRIES, entriesForEnv, slackIntegrationFor,
  type SlackIntegration, type VaultEntries, type VaultEntry, type VaultEnvironment,
} from "./vault"

// ─── #1142 Phase 1 — per-action notifications card ────────────────────────────

type NotifActionKey = "block" | "warn" | "audit" | "approval" | "fail_open" | "drift"
const NOTIF_ACTIONS: Array<{ k: NotifActionKey; label: string; hint: string }> = [
  { k: "block",     label: "Block",     hint: "loud by default — send to a security channel" },
  { k: "warn",      label: "Warn",      hint: "quiet — a heads-up to a dev channel" },
  { k: "audit",     label: "Audit",     hint: "silent by default — leave empty to skip" },
  { k: "approval",  label: "Approval",  hint: "notify approvers when a rule requires human sign-off" },
  { k: "fail_open", label: "Fail-open", hint: "customer heads-up when Guard could not evaluate policy (allowed through per your default)" },
  { k: "drift",     label: "Drift",     hint: "token usage anomalies detected against your guardrails" },
]

interface NotifChannel {
  id: string
  action: NotifActionKey
  channel_type: string
  integration_id?: string | null
  channel_ref: string
  environment_name?: string | null
  vault_handle?: string | null
  legacy_ref?: boolean
  enabled: boolean
}

interface NotifGroup { action: string; channels: NotifChannel[] }

function NotificationsCard({
  workspaceId,
  isAdmin,
  environments,
  slackIntegrations,
  vaultEntries = EMPTY_VAULT_ENTRIES,
  selectedEnvId,
}: {
  workspaceId: string | null
  isAdmin: boolean
  environments: VaultEnvironment[]
  slackIntegrations: SlackIntegration[]
  vaultEntries?: VaultEntries
  selectedEnvId: string
}) {
  const { authFetch } = useAuthFetch()
  const [groups, setGroups] = useState<NotifGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addingAction, setAddingAction] = useState<string | null>(null)
  const [addMenuFor, setAddMenuFor] = useState<string | null>(null)
  const [addType, setAddType] = useState<"slack" | "webhook" | "pagerduty" | "email">("slack")
  const [addChannel, setAddChannel] = useState("")
  const [addEntryId, setAddEntryId] = useState("")
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; err: string | null }>>({})

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const data = await guard.notifications.list(authFetch, workspaceId)
      setGroups(data.groups as NotifGroup[])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notifications")
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => { void load() }, [load])

  // PagerDuty/Webhook/Email pick a Vault entry from the selected Vault; email
  // may fall back to the workspace credential (no entry).
  const vaultType = addType === "slack" ? null : addType
  const entryOptions: VaultEntry[] = vaultType ? entriesForEnv(vaultEntries[vaultType], selectedEnvId) : []
  const pickedEntry = vaultType
    ? (entryOptions.find(e => e.id === addEntryId)?.id ?? (vaultType === "email" ? "" : (entryOptions[0]?.id ?? "")))
    : ""
  const canSave = addType === "slack"
    ? environments.length > 0 && !!addChannel.trim()
    : addType === "email" ? !!addChannel.trim() : !!pickedEntry

  async function handleAdd(action: NotifActionKey) {
    if (!workspaceId || !canSave) return
    try {
      let body: {
        action: typeof action
        channel_type: "slack" | "webhook" | "pagerduty" | "email"
        channel_ref: string
        integration_id: string | null
      }
      if (addType === "email") {
        body = { action, channel_type: "email", channel_ref: addChannel.trim(), integration_id: pickedEntry || null }
      } else if (addType === "webhook" || addType === "pagerduty") {
        // The secret lives in the Vault entry; the channel only references it.
        body = { action, channel_type: addType, channel_ref: "", integration_id: pickedEntry }
      } else {
        // Environment → Slack integration lookup: uses the panel-level Vault picker.
        const integ = slackIntegrationFor(slackIntegrations, selectedEnvId)
        body = {
          action,
          channel_type: "slack",
          channel_ref: addChannel.trim().replace(/^#+/, ""),
          integration_id: integ?.id ?? null,
        }
      }
      await guard.notifications.create(authFetch, workspaceId, body)
      setAddingAction(null)
      setAddChannel("")
      setAddEntryId("")
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add channel")
    }
  }

  async function handleRemove(id: string) {
    if (!workspaceId) return
    try {
      await guard.notifications.remove(authFetch, id, workspaceId)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove channel")
    }
  }

  async function handleTest(id: string) {
    if (!workspaceId) return
    try {
      const res = await guard.notifications.test(authFetch, id, workspaceId)
      setTestResult(prev => ({ ...prev, [id]: { ok: res.ok, err: res.error } }))
      setTimeout(() => setTestResult(prev => { const { [id]: _drop, ...rest } = prev; return rest }), 4000)
    } catch (e) {
      setTestResult(prev => ({ ...prev, [id]: { ok: false, err: e instanceof Error ? e.message : "Test failed" } }))
    }
  }

  if (loading) return <div className="card" style={{ padding: 20, fontSize: 12, color: "var(--text-muted)" }}>Loading notifications…</div>
  if (error)   return <div className="card" style={{ padding: 20, fontSize: 12, color: "var(--err)" }}>{error}</div>

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, background: "#7c3aed", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <path d="M14.5 2v20M9.5 2v20M2 14.5h20M2 9.5h20" />
          </svg>
        </span>
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Guard rules</div>
      </div>

      <div style={{ padding: "4px 20px 16px" }}>
        {NOTIF_ACTIONS.map((a, i) => {
          const group = groups.find(g => g.action === a.k)
          const channels = group?.channels ?? []
          return (
            <div key={a.k} style={{ padding: "13px 0", borderTop: i > 0 ? "1px solid var(--border)" : undefined }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>{a.label}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{a.hint}</div>
                </div>
                {isAdmin && addingAction !== a.k && (
                  <div style={{ position: "relative" }}>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setAddMenuFor(prev => prev === a.k ? null : a.k)}
                    >
                      + Add channel ▾
                    </button>
                    {addMenuFor === a.k && (
                      <>
                        <div
                          onClick={() => setAddMenuFor(null)}
                          style={{ position: "fixed", inset: 0, zIndex: 10 }}
                        />
                        <div style={{
                          position: "absolute",
                          right: 0,
                          top: "calc(100% + 4px)",
                          zIndex: 20,
                          background: "var(--surface)",
                          border: "1px solid var(--border)",
                          borderRadius: 8,
                          boxShadow: "0 6px 24px rgba(0,0,0,0.08)",
                          padding: 4,
                          minWidth: 160,
                        }}>
                          {([
                            ["slack",     "Slack"],
                            ["email",     "Email"],
                            ["pagerduty", "PagerDuty"],
                            ["webhook",   "Webhook"],
                          ] as const).map(([type, label]) => (
                            <button
                              key={type}
                              type="button"
                              onClick={() => {
                                setAddingAction(a.k)
                                setAddType(type)
                                setAddChannel("")
                                setAddEntryId("")
                                setAddMenuFor(null)
                              }}
                              style={{
                                display: "block",
                                width: "100%",
                                textAlign: "left",
                                padding: "6px 10px",
                                background: "transparent",
                                border: "none",
                                borderRadius: 4,
                                cursor: "pointer",
                                fontSize: 12.5,
                                color: "var(--text)",
                              }}
                              onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>

              {channels.length === 0 && addingAction !== a.k && (
                <div style={{ fontSize: 11.5, color: "var(--text-muted)", padding: "6px 0" }}>
                  (none)
                </div>
              )}

              {channels.map(ch => {
                const entries = vaultEntries[ch.channel_type as keyof VaultEntries] ?? []
                const envLabel = channelVaultLabel(ch, ch.channel_type === "slack" ? slackIntegrations : entries)
                const isSlack = ch.channel_type === "slack"
                // The API masks typed keys/URLs and returns a non-secret label for Vault-backed rows.
                const displayRef = isSlack ? `#${ch.channel_ref}` : (ch.vault_handle ?? ch.channel_ref)
                return (
                <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 12.5 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".04em", color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: 4, padding: "1px 6px", textTransform: "uppercase" }}>
                    {ch.channel_type}
                  </span>
                  <span style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)", color: "var(--text)", flex: 1, wordBreak: "break-all" }}>
                    {displayRef}
                    {envLabel && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: "var(--text-muted)", fontFamily: "inherit" }}>· {envLabel}</span>
                    )}
                    {ch.legacy_ref && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: "var(--warn, #b45309)", fontFamily: "inherit" }}>
                        · Typed key — move to Vault
                      </span>
                    )}
                  </span>
                  {testResult[ch.id] && (
                    <span style={{ fontSize: 11, color: testResult[ch.id].ok ? "var(--ok)" : "var(--err)" }}>
                      {testResult[ch.id].ok ? "sent ✓" : (testResult[ch.id].err ?? "failed")}
                    </span>
                  )}
                  {isAdmin && (
                    <>
                      <button type="button" onClick={() => handleTest(ch.id)} className="btn btn-ghost btn-sm" style={{ padding: "0 8px", fontSize: 11 }}>Test</button>
                      <button type="button" onClick={() => handleRemove(ch.id)} className="btn btn-ghost btn-sm" style={{ padding: "0 8px", fontSize: 11, color: "var(--err)" }}>Remove</button>
                    </>
                  )}
                </div>
                )
              })}

              {addingAction === a.k && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, padding: "6px 8px", background: "var(--surface-2)", borderRadius: 6 }}>
                  {vaultType && (
                    <VaultEntryPicker
                      service={vaultType}
                      entries={vaultEntries[vaultType]}
                      envId={selectedEnvId}
                      value={pickedEntry}
                      onChange={setAddEntryId}
                      optional={vaultType === "email"}
                    />
                  )}
                  {addType === "slack" && <span style={{ color: "var(--text-3)", fontSize: 12 }}>#</span>}
                  {(addType === "slack" || addType === "email") && (
                    <input
                      autoFocus
                      aria-label={addType === "email" ? "Recipient address" : "Slack channel"}
                      value={addChannel}
                      onChange={e => setAddChannel(addType === "slack" ? e.target.value.replace(/^#+/, "") : e.target.value)}
                      placeholder={addType === "slack" ? "compliance-hipaa" : "oncall@company.com"}
                      type={addType === "email" ? "email" : "text"}
                      style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12.5 }}
                      onKeyDown={e => { if (e.key === "Enter") void handleAdd(a.k); if (e.key === "Escape") { setAddingAction(null); setAddChannel("") } }}
                    />
                  )}
                  <button
                    type="button"
                    disabled={!canSave}
                    onClick={() => void handleAdd(a.k)}
                    className="btn btn-primary btn-sm"
                    style={{ fontSize: 11, opacity: canSave ? 1 : 0.5 }}
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    onClick={() => { setAddingAction(null); setAddChannel("") }}
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11 }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function NotificationsPanel({
  workspaceId,
  isAdmin,
  source = null,
}: {
  workspaceId: string | null
  isAdmin: boolean
  /** `?source=` filter, e.g. `gateway:<profile_id>`. */
  source?: string | null
}) {
  const { authFetch } = useAuthFetch()
  const filter = useMemo(() => parseSourceFilter(source), [source])
  const showGuardRules = !filter || filter.sourceType === "guard"
  const showAlerts = filter?.sourceType !== "guard"

  // One Vault (environment) selection drives the Slack credential for both
  // Guard-rule channels and alert channels.
  const [environments, setEnvironments] = useState<VaultEnvironment[]>([])
  const [slackIntegrations, setSlackIntegrations] = useState<SlackIntegration[]>([])
  const [vaultEntries, setVaultEntries] = useState<VaultEntries>(EMPTY_VAULT_ENTRIES)
  const [selectedEnvId, setSelectedEnvId] = useState("")

  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    void Promise.all([
      environmentsApi.list(authFetch).catch(() => []),
      credentials.slack.integration(authFetch, workspaceId).catch(() => []),
      credentials.channelEntries(authFetch, workspaceId, "pagerduty").catch(() => []),
      credentials.channelEntries(authFetch, workspaceId, "webhook").catch(() => []),
      credentials.channelEntries(authFetch, workspaceId, "email").catch(() => []),
    ]).then(([envList, integList, pd, wh, em]) => {
      if (cancelled) return
      const envs = Array.isArray(envList) ? envList : []
      setEnvironments(envs)
      const slack = Array.isArray(integList) ? integList : (integList ? [integList] : [])
      setSlackIntegrations(slack)
      setVaultEntries({ slack, pagerduty: Array.isArray(pd) ? pd : [], webhook: Array.isArray(wh) ? wh : [], email: Array.isArray(em) ? em : [] })
      setSelectedEnvId(prev => prev || envs[0]?.id || "")
    })
    return () => { cancelled = true }
  }, [authFetch, workspaceId])

  const vault = { environments, slackIntegrations, vaultEntries, selectedEnvId }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {environments.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-3)" }}>
          <label htmlFor="notif-vault" style={{ fontWeight: 600 }}>Vault</label>
          <select
            id="notif-vault"
            value={selectedEnvId}
            onChange={e => setSelectedEnvId(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "3px 8px", fontSize: 12.5, color: "var(--text)" }}
          >
            {environments.map(env => {
              const hasSlack = slackIntegrations.some(i => i.environment_id === env.id)
              return (
                <option key={env.id} value={env.id}>
                  {env.name}{hasSlack ? "" : " — (no Slack)"}
                </option>
              )
            })}
          </select>
          <span>Credentials (Slack, PagerDuty, webhook, email) for new channels in both Guard rules and Alerts.</span>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: showGuardRules && showAlerts ? "repeat(auto-fit, minmax(420px, 1fr))" : "1fr", gap: 20, alignItems: "start" }}>
        {showGuardRules && <NotificationsCard workspaceId={workspaceId} isAdmin={isAdmin} {...vault} />}
        {showAlerts && <AlertsCard workspaceId={workspaceId} isAdmin={isAdmin} filter={filter} {...vault} />}
      </div>
      <div style={{ background: "var(--info-bg)", border: "1px solid var(--info-bd)", borderRadius: 12, padding: "14px 18px" }}>
        <p style={{ fontSize: 12, fontWeight: 600, color: "var(--info)", marginBottom: 6 }}>Setup checklist</p>
        <p style={{ fontSize: 12, color: "var(--info)", marginBottom: 4 }}>
          Invite the Conduct AI Slack bot to each channel:{" "}
          <code style={{ background: "rgba(37,99,235,.12)", padding: "1px 5px", borderRadius: 4, fontFamily: "ui-monospace,monospace" }}>
            /invite @ConductAI
          </code>
        </p>
        <p style={{ fontSize: 12, color: "var(--info)" }}>
          No Slack credentials yet?{" "}
          <a href="/settings?tab=credentials" style={{ color: "var(--info)", textDecoration: "underline" }}>
            Add them in Settings &rarr; Vault
          </a>
          .
        </p>
      </div>
    </div>
  )
}
