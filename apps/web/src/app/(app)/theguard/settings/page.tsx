"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import { API } from "@/lib/api/client"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useTokenGuardrails, patchTokenGuardrails } from "@/hooks/useTokenGuardrails"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { SettingsShell, type SettingsTab } from "@/components/SettingsShell"

// ─── Types ────────────────────────────────────────────────────────────────────

interface TeamPrefs {
  alert_channel: string | null
  alert_slack_integration_id: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
  automation_security_scan: boolean
  automation_workflow_trigger: boolean
  deny_on_error: boolean
  notify_on_fail_open: boolean
  advisory_mode: boolean
}

// ─── Tab shape — mirrors workspace /settings via <SettingsShell> (issue #1359) ─

type GuardSettingsTab =
  | "enforcement"
  | "guardrails"
  | "sync"

const GUARD_SETTINGS_TABS: readonly SettingsTab<GuardSettingsTab>[] = [
  { key: "enforcement",   label: "Enforcement" },
  { key: "guardrails",    label: "Cost & performance" },
  { key: "sync",          label: "Sync status" },
]


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
  const searchParams = useSearchParams()

  // Legacy ?tab=notifications bookmarks: Notifications panel now lives at its own URL.
  useEffect(() => {
    if (searchParams?.get("tab") === "notifications") {
      router.replace("/theguard/connections/notifications")
    }
  }, [searchParams, router])

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
    notify_on_fail_open: true,
    advisory_mode: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)

  // Enforcement mode
  const [enforcementMode, setEnforcementMode] = useState<"block" | "warn" | "audit">("warn")
  const [failMode, setFailMode] = useState<"fail_open" | "fail_closed">("fail_open")
  const [denyOnError, setDenyOnError] = useState(true)
  const [notifyOnFailOpen, setNotifyOnFailOpen] = useState(true)
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
        notify_on_fail_open: data.notify_on_fail_open ?? true,
        advisory_mode: data.advisory_mode ?? false,
      })
      if (data.enforcement_mode) setEnforcementMode(data.enforcement_mode as "block" | "warn" | "audit")
      if (data.fail_mode) setFailMode(data.fail_mode as "fail_open" | "fail_closed")
      if (data.deny_on_error !== undefined) setDenyOnError(data.deny_on_error)
      if (data.notify_on_fail_open !== undefined) setNotifyOnFailOpen(data.notify_on_fail_open)
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
        <SettingsShell<GuardSettingsTab>
          wrapInAppShell={false}
          tabs={GUARD_SETTINGS_TABS}
          isAdmin={isAdmin}
          initialTab="enforcement"
          panels={{
            sync: (
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
            ),
            enforcement: (
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
                <label style={{ display: "flex", gap: 11, alignItems: "flex-start", cursor: isAdmin ? "pointer" : "default", marginTop: 14 }}
                  onClick={async () => {
                    if (!isAdmin) return
                    const next = !notifyOnFailOpen
                    setNotifyOnFailOpen(next)
                    try { await patchConfig({ notify_on_fail_open: next } as never) }
                    catch { setNotifyOnFailOpen(!next) }
                  }}>
                  <GuardToggle on={notifyOnFailOpen} onClick={() => {}} disabled={!isAdmin} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Notify on fail-open</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
                      Post a Slack warning to your workspace channel when Guard could not evaluate policy and allowed the request through. Requires a Slack webhook configured for the workspace.
                    </div>
                  </div>
                </label>
              </div>
              </div>
            ),
            guardrails: (
              <div className="card" style={{ overflow: "hidden" }}>
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
            ),
          }}
        >
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
        </SettingsShell>
      )}
    </GuardShell>
  )
}
