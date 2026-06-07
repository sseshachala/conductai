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

// ─── Types ────────────────────────────────────────────────────────────────────

interface TeamPrefs {
  alert_channel: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
  security_emit_enabled: boolean
  security_slack_alerts_enabled: boolean
  security_slack_channel: string | null
}

// ─── Guard Shell ──────────────────────────────────────────────────────────────

const GUARD_TABS = [
  { href: "/guard",          label: "Overview"  },
  { href: "/guard/spend",    label: "Spend"     },
  { href: "/guard/policies", label: "Policies"  },
  { href: "/guard/activity", label: "Activity"  },
  { href: "/guard/settings", label: "Settings"  },
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
    notify_on_block: true,
    notify_on_budget: true,
    security_emit_enabled: false,
    security_slack_alerts_enabled: false,
    security_slack_channel: null,
  })
  const [channelInput, setChannelInput] = useState("")
  const [securityChannelInput, setSecurityChannelInput] = useState("")
  const [securityChannelSaved, setSecurityChannelSaved] = useState(false)
  const [savingSecurityChannel, setSavingSecurityChannel] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [channelSaved, setChannelSaved] = useState(false)
  const [savingChannel, setSavingChannel] = useState(false)

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
        notify_on_block: data.notify_on_block ?? true,
        notify_on_budget: data.notify_on_budget ?? true,
        security_emit_enabled: data.security_emit_enabled ?? false,
        security_slack_alerts_enabled: data.security_slack_alerts_enabled ?? false,
        security_slack_channel: data.security_slack_channel ?? null,
      })
      setChannelInput((data.alert_channel ?? "").replace(/^#+/, ""))
      setSecurityChannelInput((data.security_slack_channel ?? "").replace(/^#+/, ""))
      if (data.enforcement_mode) setEnforcementMode(data.enforcement_mode as "block" | "warn" | "audit")
      // Load sync coverage in parallel
      fetch(`${base}/guard/developer-tools?workspace_id=${wsId}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) setToolCoverage(d) })
        .catch(() => {})
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

  async function handleSaveChannel() {
    setSavingChannel(true)
    const stripped = channelInput.replace(/^#+/, "")
    try {
      await patch({ alert_channel: stripped || null })
      setChannelInput(stripped)
      setPrefs(p => ({ ...p, alert_channel: stripped || null }))
      setChannelSaved(true)
      setTimeout(() => setChannelSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSavingChannel(false)
    }
  }

  async function handleSecurityToggle(field: "security_emit_enabled" | "security_slack_alerts_enabled", value: boolean) {
    setPrefs(p => ({ ...p, [field]: value }))
    try {
      await patch({ [field]: value })
    } catch (e) {
      setPrefs(p => ({ ...p, [field]: !value }))
      setError(e instanceof Error ? e.message : "Save failed")
    }
  }

  async function handleSaveSecurityChannel() {
    setSavingSecurityChannel(true)
    const stripped = securityChannelInput.replace(/^#+/, "")
    try {
      await patch({ security_slack_channel: stripped || null })
      setSecurityChannelInput(stripped)
      setPrefs(p => ({ ...p, security_slack_channel: stripped || null }))
      setSecurityChannelSaved(true)
      setTimeout(() => setSecurityChannelSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSavingSecurityChannel(false)
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
                  {/* Alert channel input */}
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Alert channel</div>
                  <div style={{ display: "flex", gap: 9, marginBottom: 18 }}>
                    <div style={{ display: "flex", alignItems: "center", flex: 1, border: "1px solid var(--border-2)", borderRadius: 8, overflow: "hidden" }}>
                      <span style={{ padding: "0 10px", fontSize: 13, color: "var(--text-muted)", background: "var(--surface-2)", borderRight: "1px solid var(--border)", alignSelf: "stretch", display: "flex", alignItems: "center", userSelect: "none" }}>#</span>
                      <input
                        type="text"
                        value={channelInput}
                        onChange={e => isAdmin && setChannelInput(e.target.value.replace(/^#+/, ""))}
                        placeholder="guard-alerts"
                        disabled={!isAdmin}
                        className="mono"
                        style={{
                          flex: 1,
                          fontSize: 13,
                          padding: "0 12px",
                          height: 36,
                          border: "none",
                          background: "transparent",
                          color: "var(--text)",
                          outline: "none",
                          opacity: isAdmin ? 1 : 0.6,
                        }}
                        onKeyDown={e => { if (e.key === "Enter" && isAdmin) handleSaveChannel() }}
                      />
                    </div>
                    {isAdmin && (
                      <button
                        onClick={handleSaveChannel}
                        disabled={savingChannel}
                        className="btn btn-ghost btn-sm"
                      >
                        {savingChannel ? "Saving…" : "Send test"}
                      </button>
                    )}
                    {channelSaved && (
                      <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600, alignSelf: "center" }}>Saved</span>
                    )}
                  </div>

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

                  {/* Drift alert channel */}
                  <div style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 16 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Drift alert channel</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 10 }}>
                      Fires when a token guardrail goes inactive — tool removed or policy disabled.
                    </div>
                    <div style={{ display: "flex", gap: 9 }}>
                      <div style={{ display: "flex", alignItems: "center", flex: 1, border: "1px solid var(--border-2)", borderRadius: 8, overflow: "hidden" }}>
                        <span style={{ padding: "0 10px", fontSize: 13, color: "var(--text-muted)", background: "var(--surface-2)", borderRight: "1px solid var(--border)", alignSelf: "stretch", display: "flex", alignItems: "center", userSelect: "none" }}>#</span>
                        <input
                          type="text"
                          value={driftChannelInput}
                          onChange={e => isAdmin && setDriftChannelInput(e.target.value.replace(/^#+/, ""))}
                          placeholder="guard-drift-alerts"
                          disabled={!isAdmin}
                          className="mono"
                          style={{
                            flex: 1, fontSize: 13, padding: "0 12px", height: 36,
                            border: "none", background: "transparent", color: "var(--text)",
                            outline: "none", opacity: isAdmin ? 1 : 0.6,
                          }}
                          onKeyDown={e => { if (e.key === "Enter" && isAdmin) handleSaveDriftChannel() }}
                        />
                      </div>
                      {isAdmin && (
                        <button onClick={handleSaveDriftChannel} disabled={savingDriftChannel} className="btn btn-ghost btn-sm">
                          {savingDriftChannel ? "Saving…" : "Save"}
                        </button>
                      )}
                      {driftChannelSaved && (
                        <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600, alignSelf: "center" }}>Saved</span>
                      )}
                    </div>
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

          {/* ── Security Loop ───────────────────────────────────────────────── */}
          <div className="card" style={{ overflow: "hidden", marginTop: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
              </span>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>Security</div>
              <a href="/security" style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-3)", textDecoration: "none" }}>
                View findings →
              </a>
            </div>
            <div style={{ padding: "4px 20px 16px" }}>
              {/* Security Emit */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Security Emit</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    Classifier runs on every Claude Code tool call. Findings with secrets, injections, or OWASP keywords surface on the Security page automatically.
                  </div>
                </div>
                <GuardToggle
                  on={prefs.security_emit_enabled}
                  onClick={() => isAdmin && handleSecurityToggle("security_emit_enabled", !prefs.security_emit_enabled)}
                />
              </div>

              {/* Security Slack Alerts */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Security Slack Alerts</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    POST to a dedicated Slack channel when a finding is detected — includes developer name, session ID, severity, and file.
                  </div>
                </div>
                <GuardToggle
                  on={prefs.security_slack_alerts_enabled}
                  onClick={() => isAdmin && handleSecurityToggle("security_slack_alerts_enabled", !prefs.security_slack_alerts_enabled)}
                />
              </div>

              {/* Security channel input — shown when Slack Alerts is on */}
              {prefs.security_slack_alerts_enabled && (
                <div style={{ paddingTop: 6, paddingBottom: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Security alert channel</div>
                  <div style={{ display: "flex", gap: 9 }}>
                    <div style={{ display: "flex", alignItems: "center", flex: 1, border: "1px solid var(--border-2)", borderRadius: 8, overflow: "hidden" }}>
                      <span style={{ padding: "0 10px", fontSize: 13, color: "var(--text-muted)", background: "var(--surface-2)", borderRight: "1px solid var(--border)", alignSelf: "stretch", display: "flex", alignItems: "center", userSelect: "none" }}>#</span>
                      <input
                        type="text"
                        value={securityChannelInput}
                        onChange={e => isAdmin && setSecurityChannelInput(e.target.value.replace(/^#+/, ""))}
                        placeholder="security-alerts"
                        disabled={!isAdmin}
                        className="mono"
                        style={{
                          flex: 1, fontSize: 13, padding: "0 12px", height: 36,
                          border: "none", background: "transparent", color: "var(--text)",
                          outline: "none", opacity: isAdmin ? 1 : 0.6,
                        }}
                        onKeyDown={e => { if (e.key === "Enter" && isAdmin) handleSaveSecurityChannel() }}
                      />
                    </div>
                    {isAdmin && (
                      <button onClick={handleSaveSecurityChannel} disabled={savingSecurityChannel} className="btn btn-ghost btn-sm">
                        {savingSecurityChannel ? "Saving…" : "Save"}
                      </button>
                    )}
                    {securityChannelSaved && (
                      <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600, alignSelf: "center" }}>Saved</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8 }}>
                    Alert format: <code style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4, fontFamily: "ui-monospace,monospace" }}>[HIGH] secret-leak in config.py:12 — session abc123 · claude-code</code>
                  </div>
                </div>
              )}
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
        </>
      )}
    </GuardShell>
  )
}
