"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useTokenGuardrails, patchTokenGuardrails } from "@/hooks/useTokenGuardrails"
import AppShell from "@/components/AppShell"
import { SlackIntegrationPicker } from "@/components/SlackIntegrationPicker"

// ─── Types ────────────────────────────────────────────────────────────────────

interface TeamPrefs {
  alert_channel: string | null
  alert_slack_integration_id: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
  automation_security_scan: boolean
  automation_workflow_trigger: boolean
}

// ─── Guard Shell ──────────────────────────────────────────────────────────────

const GUARD_TABS = [
  { href: "/guard",             label: "Overview"    },
  { href: "/guard/spend",       label: "Spend"       },
  { href: "/guard/policies",    label: "Policies"    },
  { href: "/guard/activity",    label: "Activity"    },
  { href: "/guard/session-reports", label: "Session Reports" },
  { href: "/guard/team-memory",     label: "Team Memory"     },
  { href: "/guard/settings",        label: "Settings"        },
]

function GuardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
              Guard
            </h1>
            <span className="sbadge ok" style={{ marginTop: 2 }}>
              <span className="conduct-pulse-dot" />
              live
            </span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
            MDM for AI coding tools — policies and spend limits enforced on every Claude Code, Codex, and Cursor call.
          </p>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
          last updated: just now
        </div>
      </div>
      <div className="guard-tab-nav">
        {GUARD_TABS.map(tab => {
          const isActive = tab.href === "/guard"
            ? pathname === "/guard"
            : pathname?.startsWith(tab.href)
          return (
            <Link key={tab.href} href={tab.href} className={`guard-tab${isActive ? " active" : ""}`}>
              {tab.label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}

// ─── Toggle ───────────────────────────────────────────────────────────────────

function GuardToggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <span
      onClick={onClick}
      role="switch"
      aria-checked={on}
      style={{
        width: 40,
        height: 23,
        borderRadius: 20,
        background: on ? "var(--accent)" : "var(--border-2)",
        position: "relative",
        cursor: "pointer",
        flexShrink: 0,
        transition: "background .15s",
        display: "inline-block",
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

// ─── Main page ────────────────────────────────────────────────────────────────

export default function GuardSettingsPage() {
  return <AppShell><SettingsContent /></AppShell>
}

function SettingsContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)

  const [prefs, setPrefs] = useState<TeamPrefs>({
    alert_channel: null,
    alert_slack_integration_id: null,
    notify_on_block: true,
    notify_on_budget: true,
    automation_security_scan: false,
    automation_workflow_trigger: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Notification toggles: extend prefs with warn + digest
  const [notifWarn, setNotifWarn] = useState(true)
  const [notifDigest, setNotifDigest] = useState(false)

  // Enforcement mode
  const [enforcementMode, setEnforcementMode] = useState<"block" | "warn" | "audit">("warn")

  // Re-sync state
  const [resyncing, setResyncing] = useState(false)
  const [resyncDone, setResyncDone] = useState(false)

  // Token guardrails
  const { guardrails: tokenGuardrails, refresh: refreshGuardrails } = useTokenGuardrails(activeWorkspace?.id ?? null)
  const [guardrailState, setGuardrailState] = useState({ prompt_caching: true, model_routing: true, prompt_splitting: true })
  const [guardrailSaved, setGuardrailSaved] = useState(false)
  const [driftChannelInput, setDriftChannelInput] = useState("")
  const [savingDriftChannel, setSavingDriftChannel] = useState(false)
  const [driftChannelSaved, setDriftChannelSaved] = useState(false)

  // Sync status
  const [toolCoverage, setToolCoverage] = useState<Array<{ detected_tools: string[]; mcp_registered: string[]; hook_registered: string[] }> | null>(null)

  // MCP connect
  const [memberToken, setMemberToken] = useState<string | null | undefined>(undefined)
  const [mcpCopied, setMcpCopied] = useState(false)

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const wsId = activeWorkspace?.id ?? null
  const isAdmin = permissions.canEditSettings

  async function authHeaders(): Promise<Record<string, string>> {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }

  const load = useCallback(async () => {
    if (!wsId) return
    setLoading(true)
    setError(null)
    try {
      const headers = await authHeaders()
      const res = await fetch(`${base}/guard/config?workspace_id=${wsId}`, { headers })
      if (res.status === 404) { setLoading(false); return }
      if (!res.ok) throw new Error(`Failed to load team (${res.status})`)
      const data = await res.json()
      setPrefs({
        alert_channel: data.alert_channel ?? null,
        alert_slack_integration_id: data.alert_slack_integration_id ?? null,
        notify_on_block: data.notify_on_block ?? true,
        notify_on_budget: data.notify_on_budget ?? true,
        automation_security_scan: data.automation_security_scan ?? false,
        automation_workflow_trigger: data.automation_workflow_trigger ?? false,
      })
      if (data.enforcement_mode) setEnforcementMode(data.enforcement_mode as "block" | "warn" | "audit")
      // Load sync coverage + member token in parallel
      fetch(`${base}/guard/developer-tools?workspace_id=${wsId}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) setToolCoverage(d) })
        .catch(() => {})
      fetch(`${base}/guard/members/me/token?workspace_id=${wsId}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(d => setMemberToken(d?.member_token ?? null))
        .catch(() => setMemberToken(null))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings")
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, wsId])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!tokenGuardrails) return
    setGuardrailState({
      prompt_caching:   tokenGuardrails.prompt_caching,
      model_routing:    tokenGuardrails.model_routing,
      prompt_splitting: tokenGuardrails.prompt_splitting,
    })
    if (tokenGuardrails.slack_webhook_url) setDriftChannelInput(tokenGuardrails.slack_webhook_url.replace(/^#+/, ""))
  }, [tokenGuardrails])

  async function patch(body: Partial<TeamPrefs>) {
    if (!wsId) return
    const headers = await authHeaders()
    const res = await fetch(`${base}/guard/config?workspace_id=${wsId}`, {
      method: "PATCH", headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
    return res.json()
  }

  async function handleResync() {
    if (!wsId || resyncing) return
    setResyncing(true)
    setResyncDone(false)
    try {
      const headers = await authHeaders()
      const res = await fetch(`${base}/guard/config/resync?workspace_id=${wsId}`, {
        method: "POST", headers,
      })
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
      await patch({ [field]: value })
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
      await patchTokenGuardrails(wsId, token ?? "", base, { [field]: value })
      refreshGuardrails()
      setGuardrailSaved(true)
      setTimeout(() => setGuardrailSaved(false), 2000)
    } catch {
      setGuardrailState(s => ({ ...s, [field]: !value }))
    }
  }

  async function handleSaveDriftChannel() {
    if (!wsId) return
    setSavingDriftChannel(true)
    const stripped = driftChannelInput.replace(/^#+/, "")
    try {
      const token = await getToken()
      await patchTokenGuardrails(wsId, token ?? "", base, { slack_webhook_url: stripped || null })
      setDriftChannelInput(stripped)
      refreshGuardrails()
      setDriftChannelSaved(true)
      setTimeout(() => setDriftChannelSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSavingDriftChannel(false)
    }
  }

  const NOTIFS = [
    { k: "blocks",  t: "Policy blocks",          d: "Notify the channel when a tool call is blocked by a rule." },
    { k: "warns",   t: "Policy warnings",         d: "Notify on warn-mode rule matches (e.g. force-push)." },
    { k: "budget",  t: "Budget threshold alerts", d: "Fire when team or a developer crosses the alert threshold." },
    { k: "digest",  t: "Daily spend digest",      d: "A 9am summary of yesterday's spend, top tools and developers." },
  ]

  function getNotifValue(k: string): boolean {
    if (k === "blocks") return prefs.notify_on_block
    if (k === "budget") return prefs.notify_on_budget
    if (k === "warns")  return notifWarn
    if (k === "digest") return notifDigest
    return false
  }

  function toggleNotif(k: string) {
    if (k === "blocks") handleToggle("notify_on_block", !prefs.notify_on_block)
    else if (k === "budget") handleToggle("notify_on_budget", !prefs.notify_on_budget)
    else if (k === "warns")  setNotifWarn(v => !v)
    else if (k === "digest") setNotifDigest(v => !v)
  }

  return (
    <GuardShell>
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

          {/* Two-column layout */}
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20, alignItems: "start" }}>

            {/* LEFT — Slack notifications */}
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div className="card" style={{ overflow: "hidden" }}>
                {/* Card header */}
                <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, background: "#7c3aed", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                    {/* Slack hash icon approximation */}
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                      <path d="M14.5 2v20M9.5 2v20M2 14.5h20M2 9.5h20" />
                    </svg>
                  </span>
                  <div style={{ fontWeight: 650, fontSize: 14.5 }}>Slack notifications</div>
                  <span className="sbadge ok" style={{ marginLeft: "auto" }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--ok)", display: "inline-block" }} />
                    Connected
                  </span>
                </div>

                <div style={{ padding: "16px 20px" }}>
                  {/* Alert channel — Slack integration picker */}
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Alert channel</div>
                  <SlackIntegrationPicker
                    base={base}
                    wsId={wsId ?? undefined}
                    buildHeaders={async () => {
                      const token = await getToken()
                      const h: Record<string, string> = { "Content-Type": "application/json" }
                      if (token) h["Authorization"] = `Bearer ${token}`
                      return h
                    }}
                    integrationId={prefs.alert_slack_integration_id}
                    channel={prefs.alert_channel ?? ""}
                    isAdmin={isAdmin}
                    onSave={async (integrationId, channel) => {
                      await patch({ alert_slack_integration_id: integrationId as any, alert_channel: channel || null })
                      setPrefs(p => ({ ...p, alert_slack_integration_id: integrationId, alert_channel: channel || null }))
                    }}
                  />
                  <div style={{ marginBottom: 10 }} />

                  {/* Notification toggles */}
                  {NOTIFS.map((x, i) => (
                    <div
                      key={x.k}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 14,
                        padding: "13px 0",
                        borderTop: "1px solid var(--border)",
                      }}
                    >
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{x.t}</div>
                        <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{x.d}</div>
                      </div>
                      <GuardToggle
                        on={getNotifValue(x.k)}
                        onClick={() => isAdmin && toggleNotif(x.k)}
                      />
                    </div>
                  ))}

                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 14, lineHeight: 1.5 }}>
                    Spend alerts are deduped — Slack fires once per 5% increment, not on every tool call.
                  </div>

                  {/* Drift alert channel + Slack integration picker */}
                  <div style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 16 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Drift alert channel</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 8 }}>
                      Fires when a token guardrail goes inactive — tool removed or policy disabled.
                    </div>
                    <SlackIntegrationPicker
                      base={base}
                      wsId={wsId ?? undefined}
                      buildHeaders={async () => {
                        const token = await getToken()
                        const h: Record<string, string> = { "Content-Type": "application/json" }
                        if (token) h["Authorization"] = `Bearer ${token}`
                        return h
                      }}
                      integrationId={tokenGuardrails?.slack_integration_id ?? null}
                      channel={tokenGuardrails?.slack_webhook_url ?? ""}
                      isAdmin={isAdmin}
                      onSave={async (integrationId, channel) => {
                        const token = await getToken()
                        await patchTokenGuardrails(wsId!, token ?? "", base, {
                          slack_integration_id: integrationId,
                          slack_webhook_url: channel || null,
                        })
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Setup checklist */}
              <div style={{ background: "var(--info-bg)", border: "1px solid var(--info-bd)", borderRadius: 12, padding: "14px 18px" }}>
                <p style={{ fontSize: 12, fontWeight: 600, color: "var(--info)", marginBottom: 6 }}>Setup checklist</p>
                <p style={{ fontSize: 12, color: "var(--info)", marginBottom: 4 }}>
                  Invite the Conduct AI Slack bot to your alert channel:{" "}
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

            {/* RIGHT — Sync status + Agent guard + Re-sync */}
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

              {/* Sync status — real data from /guard/developer-tools */}
              <div className="card" style={{ padding: "18px 20px" }}>
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

              {/* Agent guard */}
              <div className="card" style={{ padding: "18px 20px" }}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Agent guard</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>Enforce policy before every agentic AI step</div>
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
                      onClick={() => { if (isAdmin) { setEnforcementMode(k); patch({ enforcement_mode: k } as never).catch(() => {}) } }}
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

              {/* Auto-detected guardrails (read-only status) */}
              <div className="card" style={{ padding: "18px 20px" }}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Token guardrails</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>Auto-detected from installed tools and active policies.</div>
                {([
                  { key: "deterministic_offload", label: "Deterministic offload", desc: "warn-deterministic-compute policy" },
                  { key: "output_compression",    label: "Output compression",    desc: "RTK installed" },
                  { key: "structured_retrieval",  label: "Structured retrieval",  desc: "Agent Booster installed" },
                  { key: "metrics_budgets",       label: "Metrics & budgets",     desc: "Spend budgets configured" },
                ] as const).map((item, i) => {
                  const active = tokenGuardrails ? tokenGuardrails[item.key] : true
                  return (
                    <div key={item.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: i > 0 ? "1px solid var(--border)" : undefined }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{item.label}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>{item.desc}</div>
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 600, color: active ? "var(--ok)" : "var(--text-3)", flexShrink: 0, marginLeft: 12 }}>
                        {active ? "Active" : "Inactive"}
                      </span>
                    </div>
                  )
                })}
              </div>

              {/* Re-sync */}
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
          </div>

          {/* ── MCP Integration ─────────────────────────────────────────────── */}
          <div className="card" style={{ overflow: "hidden", marginTop: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
              </span>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>MCP Integration</div>
            </div>
            <div style={{ padding: "18px 20px" }}>
              <p style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 14 }}>
                Connect Claude.ai, Claude Desktop, or Claude for Work to ConductGuard. Every tool call will be audited and policy-enforced.
              </p>
              {memberToken === undefined ? (
                <div style={{ height: 38, borderRadius: 8, background: "var(--surface-2)", marginBottom: 14 }} />
              ) : memberToken === null ? (
                <p style={{ fontSize: 12.5, color: "var(--text-3)", marginBottom: 14 }}>
                  Run <code style={{ background: "var(--surface-2)", padding: "1px 6px", borderRadius: 4, fontFamily: "ui-monospace,monospace" }}>conduct guard init</code> in your terminal first to generate your token.
                </p>
              ) : (
                <div style={{ display: "flex", gap: 8, alignItems: "stretch", marginBottom: 14 }}>
                  <code style={{ flex: 1, fontSize: 11.5, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", fontFamily: "ui-monospace,monospace", color: "var(--text-2)", wordBreak: "break-all" }}>
                    {`https://api.conductai.ai/guard/mcp?workspace_id=${wsId ?? ""}&token=${memberToken}`}
                  </code>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ flexShrink: 0, background: mcpCopied ? "var(--ok-bg)" : undefined, color: mcpCopied ? "var(--ok)" : undefined }}
                    onClick={async () => {
                      await navigator.clipboard.writeText(`https://api.conductai.ai/guard/mcp?workspace_id=${wsId ?? ""}&token=${memberToken}`)
                      setMcpCopied(true)
                      setTimeout(() => setMcpCopied(false), 2000)
                    }}
                  >
                    {mcpCopied ? "Copied!" : "Copy"}
                  </button>
                </div>
              )}
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 5 }}>
                <li style={{ fontSize: 12.5, color: "var(--text-3)" }}><strong style={{ color: "var(--text-2)" }}>Claude.ai</strong> — Settings &rarr; MCP Servers &rarr; Add &rarr; paste URL, then type <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>load mcp</code> in chat</li>
                <li style={{ fontSize: 12.5, color: "var(--text-3)" }}><strong style={{ color: "var(--text-2)" }}>Claude Desktop</strong> — run <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>conduct guard sync</code> in your terminal</li>
                <li style={{ fontSize: 12.5, color: "var(--text-3)" }}><strong style={{ color: "var(--text-2)" }}>Claude for Work</strong> — Admin Console &rarr; Integrations &rarr; MCP &rarr; paste URL, then type <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>load mcp</code> in chat</li>
              </ul>
            </div>
          </div>

          {/* ── Token Guardrails — manual toggles ───────────────────────────── */}
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
            <div style={{ padding: "4px 20px 16px" }}>
              {([
                { key: "prompt_caching",   label: "Prompt caching",   desc: "System prompts are cached on every agent run" },
                { key: "model_routing",    label: "Model routing",    desc: "Agent runs select model tier by task complexity" },
                { key: "prompt_splitting", label: "Prompt splitting", desc: "Agent Templates enforce composable YAML skills" },
              ] as const).map(item => (
                <div key={item.key} style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>{item.label}</div>
                    <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{item.desc}</div>
                  </div>
                  <GuardToggle
                    on={guardrailState[item.key]}
                    onClick={() => isAdmin && handleGuardrailToggle(item.key, !guardrailState[item.key])}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* ── Automation ───────────────────────────────────────────────────────── */}
          <div className="card" style={{ overflow: "hidden", marginTop: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#7c3aed", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                </svg>
              </span>
              <div>
                <div style={{ fontWeight: 650, fontSize: 14.5 }}>Automation</div>
                <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 1 }}>Connect Guard to Security Loop and Workflows to close the AI-SDLC cycle.</div>
              </div>
            </div>
            <div style={{ padding: "4px 20px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Trigger Security Loop on violation</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    When Guard blocks a policy, automatically run a Security Loop scan on the affected session. Surfaces related findings without developer action.
                  </div>
                </div>
                <GuardToggle
                  on={prefs.automation_security_scan}
                  onClick={() => isAdmin && handleToggle("automation_security_scan" as any, !prefs.automation_security_scan)}
                />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Auto-run Workflow on violation</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    Fire a workflow playbook when Guard blocks a call — e.g. notify the team, open a task, or lock the affected repo until reviewed.
                  </div>
                </div>
                <GuardToggle
                  on={prefs.automation_workflow_trigger}
                  onClick={() => isAdmin && handleToggle("automation_workflow_trigger" as any, !prefs.automation_workflow_trigger)}
                />
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8, padding: "8px 12px", background: "var(--surface-2)", borderRadius: 8 }}>
                Security Loop and Workflow must be installed for these automations to run.{" "}
                <a href="/secure/settings" style={{ color: "var(--accent-text)", textDecoration: "none" }}>Configure Security Loop →</a>
              </div>
            </div>
          </div>
        </>
      )}
    </GuardShell>
  )
}
