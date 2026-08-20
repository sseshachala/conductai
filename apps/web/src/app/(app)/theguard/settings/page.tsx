"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard, environments as environmentsApi, credentials } from "@/lib/api"
import { API } from "@/lib/api/client"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useTokenGuardrails, patchTokenGuardrails } from "@/hooks/useTokenGuardrails"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { SlackIntegrationPicker } from "@/components/SlackIntegrationPicker"

// ─── Types ────────────────────────────────────────────────────────────────────

interface TeamPrefs {
  alert_channel: string | null
  alert_slack_integration_id: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
  automation_security_scan: boolean
  automation_workflow_trigger: boolean
  deny_on_error: boolean
  advisory_mode: boolean
}


// ─── Section header (reused across all groupings) ─────────────────────────────

function SectionHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div style={{ margin: "28px 0 12px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>
        {title}
      </div>
      {hint && <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{hint}</div>}
    </div>
  )
}



// ─── #1142 Phase 1 — per-action notifications card ────────────────────────────

const NOTIF_ACTIONS: Array<{ k: "block" | "warn" | "audit" | "approval"; label: string; hint: string }> = [
  { k: "block",    label: "Block",    hint: "loud by default — send to a security channel" },
  { k: "warn",     label: "Warn",     hint: "quiet — a heads-up to a dev channel" },
  { k: "audit",    label: "Audit",    hint: "silent by default — leave empty to skip" },
  { k: "approval", label: "Approval", hint: "notify approvers when a rule requires human sign-off" },
]

interface NotifChannel {
  id: string
  action: "block" | "warn" | "audit" | "approval"
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

