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
  autopilot_enabled: boolean
  automation_workflow_on_finding: boolean
  automation_finding_severity: string
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
    autopilot_enabled: false,
    automation_workflow_on_finding: false,
    automation_finding_severity: "critical",
  })
  const [channelInput, setChannelInput] = useState("")
  const [channelSaved, setChannelSaved] = useState(false)
  const [savingChannel, setSavingChannel] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detectedTools, setDetectedTools] = useState<Set<string>>(new Set())
  const [memberToken, setMemberToken] = useState<string | null | undefined>(undefined)
  const [mcpCopied, setMcpCopied] = useState(false)

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
      const [configRes, toolsRes, tokenRes] = await Promise.all([
        fetch(`${base}/secure/config?workspace_id=${wsId}`, { headers }),
        fetch(`${base}/guard/developer-tools?workspace_id=${wsId}`, { headers }),
        fetch(`${base}/guard/members/me/token?workspace_id=${wsId}`, { headers }),
      ])
      if (configRes.ok) {
        const data = await configRes.json()
        setConfig({
          security_emit_enabled: data.security_emit_enabled ?? true,
          security_slack_alerts_enabled: data.security_slack_alerts_enabled ?? false,
          security_slack_channel: data.security_slack_channel ?? null,
          slack_integration_id: data.slack_integration_id ?? null,
          autopilot_enabled: data.autopilot_enabled ?? false,
          automation_workflow_on_finding: data.automation_workflow_on_finding ?? false,
          automation_finding_severity: data.automation_finding_severity ?? "critical",
        })
        setChannelInput((data.security_slack_channel ?? "").replace(/^#+/, ""))
      }
      if (toolsRes.ok) {
        const devs: { detected_tools: string[] }[] = await toolsRes.json()
        const all = new Set(devs.flatMap(d => d.detected_tools ?? []))
        setDetectedTools(all)
      }
      if (tokenRes.ok) {
        const td: { member_token: string | null; workspace_id: string } = await tokenRes.json()
        setMemberToken(td.member_token)
      } else {
        setMemberToken(null)
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
        <div style={{ maxWidth: 900 }}>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20, alignItems: "start" }}>

          {/* Covered tools */}
          <div className="card" style={{ overflow: "hidden" }}>
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

          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <SecureLoopIcon size={15} />
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ fontWeight: 650, fontSize: 14.5 }}>Security Loop</div>
                  <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: ".06em", padding: "2px 7px", borderRadius: 20, background: "linear-gradient(135deg,#7c3aed,#2563eb)", color: "#fff" }}>
                    AGENTIC
                  </span>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>
                  An AI agent triages every finding — dismisses false positives, escalates real threats, opens fix PRs
                </div>
              </div>
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

              {/* Autopilot */}
              <div style={{ padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                      <div style={{ fontWeight: 600, fontSize: 13.5 }}>Agentic Autopilot</div>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 20, background: config.autopilot_enabled ? "linear-gradient(135deg,#7c3aed,#2563eb)" : "var(--surface-2)", color: config.autopilot_enabled ? "#fff" : "var(--text-muted)", letterSpacing: ".04em" }}>
                        {config.autopilot_enabled ? "ACTIVE" : "OFF"}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-3)" }}>
                      When active, the AI agent goes all the way — reads the affected file, writes a targeted patch, opens a PR, and notifies your team. When off, the agent triages and flags but leaves fixing to you.
                    </div>
                    {config.autopilot_enabled && (
                      <div style={{ marginTop: 8, fontSize: 11.5, background: "linear-gradient(135deg,rgba(124,58,237,.08),rgba(37,99,235,.08))", border: "1px solid rgba(124,58,237,.25)", borderRadius: 8, padding: "8px 12px", color: "#5b21b6" }}>
                        Agent will autonomously fix every confirmed finding with a linked repo. Requires <strong>security-autopilot-fix</strong> playbook installed.
                      </div>
                    )}
                  </div>
                  <GuardToggle
                    on={config.autopilot_enabled}
                    onClick={async () => {
                      if (!isAdmin) return
                      const next = !config.autopilot_enabled
                      setConfig(c => ({ ...c, autopilot_enabled: next }))
                      try {
                        const res = await fetch(`${base}/secure/config?workspace_id=${wsId}`, {
                          method: "PATCH", headers: await authHeaders(),
                          body: JSON.stringify({ autopilot_enabled: next }),
                        })
                        if (!res.ok) throw new Error()
                      } catch {
                        setConfig(c => ({ ...c, autopilot_enabled: !next }))
                        setError("Save failed")
                      }
                    }}
                  />
                </div>
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

          </div>{/* end 2-col grid */}


          {/* ── Automation ──────────────────────────────────────────────────── */}
          <div className="card" style={{ overflow: "hidden", marginBottom: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#7c3aed", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                </svg>
              </span>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>Automation</div>
            </div>
            <div style={{ padding: "4px 20px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13.5 }}>Trigger Workflow on finding</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
                    When a finding meets the severity threshold, automatically fire a workflow playbook — e.g. create a task, notify the team, or escalate to on-call.
                  </div>
                </div>
                <GuardToggle
                  on={config.automation_workflow_on_finding}
                  onClick={async () => {
                    if (!isAdmin) return
                    const next = !config.automation_workflow_on_finding
                    setConfig(c => ({ ...c, automation_workflow_on_finding: next }))
                    try { await patch({ automation_workflow_on_finding: next }) }
                    catch { setConfig(c => ({ ...c, automation_workflow_on_finding: !next })); setError("Save failed") }
                  }}
                />
              </div>
              {config.automation_workflow_on_finding && (
                <div style={{ padding: "10px 0", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Minimum severity to trigger</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 1 }}>Only findings at or above this level fire the workflow.</div>
                  </div>
                  <select
                    value={config.automation_finding_severity}
                    onChange={async e => {
                      const val = e.target.value
                      setConfig(c => ({ ...c, automation_finding_severity: val }))
                      try { await patch({ automation_finding_severity: val }) }
                      catch { setError("Save failed") }
                    }}
                    disabled={!isAdmin}
                    style={{ fontSize: 12, border: "1px solid var(--border)", borderRadius: 8, padding: "5px 10px", color: "var(--text-2)", background: "var(--surface)", outline: "none", cursor: isAdmin ? "pointer" : "default" }}
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                  </select>
                </div>
              )}
              <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8, padding: "8px 12px", background: "var(--surface-2)", borderRadius: 8 }}>
                Guard violations can also trigger Security Loop scans.{" "}
                <a href="/guard/settings" style={{ color: "var(--accent-text)", textDecoration: "none" }}>Configure Guard automation →</a>
              </div>
            </div>
          </div>

          {/* ── MCP Integration ─────────────────────────────────────────────── */}
          <div className="card" style={{ overflow: "hidden", marginBottom: 20 }}>
            <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "#2563eb", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <path d="M8 21h8M12 17v4" />
                </svg>
              </span>
              <div style={{ fontWeight: 650, fontSize: 14.5 }}>MCP Integration</div>
            </div>
            <div style={{ padding: "16px 20px" }}>
              <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 14 }}>
                Connect Claude.ai, Claude Desktop, or Claude for Work to ConductGuard. Every tool call will be audited and policy-enforced.
              </div>

              {memberToken === undefined ? (
                // loading skeleton
                <div style={{ height: 36, borderRadius: 8, background: "var(--surface-2)", marginBottom: 14 }} />
              ) : memberToken === null ? (
                <div style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: 8, padding: "10px 14px", marginBottom: 14 }}>
                  Run <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface)", padding: "1px 5px", borderRadius: 4 }}>conduct guard init</code> in your terminal first to generate your token.
                </div>
              ) : (
                <div style={{ marginBottom: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <code style={{
                      flex: 1, fontFamily: "ui-monospace,monospace", fontSize: 11.5,
                      background: "var(--surface-2)", border: "1px solid var(--border)",
                      borderRadius: 8, padding: "8px 12px", color: "var(--text-2)",
                      wordBreak: "break-all", display: "block", lineHeight: 1.5,
                    }}>
                      {`https://api.conductai.ai/guard/mcp?workspace_id=${wsId ?? ""}&token=${memberToken}`}
                    </code>
                    <button
                      onClick={async () => {
                        await navigator.clipboard.writeText(`https://api.conductai.ai/guard/mcp?workspace_id=${wsId ?? ""}&token=${memberToken}`)
                        setMcpCopied(true)
                        setTimeout(() => setMcpCopied(false), 2000)
                      }}
                      style={{
                        flexShrink: 0, fontSize: 12, fontWeight: 600, padding: "7px 14px",
                        borderRadius: 8, border: "1px solid var(--border)",
                        background: mcpCopied ? "var(--ok-bg)" : "var(--surface-2)",
                        color: mcpCopied ? "var(--ok)" : "var(--text-2)",
                        cursor: "pointer", transition: "all .15s",
                      }}
                    >
                      {mcpCopied ? "Copied!" : "Copy"}
                    </button>
                  </div>
                </div>
              )}

              <div style={{ fontSize: 12, color: "var(--text-3)" }}>
                <div style={{ marginBottom: 5 }}>
                  <strong style={{ color: "var(--text-2)" }}>Claude.ai</strong> — Settings &rarr; MCP Servers &rarr; Add &rarr; paste URL
                </div>
                <div style={{ marginBottom: 5 }}>
                  <strong style={{ color: "var(--text-2)" }}>Claude Desktop</strong> — Settings &rarr; Developer &rarr; MCP Servers &rarr; paste URL
                </div>
                <div>
                  <strong style={{ color: "var(--text-2)" }}>Claude for Work</strong> — Admin Console &rarr; Integrations &rarr; MCP &rarr; paste URL
                </div>
              </div>
            </div>
          </div>

          {/* Info */}
          <div style={{ background: "var(--info-bg)", border: "1px solid var(--info-bd)", borderRadius: 12, padding: "14px 18px" }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: "var(--info)", marginBottom: 6 }}>How the agent works</p>
            <p style={{ fontSize: 12, color: "var(--info)", marginBottom: 4 }}>
              <strong>1. Detect</strong> — Security Emit passively classifies every Claude Code tool call. Zero developer friction.
            </p>
            <p style={{ fontSize: 12, color: "var(--info)", marginBottom: 4 }}>
              <strong>2. Triage</strong> — an AI agent reviews each finding: false positives are dismissed in seconds, real threats escalated immediately.
            </p>
            <p style={{ fontSize: 12, color: "var(--info)" }}>
              <strong>3. Fix (Autopilot)</strong> — with Agentic Autopilot active, the agent reads your code, writes a patch, and opens a PR — no human in the loop until review time.
            </p>
          </div>
        </div>
      )}
    </SecureShell>
  )
}
