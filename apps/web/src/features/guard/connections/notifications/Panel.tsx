"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard, environments as environmentsApi, credentials } from "@/lib/api"

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
  channel_ref: string
  enabled: boolean
}

interface NotifGroup { action: string; channels: NotifChannel[] }

function NotificationsCard({
  workspaceId,
  isAdmin,
}: {
  workspaceId: string | null
  isAdmin: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [groups, setGroups] = useState<NotifGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addingAction, setAddingAction] = useState<string | null>(null)
  const [addMenuFor, setAddMenuFor] = useState<string | null>(null)
  const [addType, setAddType] = useState<"slack" | "webhook" | "pagerduty" | "email">("slack")
  const [addChannel, setAddChannel] = useState("")
  const [selectedEnvId, setSelectedEnvId] = useState<string>("")
  const [environments, setEnvironments] = useState<Array<{ id: string; name: string }>>([])
  const [slackIntegrations, setSlackIntegrations] = useState<Array<{ id: string; handle: string; environment_id: string | null; environment_name: string | null }>>([])
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; err: string | null }>>({})

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const [data, envList, integList] = await Promise.all([
        guard.notifications.list(authFetch, workspaceId),
        environmentsApi.list(authFetch).catch(() => []),
        credentials.slack.integration(authFetch, workspaceId).catch(() => []),
      ])
      setGroups(data.groups as NotifGroup[])
      const envs = Array.isArray(envList) ? envList : []
      setEnvironments(envs)
      const integs = Array.isArray(integList) ? integList : (integList ? [integList] : [])
      setSlackIntegrations(integs)
      // Panel-level env: seed once from the first env if user hasn't picked yet.
      setSelectedEnvId(prev => prev || envs[0]?.id || "")
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notifications")
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => { void load() }, [load])

  async function handleAdd(action: NotifActionKey) {
    if (!workspaceId || !addChannel.trim()) return
    try {
      let body: {
        action: typeof action
        channel_type: "slack" | "webhook" | "pagerduty" | "email"
        channel_ref: string
        integration_id: string | null
      }
      if (addType === "webhook" || addType === "pagerduty" || addType === "email") {
        body = {
          action,
          channel_type: addType,
          channel_ref: addChannel.trim(),
          integration_id: null,
        }
      } else {
        // Environment → Slack integration lookup: uses the panel-level env picker.
        const integ = selectedEnvId
          ? (slackIntegrations.find(i => i.environment_id === selectedEnvId) ?? null)
          : (slackIntegrations[0] ?? null)
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
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Notifications</div>
        {environments.length > 0 && (
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)" }}>
            Vault
            <select
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
          </label>
        )}
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
                const chIntegId = (ch as { integration_id?: string | null }).integration_id
                const integ = chIntegId ? slackIntegrations.find(i => i.id === chIntegId) : null
                const envLabel = integ?.environment_name ?? (integ ? "(default env)" : null)
                const isSlack = ch.channel_type === "slack"
                const isPd = ch.channel_type === "pagerduty"
                const displayRef =
                  isSlack ? `#${ch.channel_ref}` :
                  isPd    ? `${ch.channel_ref.slice(0, 6)}…${ch.channel_ref.slice(-4)}` :
                  ch.channel_ref
                return (
                <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 12.5 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".04em", color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: 4, padding: "1px 6px", textTransform: "uppercase" }}>
                    {ch.channel_type}
                  </span>
                  <span style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)", color: "var(--text)", flex: 1, wordBreak: "break-all" }}>
                    {displayRef}
                    {isSlack && envLabel && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: "var(--text-muted)", fontFamily: "inherit" }}>· {envLabel}</span>
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
                  {addType === "slack" && <span style={{ color: "var(--text-3)", fontSize: 12 }}>#</span>}
                  <input
                    autoFocus
                    value={addChannel}
                    onChange={e => setAddChannel(addType === "slack" ? e.target.value.replace(/^#+/, "") : e.target.value)}
                    placeholder={
                      addType === "slack"     ? "compliance-hipaa" :
                      addType === "email"     ? "oncall@company.com" :
                      addType === "pagerduty" ? "PagerDuty routing key (32-char integration key)" :
                      "https://example.com/hooks/guard"
                    }
                    type={addType === "email" ? "email" : "text"}
                    style={{ flex: 1, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12.5, fontFamily: (addType === "webhook" || addType === "pagerduty") ? "var(--font-mono, ui-monospace, monospace)" : undefined }}
                    onKeyDown={e => { if (e.key === "Enter") void handleAdd(a.k); if (e.key === "Escape") { setAddingAction(null); setAddChannel("") } }}
                  />
                  <button
                    type="button"
                    disabled={(addType === "slack" && environments.length === 0) || !addChannel.trim()}
                    onClick={() => void handleAdd(a.k)}
                    className="btn btn-primary btn-sm"
                    style={{ fontSize: 11, opacity: (addType === "slack" && environments.length === 0) || !addChannel.trim() ? 0.5 : 1 }}
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
}: {
  workspaceId: string | null
  isAdmin: boolean
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <NotificationsCard workspaceId={workspaceId} isAdmin={isAdmin} />
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
          <a href="/settings/environments" style={{ color: "var(--info)", textDecoration: "underline" }}>
            Add them in Settings &rarr; Vault
          </a>
          .
        </p>
      </div>
    </div>
  )
}