  async function handleAdd(action: "block" | "warn" | "audit" | "approval") {
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
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Slack channels by action</div>
        {environments.length > 0 && (
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)" }}>
            Environment
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


// ─── Toggle ───────────────────────────────────────────────────────────────────

function GuardToggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <span
      onClick={disabled ? undefined : onClick}
      role="switch"
      aria-checked={on}
      aria-disabled={disabled}
      style={{
        width: 40,
        height: 23,
        borderRadius: 20,
        background: on ? "var(--accent)" : "var(--border-2)",
        position: "relative",
        cursor: disabled ? "default" : "pointer",
        flexShrink: 0,
        transition: "background .15s",
        display: "inline-block",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2.5,
          left: on ? 19.5 : 2.5,
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "#fff",
          transition: "left .15s",
          boxShadow: "var(--shadow-sm)",
        }}
      />
    </span>
  )
}

// ─── #980 Rate Limits — workspace default RPM/TPM ─────────────────────────────
// ponytail: workspace default only in V1. Per-agent overrides land when the
// agent identity picker ships (backend already accepts agent_identity_id).

function RateLimitsCard({ isAdmin }: { isAdmin: boolean }) {
  const { authFetch } = useAuthFetch()
  const [rpm, setRpm] = useState<string>("")
  const [tpm, setTpm] = useState<string>("")
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [overrideCount, setOverrideCount] = useState(0)

  useEffect(() => {
    if (!isAdmin) return  // GET requires admin; skip fetch for viewers/developers
    let cancelled = false
    guard.rateLimits.list(authFetch).then((rows) => {
      if (cancelled) return
      const def = rows.find(r => !r.agent_identity_id)
      setRpm(def?.rpm != null ? String(def.rpm) : "")
      setTpm(def?.tpm != null ? String(def.tpm) : "")
      setOverrideCount(rows.filter(r => r.agent_identity_id).length)
      setLoaded(true)
    }).catch(() => setLoaded(true))
    return () => { cancelled = true }
  }, [authFetch, isAdmin])

  if (!isAdmin) return null

  async function save() {
    setSaving(true); setErr(null); setSaved(false)
    try {
      const body: { agent_identity_id: null; rpm: number | null; tpm: number | null } = {
        agent_identity_id: null,
        rpm: rpm.trim() === "" ? null : Number(rpm),
        tpm: tpm.trim() === "" ? null : Number(tpm),
      }
      await guard.rateLimits.upsert(authFetch, body)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: any) {
      setErr(e?.message || "Save failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card" style={{ overflow: "hidden", marginTop: 20 }}>
      <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
        </span>
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Workspace default</div>
        {saved && <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--ok)", fontWeight: 600 }}>Saved</span>}
      </div>

      <div style={{ padding: "16px 20px", display: "grid", gap: 14 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Leave a field blank to remove that cap. Overrides per-agent identity land soon
          {overrideCount > 0 ? ` — ${overrideCount} override${overrideCount === 1 ? "" : "s"} currently active.` : "."}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Requests / min (RPM)</span>
            <input
              type="number"
              min={1}
              placeholder="unlimited"
              value={rpm}
              onChange={e => setRpm(e.target.value)}
              disabled={!isAdmin || !loaded}
              style={{ padding: "9px 12px", fontSize: 13, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--text)" }}
            />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Tokens / min (TPM)</span>
            <input
              type="number"
              min={1}
              placeholder="unlimited"
              value={tpm}
              onChange={e => setTpm(e.target.value)}
              disabled={!isAdmin || !loaded}
              style={{ padding: "9px 12px", fontSize: 13, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--text)" }}
            />
          </label>
        </div>

        <RateLimitPresets isAdmin={isAdmin} onPick={(r, t) => { setRpm(String(r)); setTpm(String(t)) }} />

        {err && <div style={{ fontSize: 12, color: "var(--danger)" }}>{err}</div>}

        <div>
          <button
            type="button"
            onClick={save}
            disabled={!isAdmin || saving || !loaded}
            className="btn btn-primary btn-sm"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  )
}


// Anthropic Tier 1 defaults for reference: 50 RPM, 40k input TPM.
const RATE_LIMIT_PRESETS: Array<{ label: string; rpm: number; tpm: number; why: string }> = [
  { label: "Solo dev / smoke test",     rpm: 2,   tpm: 500,     why: "trips the cap in a 3-call test — good for verifying enforcement" },
  { label: "Small team, exploratory",   rpm: 60,  tpm: 100000,  why: "~1 req/sec sustained; enough for Cursor / Claude Code chat" },
  { label: "Team of 10-20 devs",        rpm: 300, tpm: 500000,  why: "absorbs bursts, still catches runaway agents" },
]

function RateLimitPresets({ isAdmin, onPick }: { isAdmin: boolean; onPick: (rpm: number, tpm: number) => void }) {
  return (
    <div style={{ border: "1px dashed var(--border)", borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
        Suggested defaults
      </div>
      <div style={{ display: "grid", gap: 6 }}>
        {RATE_LIMIT_PRESETS.map(p => (
          <button
            key={p.label}
            type="button"
            onClick={() => onPick(p.rpm, p.tpm)}
            disabled={!isAdmin}
            style={{
              display: "grid",
              gridTemplateColumns: "160px 60px 80px 1fr",
              gap: 10,
              alignItems: "center",
              padding: "6px 8px",
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 6,
              cursor: isAdmin ? "pointer" : "default",
              textAlign: "left",
              color: "var(--text-2)",
              fontSize: 12.5,
            }}
            onMouseEnter={e => { if (isAdmin) e.currentTarget.style.background = "var(--surface-2)" }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent" }}
            title={isAdmin ? "Apply to fields" : "Admin only"}
          >
            <span style={{ fontWeight: 600, color: "var(--text)" }}>{p.label}</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{p.rpm} rpm</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{p.tpm.toLocaleString()} tpm</span>
            <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>{p.why}</span>
          </button>
        ))}
      </div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 8 }}>
        Per-agent identity gets its own limits once the picker ships. Anthropic Tier 1 default for reference: 50 rpm, 40k tpm.
      </div>
    </div>
  )
}


// ─── Main page ────────────────────────────────────────────────────────────────

export default function GuardSettingsPage() {
  return <AppShell><SettingsContent /></AppShell>
}

function SettingsContent() {
  const { authFetch } = useAuthFetch()
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const router = useRouter()

  useEffect(() => {
    if (resolvedRole !== null && !permissions.canEditSettings) router.replace("/theguard")
  }, [resolvedRole, permissions.canEditSettings, router])

  const [prefs, setPrefs] = useState<TeamPrefs>({
    alert_channel: null,
    alert_slack_integration_id: null,
    notify_on_block: true,
    notify_on_budget: true,
    automation_security_scan: false,
    automation_workflow_trigger: false,
    deny_on_error: true,
    advisory_mode: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)

  // Enforcement mode
  const [enforcementMode, setEnforcementMode] = useState<"block" | "warn" | "audit">("warn")
  const [failMode, setFailMode] = useState<"fail_open" | "fail_closed">("fail_open")
  const [denyOnError, setDenyOnError] = useState(true)
  const [enforcementError, setEnforcementError] = useState<string | null>(null)

  // Re-sync state
  const [resyncing, setResyncing] = useState(false)
  const [resyncDone, setResyncDone] = useState(false)

  // Token guardrails
  const { guardrails: tokenGuardrails, refresh: refreshGuardrails } = useTokenGuardrails(activeWorkspace?.id ?? null)
  const [guardrailState, setGuardrailState] = useState({ prompt_caching: true, model_routing: true, prompt_splitting: true })
  const [guardrailSaved, setGuardrailSaved] = useState(false)

  // Sync status
  const [toolCoverage, setToolCoverage] = useState<Array<{ detected_tools: string[]; mcp_registered: string[]; hook_registered: string[] }> | null>(null)

  // MCP connect

  const wsId = activeWorkspace?.id ?? null
  const isAdmin = permissions.canEditSettings

  const load = useCallback(async () => {
    if (!wsId) return
    setLoading(true)
    setError(null)
    try {
      const data = await guard.config.get(authFetch, wsId)
      setPrefs({
        alert_channel: data.alert_channel ?? null,
        alert_slack_integration_id: data.alert_slack_integration_id ?? null,
        notify_on_block: data.notify_on_block ?? true,
        notify_on_budget: data.notify_on_budget ?? true,
        automation_security_scan: data.automation_security_scan ?? false,
        automation_workflow_trigger: data.automation_workflow_trigger ?? false,
        deny_on_error: data.deny_on_error ?? true,
        advisory_mode: data.advisory_mode ?? false,
      })
      if (data.enforcement_mode) setEnforcementMode(data.enforcement_mode as "block" | "warn" | "audit")
      if (data.fail_mode) setFailMode(data.fail_mode as "fail_open" | "fail_closed")
      if (data.deny_on_error !== undefined) setDenyOnError(data.deny_on_error)
      setLastFetched(new Date())
      // Load sync coverage in parallel — non-fatal
      guard.developerTools.list(authFetch, wsId)
        .then(d => { if (d) setToolCoverage(d) })
        .catch(() => {})
    } catch (e: any) {
      if (e?.message?.includes("404") || String(e).includes("404")) { setLoading(false); return }
      setError(e instanceof Error ? e.message : "Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [authFetch, wsId])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!tokenGuardrails) return
    setGuardrailState({
      prompt_caching:   tokenGuardrails.prompt_caching,
      model_routing:    tokenGuardrails.model_routing,
      prompt_splitting: tokenGuardrails.prompt_splitting,
    })
  }, [tokenGuardrails])

  async function patchConfig(body: Partial<TeamPrefs>) {
    if (!wsId) return
    const res = await guard.config.patch(authFetch, wsId, body as Record<string, unknown>)
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
    return res.json()
  }

  async function handleResync() {
    if (!wsId || resyncing) return
    setResyncing(true)
    setResyncDone(false)
    try {
      const res = await guard.config.resync(authFetch, wsId)
      if (!res.ok) throw new Error(`Resync failed (${res.status})`)
      setResyncDone(true)
      setTimeout(() => setResyncDone(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resync failed")
    } finally {
      setResyncing(false)
    }
  }


  async function handleToggle(field: "notify_on_block" | "notify_on_budget", value: boolean) {
    setPrefs(p => ({ ...p, [field]: value }))
    try {
      await patchConfig({ [field]: value })
    } catch (e) {
      setPrefs(p => ({ ...p, [field]: !value }))
      setError(e instanceof Error ? e.message : "Save failed")
    }
  }

  async function handleGuardrailToggle(field: "prompt_caching" | "model_routing" | "prompt_splitting", value: boolean) {
    if (!wsId) return
    setGuardrailState(s => ({ ...s, [field]: value }))
    try {
      const token = await getToken()
      await patchTokenGuardrails(wsId, token ?? "", API, { [field]: value })
      refreshGuardrails()
      setGuardrailSaved(true)
      setTimeout(() => setGuardrailSaved(false), 2000)
    } catch {
      setGuardrailState(s => ({ ...s, [field]: !value }))
    }
  }

  const NOTIFS = [
    { k: "blocks",  t: "Policy blocks",          d: "Notify the channel when a tool call is blocked by a rule.", locked: false },
    { k: "warns",   t: "Policy warnings",         d: "Warn-mode matches share the Policy blocks toggle above — turn that off to silence both.", locked: true },
    { k: "budget",  t: "Budget threshold alerts", d: "Fire when team or a developer crosses the alert threshold.", locked: false },
  ]

  function getNotifValue(k: string): boolean {
    if (k === "blocks") return prefs.notify_on_block
    if (k === "budget") return prefs.notify_on_budget
    if (k === "warns")  return prefs.notify_on_block
    return false
  }

  function toggleNotif(k: string) {
    if (k === "blocks") handleToggle("notify_on_block", !prefs.notify_on_block)
    else if (k === "budget") handleToggle("notify_on_budget", !prefs.notify_on_budget)
  }

  const isSlackConnected = prefs.alert_slack_integration_id != null

  return (
    <GuardShell lastFetched={lastFetched}>
      {loading ? (
        <div style={{ textAlign: "center", padding: "40px 0", fontSize: 13, color: "var(--text-muted)" }}>
          Loading settings…
        </div>
      ) : error ? (
        <div style={{
          borderRadius: 12,
          border: "1px solid var(--err-bd)",
          background: "var(--err-bg)",
          padding: "12px 16px",
          fontSize: 13,
          color: "var(--err)",
          marginBottom: 16,
        }}>
          {error}
        </div>
      ) : (
        <>
          {/* View-only notice */}
          {!isAdmin && resolvedRole !== null && (
            <div style={{
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              padding: "10px 16px",
              fontSize: 12,
              color: "var(--text-3)",
              marginBottom: 24,
            }}>
              View only — contact your admin to make changes.
            </div>
          )}

          {/* Status ribbon — sync + resync side by side */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 12 }}>Sync status</div>
                {toolCoverage === null ? (
                  <div style={{ height: 40 }} />
                ) : (() => {
                  const total = toolCoverage.length
                  const synced = toolCoverage.filter(dev =>
                    dev.detected_tools.every(t =>
                      dev.mcp_registered.includes(t) || dev.hook_registered.includes(t)
                    )
                  ).length
                  const allGood = total === 0 || synced === total
                  return (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                        <span style={{ fontSize: 26, fontWeight: 700, color: allGood ? "var(--ok)" : "var(--warn)" }}>
                          {total === 0 ? "—" : `${synced}/${total}`}
                        </span>
                        <span style={{ fontSize: 13, color: "var(--text-3)" }}>machines in sync</span>
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>
                        Policies propagate within <strong style={{ color: "var(--text-2)" }}>60s</strong> of a change.
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 14, fontSize: 12.5, color: allGood ? "var(--ok)" : "var(--warn)" }}>
                        <span className="conduct-pulse-dot" style={{ background: allGood ? "var(--ok)" : "var(--warn)" }} />
                        {total === 0 ? "No developers connected yet" : allGood ? "All developers up to date" : `${total - synced} developer${total - synced !== 1 ? "s" : ""} need sync — run: conduct guard sync`}
                      </div>
                    </>
                  )
                })()}
              </div>
              <div className="card" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 12 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 4v6h-6M1 20v-6h6" />
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                </svg>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>Re-sync all machines</div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Force a policy push now</div>
                </div>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!isAdmin || resyncing}
                  style={{ opacity: isAdmin ? 1 : 0.5 }}
                  onClick={handleResync}
                >
                  {resyncing ? "Syncing…" : resyncDone ? "Synced" : "Re-sync"}
                </button>
              </div>
          </div>

          <SectionHeader title="Enforcement" hint="How Guard decides and when it fails safely" />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 20, alignItems: "stretch" }}>
              <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4, gap: 8 }}>
                  <div className="eyebrow">Agent guard <span style={{ color: "var(--text-muted)", fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>· workspace default</span></div>
                  <a href="/playbooks" style={{ fontSize: 12, color: "var(--text-3)", textDecoration: "none", whiteSpace: "nowrap" }}>Learn more →</a>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>Applied to playbook runs (brain / tool / output blocks).</div>
                {enforcementError && (
                  <div style={{ fontSize: 12, color: "var(--err)", background: "var(--err-bg)", border: "1px solid var(--err-bd)", borderRadius: 6, padding: "6px 10px", marginBottom: 10 }}>
                    {enforcementError}
                  </div>
                )}
                {([
                  ["block", "Block",      "Run halts — the AI step never executes"],
                  ["warn",  "Warn",       "Flagged in the run trace, step proceeds"],
                  ["audit", "Audit only", "Recorded silently, no visible interruption"],
                ] as const).map(([k, t, d], i) => (
                  <label
                    key={k}
                    style={{
                      display: "flex",
                      gap: 11,
                      padding: "10px 0",
                      borderTop: i > 0 ? "1px solid var(--border)" : "none",
                      cursor: isAdmin ? "pointer" : "default",
                      alignItems: "flex-start",
                    }}
                  >
                    <span
                      onClick={async () => {
                        if (!isAdmin || enforcementMode === k) return
                        const prev = enforcementMode
                        setEnforcementMode(k)
                        setEnforcementError(null)
                        try {
                          await patchConfig({ enforcement_mode: k } as never)
                        } catch (e) {
                          setEnforcementMode(prev)
                          setEnforcementError(e instanceof Error ? e.message : "Failed to save enforcement mode")
                        }
                      }}
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: "50%",
                        border: `2px solid ${enforcementMode === k ? "var(--accent)" : "var(--border-2)"}`,
                        display: "grid",
                        placeItems: "center",
                        marginTop: 2,
                        flexShrink: 0,
                        cursor: isAdmin ? "pointer" : "default",
                      }}
                    >
                      {enforcementMode === k && (
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" }} />
                      )}
                    </span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{t}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{d}</div>
                    </div>
                  </label>
                ))}
              </div>
              <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Outage behavior</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                  What the CLI hook does when it can&apos;t reach Guard. Applies to conduct-cli hook calls only.
                </div>
                {([
                  ["fail_open",   "Fail open",   "Tool calls proceed when Guard is unreachable. Recommended for most teams — keeps developers productive when our infra hiccups."],
                  ["fail_closed", "Fail-Closed Mode", "Tool calls are blocked with rule_id=guard-unavailable until Guard responds. Use for regulated workloads where missing a policy check is worse than a paused build."],
                ] as const).map(([k, t, d], i) => (
                  <label
                    key={k}
                    style={{
                      display: "flex",
                      gap: 11,
                      padding: "10px 0",
                      borderTop: i > 0 ? "1px solid var(--border)" : "none",
                      cursor: isAdmin ? "pointer" : "default",
                      alignItems: "flex-start",
                    }}
                  >
                    <span
                      onClick={async () => {
                        if (!isAdmin || failMode === k) return
                        const prev = failMode
                        setFailMode(k)
                        try {
                          await patchConfig({ fail_mode: k } as never)
                        } catch {
                          setFailMode(prev)
                        }
                      }}
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: "50%",
                        border: `2px solid ${failMode === k ? "var(--accent)" : "var(--border-2)"}`,
                        display: "grid",
                        placeItems: "center",
                        marginTop: 2,
                        flexShrink: 0,
                        cursor: isAdmin ? "pointer" : "default",
                      }}
                    >
                      {failMode === k && (
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" }} />
                      )}
                    </span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{t}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{d}</div>
                    </div>
                  </label>
                ))}
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, lineHeight: 1.5 }}>
                  Change takes effect on each machine the next time <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "0 4px", borderRadius: 3 }}>conduct guard sync</code> runs (≤60s for active CLI sessions).
                </div>
              </div>
              <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Policy error behavior</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                  What Guard does if policy evaluation throws. Applies across proxy, MCP, and playbook runtime.
                </div>
                <label style={{ display: "flex", gap: 11, alignItems: "flex-start", cursor: isAdmin ? "pointer" : "default" }}
                  onClick={async () => {
                    if (!isAdmin) return
                    const next = !denyOnError
                    setDenyOnError(next)
                    try { await patchConfig({ deny_on_error: next } as never) }
                    catch { setDenyOnError(!next) }
                  }}>
                  <GuardToggle on={denyOnError} onClick={() => {}} disabled={!isAdmin} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Fail closed on error</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
                      Block the request and write an audit entry if the policy engine throws. Recommended. Disable only if you prefer fail-open during policy engine incidents.
                    </div>
                  </div>
                </label>
              </div>
          </div>

          <SectionHeader title="Notifications" hint="Route policy events per action tier. Add multiple Slack channels — each one gets pinged whenever a rule with that action fires." />
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <NotificationsCard workspaceId={wsId ?? null} isAdmin={isAdmin} />
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
                  Add them in Settings &rarr; Environments
                </a>
                .
              </p>
            </div>
          </div>

          <SectionHeader title="Cost & performance" hint="Token guardrails detected and enforced across your workspace" />
          <div className="card" style={{ overflow: "hidden", marginTop: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
                </svg>
              </span>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>Token guardrails</div>
              <a href="/token-guardrails" target="_blank" style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-3)", textDecoration: "none" }}>
                Learn more →
              </a>
              {guardrailSaved && (
                <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600 }}>Saved</span>
              )}
            </div>

            {/* Detected (auto) status — shown first */}
            <div style={{ padding: "4px 20px 8px" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", padding: "10px 0 4px" }}>Detected</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Passive detection from installed tools and active policies. Full enforcement coming in a future release.</div>
              {tokenGuardrails === null ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {[...Array(4)].map((_, i) => (
                    <div key={i} style={{ height: 36, background: "var(--surface-2)", borderRadius: 6, opacity: 0.6 }} />
                  ))}
                </div>
              ) : (
                ([
                  { key: "deterministic_offload", label: "Deterministic offload", desc: "Detects whether the warn-deterministic-compute policy is active. In-sandbox offloading coming soon." },
                  { key: "output_compression",    label: "Output compression",    desc: "Detects RTK install. RTK compresses terminal output today — sandbox run compression coming soon." },
                  { key: "structured_retrieval",  label: "Structured retrieval",  desc: "Detects Agent Booster install. Smart file reads inside sandbox runs coming soon." },
                  { key: "metrics_budgets",       label: "Metrics & budgets",     desc: "Spend budgets enforced on proxy traffic. Workflow run budget enforcement coming soon." },
                ] as const).map((item, i) => {
                  const detected = tokenGuardrails[item.key] ?? false
                  return (
                    <div key={item.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0", borderTop: i > 0 ? "1px solid var(--border)" : undefined }}>
                      <div>
                        <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>{item.label}</div>
                        <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{item.desc}</div>
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 600, color: detected ? "var(--ok)" : "var(--text-3)", flexShrink: 0, marginLeft: 12 }}>
                        {detected ? "Detected" : "Not detected"}
                      </span>
                    </div>
                  )
                })
              )}
            </div>

            {/* Manual toggles — shown below Detected */}
            <div style={{ padding: "4px 20px 16px", borderTop: "1px solid var(--border)" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", padding: "10px 0 4px" }}>Toggleable</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Workspace-wide controls — flip off to opt the whole team out.</div>
              {([
                { key: "prompt_caching",   label: "Prompt caching",   desc: "System prompts cached on every agent run — repeat calls don't re-pay for the same tokens. Enforced.", pending: false },
                { key: "model_routing",    label: "Model routing",    desc: "Each run routes to the cheapest model tier that can handle the task — Haiku for simple, Opus for complex. Enforced.", pending: false },
                { key: "prompt_splitting", label: "Prompt splitting", desc: "Split large prompts into chunks to stay within context limits. Not yet implemented.", pending: true },
              ] as const).map(item => (
                <div key={item.key} style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
                      {item.label}
                      {item.pending && (
                        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: ".04em", color: "#92400e", background: "#fef3c7", borderRadius: 4, padding: "1px 5px" }}>PENDING</span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{item.desc}</div>
                  </div>
                  <GuardToggle
                    on={guardrailState[item.key]}
                    onClick={() => handleGuardrailToggle(item.key, !guardrailState[item.key])}
                    disabled={!isAdmin || item.pending}
                  />
                </div>
              ))}
            </div>
          </div>

          {isAdmin && (
            <>
              <SectionHeader title="Rate Limits" hint="Requests-per-minute and tokens-per-minute caps on proxy traffic. Blocks return 429 with x-guard reason." />
              <RateLimitsCard isAdmin={isAdmin} />
            </>
          )}

          <SectionHeader title="Connections" hint="MCP servers and integrations" />
          <div className="card" style={{ marginTop: 20, padding: "14px 20px", display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
              </svg>
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>MCP servers</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Conduct AI Guard is enabled by default. Connect Claude.ai, Desktop, or Work from the MCP servers page.</div>
            </div>
            <a href="/integrations" className="btn btn-ghost btn-sm" style={{ textDecoration: "none" }}>
              Manage MCP →
            </a>
          </div>

          {/* Automation — hidden until operation cleanup complete */}
        </>
      )}
    </GuardShell>
  )
}
