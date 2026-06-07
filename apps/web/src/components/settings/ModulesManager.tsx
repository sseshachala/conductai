"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { setGuardTeamId, removeGuardTeamId } from "@/lib/guardStorage"
import { SecureLoopIcon } from "@/app/secure/_components"

interface GuardConfig {
  workspace_id: string
  invite_code: string
  alert_channel: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
}

interface OrgOption { id: string; name: string }

function ModuleCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
      {children}
    </div>
  )
}

function ConductGuardModule() {
  const { getToken } = useAuth()
  const { workspaces, activeWorkspace } = useWorkspace()

  const [config, setConfig] = useState<GuardConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState(false)
  const [confirmUninstall, setConfirmUninstall] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTeamPicker, setShowTeamPicker] = useState(false)
  const [selectedOrg, setSelectedOrg] = useState<OrgOption | null>(null)
  const [uninstallConfirmValue, setUninstallConfirmValue] = useState("")

  const availableOrgs: OrgOption[] = workspaces.map(w => ({ id: w.id, name: w.name }))
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const buildHeaders = useCallback(async (wsId?: string): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const id = wsId ?? activeWorkspace?.id
    if (id) h["X-Guard-Workspace-ID"] = id
    return h
  }, [getToken, activeWorkspace])

  const fetchInstallStatus = useCallback(async (wsId?: string) => {
    setLoading(true)
    const guardWsId = wsId ?? activeWorkspace?.id
    try {
      const h = await buildHeaders(guardWsId)
      const res = await fetch(`${base}/guard/config/installed${guardWsId ? `?workspace_id=${guardWsId}` : ""}`, { headers: h })
      if (res.ok) {
        const data = await res.json()
        if (data.installed) {
          if (guardWsId && typeof window !== "undefined") setGuardTeamId(guardWsId, guardWsId)
          const configRes = await fetch(`${base}/guard/config${guardWsId ? `?workspace_id=${guardWsId}` : ""}`, { headers: h })
          if (configRes.ok) setConfig(await configRes.json())
        } else {
          setConfig(null)
        }
      }
    } catch {
      setConfig(null)
    } finally {
      setLoading(false)
    }
  }, [buildHeaders, base, activeWorkspace])

  useEffect(() => { fetchInstallStatus() }, [fetchInstallStatus])

  function handleInstall() {
    setError(null)
    setSelectedOrg(activeWorkspace ? { id: activeWorkspace.id, name: activeWorkspace.name } : null)
    setShowTeamPicker(true)
  }

  async function handleInstallConfirm() {
    const org = selectedOrg
    if (!org) return
    setShowTeamPicker(false)
    setInstalling(true)
    setError(null)
    try {
      const h = await buildHeaders(org.id)
      const res = await fetch(`${base}/guard/config?workspace_id=${org.id}`, { headers: h })
      if (!res.ok) { const body = await res.text(); setError(`Installation failed — ${body || res.statusText}`); return }
      if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("guard-install-changed", { detail: { installed: true } }))
      await fetchInstallStatus(org.id)
    } catch {
      setError("Installation failed — check your connection and try again.")
    } finally {
      setInstalling(false)
    }
  }

  async function handleUninstall() {
    if (uninstallConfirmValue !== "ConductGuard") return
    setUninstalling(true)
    try {
      const wsId = activeWorkspace?.id
      const h = await buildHeaders(wsId)
      await fetch(`${base}/guard/config${wsId ? `?workspace_id=${wsId}` : ""}`, { method: "DELETE", headers: h })
    } catch { /* non-fatal */ } finally {
      if (typeof window !== "undefined") {
        if (activeWorkspace?.id) removeGuardTeamId(activeWorkspace.id)
        window.dispatchEvent(new CustomEvent("guard-install-changed", { detail: { installed: false } }))
      }
      setConfig(null); setConfirmUninstall(false); setUninstallConfirmValue(""); setUninstalling(false)
    }
  }

  if (loading) {
    return (
      <ModuleCard>
        <div style={{ height: 128, borderRadius: 12, background: "var(--surface-2)", opacity: 0.7 }} />
      </ModuleCard>
    )
  }

  const isInstalled = !!config

  return (
    <ModuleCard>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ width: 40, height: 40, borderRadius: 10, background: "var(--accent-weak)", color: "var(--accent-text)", display: "grid", placeItems: "center", flexShrink: 0, fontSize: 20 }} aria-hidden="true">🛡</span>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 650, color: "var(--text)", margin: 0 }}>ConductGuard</h3>
            <p style={{ fontSize: 12.5, color: "var(--text-3)", marginTop: 3, margin: "3px 0 0" }}>AI tool fleet management for your engineering team.</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {isInstalled && <span className="sbadge ok">✓ Installed</span>}
          {isInstalled ? (
            <button onClick={() => setConfirmUninstall(true)} disabled={uninstalling} className="btn btn-ghost btn-sm" style={{ color: "var(--err)" }}>Uninstall</button>
          ) : (
            <button onClick={handleInstall} disabled={installing} className="btn btn-primary btn-sm">{installing ? "Installing…" : "Install"}</button>
          )}
        </div>
      </div>

      {/* Feature list — not installed */}
      {!isInstalled && (
        <>
          <ul style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13, color: "var(--text-2)", listStyle: "none", margin: 0, padding: 0 }}>
            {[
              "Monthly spend limits with hard caps — blocks sessions when budget is hit",
              "Alert at configurable thresholds (80%, 90%, custom) before costs spiral",
              "Real-time activity feed across Claude Code, Codex, Cursor",
              "Policy enforcement — pushed to all developers automatically",
              "Full audit trail — SOC 2 ready",
            ].map(feat => (
              <li key={feat} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                <span style={{ color: "var(--ok)", marginTop: 2, flexShrink: 0, fontSize: 12 }} aria-hidden="true">✓</span>
                <span>{feat}</span>
              </li>
            ))}
          </ul>
          <p style={{ fontSize: 12, color: "var(--text-muted)", borderTop: "1px solid var(--border)", paddingTop: 12, margin: 0 }}>
            Team-level — applies across all projects in the selected team.
          </p>
        </>
      )}

      {/* Installed state */}
      {isInstalled && config && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <Link href="/guard" className="btn btn-ghost btn-sm" style={{ color: "var(--accent-text)" }}>
            Go to Guard dashboard →
          </Link>
        </div>
      )}

      {/* Error */}
      {error && <p style={{ fontSize: 12, color: "var(--err)", borderTop: "1px solid var(--err-bd)", paddingTop: 12, margin: 0 }}>{error}</p>}

      {/* Team picker dialog */}
      {showTeamPicker && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)", backdropFilter: "blur(4px)" }}>
          <div className="card" style={{ maxWidth: 400, width: "100%", margin: "0 16px", padding: 24, display: "flex", flexDirection: "column", gap: 16, boxShadow: "var(--shadow-lg)" }}>
            <div>
              <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>Select a team</h4>
              <p style={{ fontSize: 12, color: "var(--text-3)", marginTop: 4 }}>Guard will apply to all projects in the selected team.</p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {availableOrgs.length === 0 && <p style={{ fontSize: 12, color: "var(--text-muted)", padding: "8px 0" }}>No teams found.</p>}
              {availableOrgs.map(org => (
                <button key={org.id} onClick={() => setSelectedOrg(org)}
                  style={selectedOrg?.id === org.id
                    ? { width: "100%", display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", borderRadius: 8, fontSize: 14, textAlign: "left", background: "var(--accent-weak)", border: "1px solid var(--accent)", color: "var(--text)", cursor: "pointer" }
                    : { width: "100%", display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", borderRadius: 8, fontSize: 14, textAlign: "left", background: "transparent", border: "1px solid var(--border)", color: "var(--text-2)", cursor: "pointer" }
                  }>
                  <span style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--accent-weak)", color: "var(--accent-text)", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    {org.name.charAt(0).toUpperCase()}
                  </span>
                  <span style={{ fontWeight: 500 }}>{org.name}</span>
                  {selectedOrg?.id === org.id && <span style={{ marginLeft: "auto", color: "var(--accent-text)", fontSize: 12 }}>✓</span>}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, paddingTop: 4 }}>
              <button onClick={() => setShowTeamPicker(false)} className="btn btn-ghost" style={{ flex: 1 }}>Cancel</button>
              <button onClick={handleInstallConfirm} disabled={!selectedOrg} className="btn btn-primary" style={{ flex: 1 }}>Install Guard</button>
            </div>
          </div>
        </div>
      )}

      {/* Uninstall confirmation */}
      {confirmUninstall && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)", backdropFilter: "blur(4px)" }}>
          <div className="card" style={{ maxWidth: 400, width: "100%", margin: "0 16px", padding: 24, display: "flex", flexDirection: "column", gap: 16, boxShadow: "var(--shadow-lg)" }}>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>Uninstall ConductGuard?</h4>
            <p style={{ fontSize: 13, color: "var(--text-2)" }}>This will disconnect all developers. Audit data is retained for 90 days.</p>
            <p style={{ fontSize: 12, color: "var(--err)" }}>Type <strong>ConductGuard</strong> to confirm.</p>
            <input value={uninstallConfirmValue} onChange={e => setUninstallConfirmValue(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleUninstall(); if (e.key === "Escape") { setConfirmUninstall(false); setUninstallConfirmValue("") } }}
              placeholder="ConductGuard"
              style={{ height: 36, border: "1px solid var(--err-bd)", borderRadius: 8, padding: "0 12px", fontSize: 13, width: "100%", background: "var(--surface)", color: "var(--text)", outline: "none", boxSizing: "border-box" }}
            />
            <div style={{ display: "flex", gap: 12, paddingTop: 4 }}>
              <button onClick={() => { setConfirmUninstall(false); setUninstallConfirmValue("") }} className="btn btn-ghost" style={{ flex: 1 }}>Cancel</button>
              <button onClick={handleUninstall} disabled={uninstalling || uninstallConfirmValue !== "ConductGuard"}
                style={{ flex: 1, background: "var(--err)", color: "#fff", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: uninstallConfirmValue === "ConductGuard" ? "pointer" : "not-allowed", opacity: uninstallConfirmValue === "ConductGuard" ? 1 : 0.4 }}>
                {uninstalling ? "Uninstalling…" : "Uninstall"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ModuleCard>
  )
}

