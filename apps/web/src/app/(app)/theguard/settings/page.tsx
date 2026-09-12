"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { SettingsShell, type SettingsTab } from "@/components/SettingsShell"
import { GuardToggle } from "@/features/guard/GuardToggle"

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

const GUARD_SETTINGS_TABS: readonly SettingsTab<GuardSettingsTab>[] = [
  { key: "enforcement",   label: "Enforcement" },
]

// ─── Main page ────────────────────────────────────────────────────────────────

export default function GuardSettingsPage() {
  return <AppShell><SettingsContent /></AppShell>
}

function SettingsContent() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions, role: resolvedRole } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const router = useRouter()
  const searchParams = useSearchParams()

  // Legacy ?tab=* bookmarks — panels moved to their own URLs.
  useEffect(() => {
    const tab = searchParams?.get("tab")
    if (tab === "notifications") router.replace("/theguard/connections/notifications")
    else if (tab === "sync") router.replace("/theguard/connections/sync")
    else if (tab === "guardrails") router.replace("/theguard/spend/optimization")
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
    } catch (e: any) {
      if (e?.message?.includes("404") || String(e).includes("404")) { setLoading(false); return }
      setError(e instanceof Error ? e.message : "Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [authFetch, wsId])

  useEffect(() => { load() }, [load])

  async function patchConfig(body: Partial<TeamPrefs>) {
    if (!wsId) return
    const res = await guard.config.patch(authFetch, wsId, body as Record<string, unknown>)
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
    return res.json()
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
