"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell } from "../_components"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { SecureLoopIcon } from "../_components"
import { SlackIntegrationPicker } from "@/components/SlackIntegrationPicker"

// Known tools — display name + support state
const KNOWN_TOOLS: { key: string; label: string; supported: boolean }[] = [
  { key: "claude-code", label: "Claude Code",     supported: true  },
  { key: "codex",       label: "Codex CLI",        supported: false },
  { key: "cursor",      label: "Cursor",           supported: false },
  { key: "copilot",     label: "GitHub Copilot",   supported: false },
  { key: "windsurf",    label: "Windsurf",         supported: false },
]

interface SecureConfig {
  security_emit_enabled: boolean
  security_slack_alerts_enabled: boolean
  security_slack_channel: string | null
  slack_integration_id: string | null
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
    slack_integration_id: null,
  })
  const [channelInput, setChannelInput] = useState("")
  const [channelSaved, setChannelSaved] = useState(false)
  const [savingChannel, setSavingChannel] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detectedTools, setDetectedTools] = useState<Set<string>>(new Set())

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
      const headers = await authHeaders()
      const [configRes, toolsRes] = await Promise.all([
        fetch(`${base}/secure/config?workspace_id=${wsId}`, { headers }),
        fetch(`${base}/guard/developer-tools?workspace_id=${wsId}`, { headers }),
      ])
      if (configRes.ok) {
        const data = await configRes.json()
        setConfig({
          security_emit_enabled: data.security_emit_enabled ?? true,
          security_slack_alerts_enabled: data.security_slack_alerts_enabled ?? false,
          security_slack_channel: data.security_slack_channel ?? null,
          slack_integration_id: data.slack_integration_id ?? null,
        })
        setChannelInput((data.security_slack_channel ?? "").replace(/^#+/, ""))
      }
      if (toolsRes.ok) {
        const devs: { detected_tools: string[] }[] = await toolsRes.json()
        const all = new Set(devs.flatMap(d => d.detected_tools ?? []))
        setDetectedTools(all)
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

          {/* Covered tools */}
          <div className="card" style={{ overflow: "hidden", marginBottom: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>Covered tools</div>
              <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                Detected from your team's machines. Security Loop runs on supported tools automatically.
              </div>
            </div>
            <div style={{ padding: "4px 20px 8px" }}>
              {KNOWN_TOOLS.map((tool, i) => {
                const detected = detectedTools.has(tool.key)
                const isActive = tool.supported && detected
                return (
                  <div key={tool.key} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 0", borderTop: i > 0 ? "1px solid var(--border)" : undefined, opacity: tool.supported ? 1 : 0.5 }}>
                    <span style={{ width: 32, height: 32, borderRadius: 8, background: tool.supported ? "#fee2e2" : "var(--surface-2)", color: tool.supported ? "#dc2626" : "var(--text-muted)", display: "grid", placeItems: "center", flexShrink: 0 }}>
                      <SecureLoopIcon size={15} />
                    </span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                        {tool.label}
                        {detected && (
                          <span style={{ fontSize: 10, fontWeight: 600, padding: "1px 7px", borderRadius: 20, background: "var(--ok-bg)", color: "var(--ok)" }}>detected</span>
                        )}
                        {!tool.supported && (
                          <span style={{ fontSize: 10, fontWeight: 600, padding: "1px 7px", borderRadius: 20, background: "var(--surface-2)", color: "var(--text-muted)" }}>coming soon</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 1 }}>
                        {tool.supported ? "Passive classifier active on every tool call" : "Security Loop support in development"}
                      </div>
                    </div>
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                      background: isActive ? "var(--ok)" : "var(--border-2)",
                    }} />
                  </div>
                )
              })}
            </div>
          </div>

          <div className="card" style={{ overflow: "hidden", marginBottom: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <SecureLoopIcon size={15} />
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

              {config.security_slack_alerts_enabled && (
                <div style={{ paddingBottom: 6 }}>
                  <SlackIntegrationPicker
                    base={base}
                    wsId={wsId}
                    buildHeaders={authHeaders}
                    integrationId={config.slack_integration_id}
                    channel={config.security_slack_channel ?? ""}
                    isAdmin={isAdmin}
                    onSave={async (integrationId, channel) => {
                      await patch({ slack_integration_id: integrationId as any, security_slack_channel: channel || null })
                      setConfig(c => ({ ...c, slack_integration_id: integrationId, security_slack_channel: channel || null }))
                    }}
                  />
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
