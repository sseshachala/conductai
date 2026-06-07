"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell } from "../page"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useGuardTeam } from "@/hooks/useGuardTeam"

interface SecureConfig {
  security_emit_enabled: boolean
  security_slack_alerts_enabled: boolean
  security_slack_channel: string | null
}

function GuardToggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <span
      onClick={onClick}
      role="switch"
      aria-checked={on}
      style={{
        width: 40, height: 23, borderRadius: 20,
        background: on ? "var(--accent)" : "var(--border-2)",
        position: "relative", cursor: "pointer", flexShrink: 0,
        transition: "background .15s", display: "inline-block",
      }}
    >
      <span style={{
        position: "absolute", top: 2.5, left: on ? 19.5 : 2.5,
        width: 18, height: 18, borderRadius: "50%",
        background: "#fff", transition: "left .15s",
        boxShadow: "var(--shadow-sm)",
      }} />
    </span>
  )
}

export default function SecureSettingsPage() {
  return <AppShell><SettingsContent /></AppShell>
}

function SettingsContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const { teamId } = useGuardTeam()
  const { permissions } = useGuardRole(teamId, activeWorkspace?.id ?? null)

  const [config, setConfig] = useState<SecureConfig>({
    security_emit_enabled: true,
    security_slack_alerts_enabled: false,
    security_slack_channel: null,
  })
  const [channelInput, setChannelInput] = useState("")
  const [channelSaved, setChannelSaved] = useState(false)
  const [savingChannel, setSavingChannel] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const wsId = activeWorkspace?.id
  const isAdmin = permissions.canEditSettings

  const authHeaders = useCallback(async () => {
    const token = await getToken()
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
  }, [getToken])

  const load = useCallback(async () => {
    if (!wsId) return
    setLoading(true)
    try {
      const res = await fetch(`${base}/secure/config?workspace_id=${wsId}`, { headers: await authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setConfig({
          security_emit_enabled: data.security_emit_enabled ?? true,
          security_slack_alerts_enabled: data.security_slack_alerts_enabled ?? false,
          security_slack_channel: data.security_slack_channel ?? null,
        })
        setChannelInput((data.security_slack_channel ?? "").replace(/^#+/, ""))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [base, wsId, authHeaders])

  useEffect(() => { load() }, [load])

  async function patch(body: Partial<SecureConfig>) {
    if (!wsId) return
    const res = await fetch(`${base}/secure/config?workspace_id=${wsId}`, {
      method: "PATCH", headers: await authHeaders(), body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
  }

  async function handleToggle(field: "security_emit_enabled" | "security_slack_alerts_enabled", value: boolean) {
    setConfig(c => ({ ...c, [field]: value }))
    try {
      await patch({ [field]: value })
    } catch (e) {
      setConfig(c => ({ ...c, [field]: !value }))
      setError(e instanceof Error ? e.message : "Save failed")
    }
  }

  async function handleSaveChannel() {
    setSavingChannel(true)
    const stripped = channelInput.replace(/^#+/, "")
    try {
      await patch({ security_slack_channel: stripped || null })
      setConfig(c => ({ ...c, security_slack_channel: stripped || null }))
      setChannelSaved(true)
      setTimeout(() => setChannelSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSavingChannel(false)
    }
  }

  return (
    <SecureShell>
      {loading ? (
        <div style={{ textAlign: "center", padding: "40px 0", fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
      ) : error ? (
        <div style={{ borderRadius: 12, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "12px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>{error}</div>
      ) : (
        <div style={{ maxWidth: 640 }}>

          <div className="card" style={{ overflow: "hidden", marginBottom: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
              </span>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>Security Loop — Claude Code</div>
            </div>

            <div style={{ padding: "4px 20px 16px" }}>

              {/* Security Emit */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Security Emit</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    Fast-path classifier runs on every Claude Code tool call. Findings surface here automatically — zero developer action required.
                  </div>
                </div>
                <GuardToggle
                  on={config.security_emit_enabled}
                  onClick={() => isAdmin && handleToggle("security_emit_enabled", !config.security_emit_enabled)}
                />
              </div>

              {/* Slack Alerts */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Slack Alerts</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    POST to a Slack channel when a finding is detected — includes severity, file, and Claude Code session ID.
                  </div>
                </div>
                <GuardToggle
                  on={config.security_slack_alerts_enabled}
                  onClick={() => isAdmin && handleToggle("security_slack_alerts_enabled", !config.security_slack_alerts_enabled)}
                />
              </div>

              {/* Channel input */}
              {config.security_slack_alerts_enabled && (
                <div style={{ paddingBottom: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Alert channel</div>
                  <div style={{ display: "flex", gap: 9 }}>
                    <div style={{ display: "flex", alignItems: "center", flex: 1, border: "1px solid var(--border-2)", borderRadius: 8, overflow: "hidden" }}>
                      <span style={{ padding: "0 10px", fontSize: 13, color: "var(--text-muted)", background: "var(--surface-2)", borderRight: "1px solid var(--border)", alignSelf: "stretch", display: "flex", alignItems: "center", userSelect: "none" }}>#</span>
                      <input
                        type="text"
                        value={channelInput}
                        onChange={e => isAdmin && setChannelInput(e.target.value.replace(/^#+/, ""))}
                        placeholder="security-alerts"
                        disabled={!isAdmin}
                        className="mono"
                        style={{ flex: 1, fontSize: 13, padding: "0 12px", height: 36, border: "none", background: "transparent", color: "var(--text)", outline: "none", opacity: isAdmin ? 1 : 0.6 }}
                        onKeyDown={e => { if (e.key === "Enter" && isAdmin) handleSaveChannel() }}
                      />
                    </div>
                    {isAdmin && (
                      <button onClick={handleSaveChannel} disabled={savingChannel} className="btn btn-ghost btn-sm">
                        {savingChannel ? "Saving…" : "Save"}
                      </button>
                    )}
                    {channelSaved && <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600, alignSelf: "center" }}>Saved</span>}
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8 }}>
                    Format: <code style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4, fontFamily: "ui-monospace,monospace" }}>[HIGH] secret-leak in config.py:12 · claude-code</code>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Info */}
          <div style={{ background: "var(--info-bg)", border: "1px solid var(--info-bd)", borderRadius: 12, padding: "14px 18px" }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: "var(--info)", marginBottom: 6 }}>How it works</p>
            <p style={{ fontSize: 12, color: "var(--info)", marginBottom: 4 }}>
              Security Emit activates on every developer's machine on next <code style={{ background: "rgba(37,99,235,.12)", padding: "1px 5px", borderRadius: 4, fontFamily: "ui-monospace,monospace" }}>conduct guard sync</code>.
            </p>
            <p style={{ fontSize: 12, color: "var(--info)" }}>
              Toggle here → flag syncs to all Claude Code sessions within 60 seconds. No per-developer action needed.
            </p>
          </div>
        </div>
      )}
    </SecureShell>
  )
}