function SecurityLoopModule() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [installed, setInstalled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState(false)
  const [confirmUninstall, setConfirmUninstall] = useState(false)
  const [uninstallConfirmValue, setUninstallConfirmValue] = useState("")
  const [error, setError] = useState<string | null>(null)

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const buildHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    return h
  }, [getToken])

  useEffect(() => {
    const wsId = activeWorkspace?.id
    if (!wsId) { setLoading(false); return }
    buildHeaders().then(h =>
      fetch(`${base}/secure/installed?workspace_id=${wsId}`, { headers: h })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) setInstalled(!!d.installed) })
        .catch(() => {})
        .finally(() => setLoading(false))
    )
  }, [activeWorkspace?.id, buildHeaders, base])

  async function handleInstall() {
    const wsId = activeWorkspace?.id
    if (!wsId) return
    setInstalling(true)
    setError(null)
    try {
      const h = await buildHeaders()
      const res = await fetch(`${base}/secure/install?workspace_id=${wsId}`, { method: "POST", headers: h })
      if (!res.ok) { setError(`Install failed (${res.status})`); return }
      setInstalled(true)
      if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("secure-install-changed", { detail: { installed: true } }))
    } catch {
      setError("Install failed — check your connection.")
    } finally {
      setInstalling(false)
    }
  }

  async function handleUninstall() {
    if (uninstallConfirmValue !== "SecurityLoop") return
    const wsId = activeWorkspace?.id
    setUninstalling(true)
    try {
      const h = await buildHeaders()
      await fetch(`${base}/secure/install${wsId ? `?workspace_id=${wsId}` : ""}`, { method: "DELETE", headers: h })
    } catch {}
    finally {
      setInstalled(false)
      setConfirmUninstall(false)
      setUninstallConfirmValue("")
      setUninstalling(false)
      if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("secure-install-changed", { detail: { installed: false } }))
    }
  }

  if (loading) {
    return <ModuleCard><div style={{ height: 100, borderRadius: 12, background: "var(--surface-2)", opacity: 0.7 }} /></ModuleCard>
  }

  return (
    <ModuleCard>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ width: 40, height: 40, borderRadius: 10, background: "#fee2e2", color: "#dc2626", display: "grid", placeItems: "center", flexShrink: 0 }}>
            <SecureLoopIcon size={20} />
          </span>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 650, color: "var(--text)", margin: 0 }}>Security Loop</h3>
            <p style={{ fontSize: 12.5, color: "var(--text-3)", margin: "3px 0 0" }}>Passive security classifier for Claude Code — zero developer action required.</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {installed && <span className="sbadge ok">✓ Installed</span>}
          {installed ? (
            <button onClick={() => setConfirmUninstall(true)} disabled={uninstalling} className="btn btn-ghost btn-sm" style={{ color: "var(--err)" }}>Uninstall</button>
          ) : (
            <button onClick={handleInstall} disabled={installing} className="btn btn-primary btn-sm">
              {installing ? "Installing…" : "Install"}
            </button>
          )}
        </div>
      </div>

      {!installed && (
        <ul style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13, color: "var(--text-2)", listStyle: "none", margin: 0, padding: 0 }}>
          {[
            "Runs on every Claude Code tool call — no hooks to configure per developer",
            "Detects secrets, injections, path traversal, and OWASP patterns automatically",
            "Findings surface in the Secure dashboard with severity, file, and session ID",
            "Slack alerts on high/critical findings with one toggle",
            "Custom detection rules via regex — add your own patterns",
          ].map(feat => (
            <li key={feat} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ color: "var(--ok)", marginTop: 2, flexShrink: 0, fontSize: 12 }}>✓</span>
              <span>{feat}</span>
            </li>
          ))}
        </ul>
      )}

      {installed && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <Link href="/secure" className="btn btn-ghost btn-sm" style={{ color: "var(--accent-text)" }}>
            Go to Security Loop dashboard →
          </Link>
        </div>
      )}

      {error && <p style={{ fontSize: 12, color: "var(--err)", borderTop: "1px solid var(--err-bd)", paddingTop: 12, margin: 0 }}>{error}</p>}

      {confirmUninstall && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)", backdropFilter: "blur(4px)" }}>
          <div className="card" style={{ maxWidth: 400, width: "100%", margin: "0 16px", padding: 24, display: "flex", flexDirection: "column", gap: 16, boxShadow: "var(--shadow-lg)" }}>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>Uninstall Security Loop?</h4>
            <p style={{ fontSize: 13, color: "var(--text-2)" }}>The classifier will stop running on all developers' machines on next sync. Findings data is retained.</p>
            <p style={{ fontSize: 12, color: "var(--err)" }}>Type <strong>SecurityLoop</strong> to confirm.</p>
            <input
              value={uninstallConfirmValue}
              onChange={e => setUninstallConfirmValue(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleUninstall(); if (e.key === "Escape") { setConfirmUninstall(false); setUninstallConfirmValue("") } }}
              placeholder="SecurityLoop"
              style={{ height: 36, border: "1px solid var(--err-bd)", borderRadius: 8, padding: "0 12px", fontSize: 13, width: "100%", background: "var(--surface)", color: "var(--text)", outline: "none", boxSizing: "border-box" }}
            />
            <div style={{ display: "flex", gap: 12, paddingTop: 4 }}>
              <button onClick={() => { setConfirmUninstall(false); setUninstallConfirmValue("") }} className="btn btn-ghost" style={{ flex: 1 }}>Cancel</button>
              <button
                onClick={handleUninstall}
                disabled={uninstalling || uninstallConfirmValue !== "SecurityLoop"}
                style={{ flex: 1, background: "var(--err)", color: "#fff", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: uninstallConfirmValue === "SecurityLoop" ? "pointer" : "not-allowed", opacity: uninstallConfirmValue === "SecurityLoop" ? 1 : 0.4 }}
              >
                {uninstalling ? "Uninstalling…" : "Uninstall"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ModuleCard>
  )
}

export default function ModulesManager() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <ConductGuardModule />
      <SecurityLoopModule />
    </div>
  )
}
