"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { setGuardTeamId, removeGuardTeamId } from "@/lib/guardStorage"

// ─── Types ────────────────────────────────────────────────────────────────────

interface GuardConfig {
  workspace_id: string
  invite_code: string
  alert_channel: string | null
  notify_on_block: boolean
  notify_on_budget: boolean
}

// ─── Module card shared shell ─────────────────────────────────────────────────

function ModuleCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-6 py-5 space-y-4">
      {children}
    </div>
  )
}

// ─── ConductGuard module ──────────────────────────────────────────────────────

interface OrgOption { id: string; name: string }

function ConductGuardModule() {
  const { getToken } = useAuth()
  const { workspaces, activeWorkspace } = useWorkspace()

  const [config, setConfig] = useState<GuardConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState(false)
  const [confirmUninstall, setConfirmUninstall] = useState(false)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTeamPicker, setShowTeamPicker] = useState(false)
  const [selectedOrg, setSelectedOrg] = useState<OrgOption | null>(null)
  const [uninstallConfirmValue, setUninstallConfirmValue] = useState("")

  const availableOrgs: OrgOption[] = workspaces.map(w => ({ id: w.id, name: w.name }))

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const buildHeaders = useCallback(async (wsId?: string): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const id = wsId ?? activeWorkspace?.id
    if (id) h["X-Guard-Workspace-ID"] = id
    return h
  }, [getToken, activeWorkspace])

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  // ── Load installed state ─────────────────────────────────────────────────────

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
          if (configRes.ok) {
            const t = await configRes.json()
            setConfig(t)
          }
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

  useEffect(() => {
    fetchInstallStatus()
  }, [fetchInstallStatus])

  // ── Install ──────────────────────────────────────────────────────────────────

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
      if (!res.ok) {
        const body = await res.text()
        setError(`Installation failed — ${body || res.statusText}`)
        return
      }
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("guard-install-changed", { detail: { installed: true } }))
      }
      await fetchInstallStatus(org.id)
    } catch {
      setError("Installation failed — check your connection and try again.")
    } finally {
      setInstalling(false)
    }
  }

  // ── Uninstall ─────────────────────────────────────────────────────────────────

  async function handleUninstall() {
    if (uninstallConfirmValue !== "ConductGuard") return
    setUninstalling(true)
    try {
      const wsId = activeWorkspace?.id
      const h = await buildHeaders(wsId)
      const qs = wsId ? `?workspace_id=${wsId}` : ""
      await fetch(`${base}/guard/config${qs}`, { method: "DELETE", headers: h })
    } catch {
      // Non-fatal — clear local state regardless
    } finally {
      if (typeof window !== "undefined") {
        if (activeWorkspace?.id) removeGuardTeamId(activeWorkspace.id)
        window.dispatchEvent(new CustomEvent("guard-install-changed", { detail: { installed: false } }))
      }
      setConfig(null)
      setConfirmUninstall(false)
      setUninstallConfirmValue("")
      setUninstalling(false)
    }
  }

  // ── Copy invite code ──────────────────────────────────────────────────────────

  async function handleCopy() {
    if (!config?.invite_code) return
    await navigator.clipboard.writeText(`conduct guard join ${config.invite_code}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ── Regenerate invite code ────────────────────────────────────────────────────

  async function handleRegenerate() {
    if (!config) return
    setRegenerating(true)
    try {
      const h = await buildHeaders()
      const wsId = activeWorkspace?.id
      const res = await fetch(
        `${base}/guard/config/invite/regenerate${wsId ? `?workspace_id=${wsId}` : ""}`,
        { method: "POST", headers: h }
      )
      if (res.ok) {
        const data: { invite_code: string } = await res.json()
        setConfig(prev => prev ? { ...prev, invite_code: data.invite_code } : prev)
      }
    } catch {
      // Non-fatal
    } finally {
      setRegenerating(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <ModuleCard>
        <div className="animate-pulse h-32 bg-stone-50 rounded-lg" />
      </ModuleCard>
    )
  }

  const isInstalled = !!config

  return (
    <ModuleCard>
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="text-2xl leading-none" aria-hidden="true">🛡</span>
          <div>
            <h3 className="text-sm font-semibold text-stone-900">ConductGuard</h3>
            <p className="text-xs text-stone-500 mt-0.5">AI tool fleet management for your engineering team.</p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {isInstalled && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5">
              <span aria-hidden="true">✓</span> Installed
            </span>
          )}
          {isInstalled ? (
            <button
              onClick={() => setConfirmUninstall(true)}
              disabled={uninstalling}
              className="text-xs font-medium text-stone-500 hover:text-red-600 border border-stone-200 hover:border-red-200 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
            >
              Uninstall
            </button>
          ) : (
            <button
              onClick={handleInstall}
              disabled={installing}
              className="text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-4 py-1.5 transition-colors disabled:opacity-50"
            >
              {installing ? "Installing…" : "Install"}
            </button>
          )}
        </div>
      </div>

      {/* Feature list — only shown when not installed */}
      {!isInstalled && (
        <ul className="space-y-1.5 text-sm text-stone-600">
          {[
            "Monthly spend limits with hard caps — blocks sessions when budget is hit",
            "Alert at configurable thresholds (80%, 90%, custom) before costs spiral",
            "Real-time activity feed across Claude Code, Codex, Cursor",
            "Policy enforcement — pushed to all developers automatically",
            "Full audit trail — SOC 2 ready",
          ].map(feat => (
            <li key={feat} className="flex items-start gap-2">
              <span className="text-indigo-500 mt-0.5 shrink-0" aria-hidden="true">✓</span>
              <span>{feat}</span>
            </li>
          ))}
        </ul>
      )}

      {!isInstalled && (
        <p className="text-xs text-stone-400 border-t border-stone-100 pt-3">
          Team-level — applies across all projects in the selected team.
        </p>
      )}

      {/* Installed state */}
      {isInstalled && config && (
        <div className="border-t border-stone-100 pt-4 space-y-4">
          <div className="flex items-center justify-end">
            <Link
              href="/guard"
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors"
            >
              Go to Guard dashboard →
            </Link>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-600 border-t border-red-100 pt-3">{error}</p>
      )}

      {/* Team picker dialog */}
      {showTeamPicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl border border-stone-200 shadow-xl max-w-sm w-full mx-4 p-6 space-y-4">
            <div>
              <h4 className="text-sm font-semibold text-stone-900">Select a team</h4>
              <p className="text-xs text-stone-500 mt-1">Guard will apply to all projects in the selected team.</p>
            </div>
            <div className="space-y-1.5">
              {availableOrgs.length === 0 && (
                <p className="text-xs text-stone-400 py-2">No teams found.</p>
              )}
              {availableOrgs.map(org => (
                <button
                  key={org.id}
                  onClick={() => setSelectedOrg(org)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors text-left ${
                    selectedOrg?.id === org.id
                      ? "bg-indigo-50 border border-indigo-200 text-indigo-900"
                      : "hover:bg-stone-50 border border-transparent text-stone-700"
                  }`}
                >
                  <span className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold flex items-center justify-center shrink-0">
                    {org.name.charAt(0).toUpperCase()}
                  </span>
                  <span className="font-medium">{org.name}</span>
                  {selectedOrg?.id === org.id && <span className="ml-auto text-indigo-600 text-xs">✓</span>}
                </button>
              ))}
            </div>
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => setShowTeamPicker(false)}
                className="flex-1 text-sm font-medium text-stone-600 border border-stone-200 rounded-lg px-4 py-2 hover:bg-stone-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleInstallConfirm}
                disabled={!selectedOrg}
                className="flex-1 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-4 py-2 transition-colors disabled:opacity-40"
              >
                Install Guard
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Uninstall confirmation dialog */}
      {confirmUninstall && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl border border-stone-200 shadow-xl max-w-sm w-full mx-4 p-6 space-y-4">
            <h4 className="text-sm font-semibold text-stone-900">Uninstall ConductGuard?</h4>
            <p className="text-sm text-stone-600">
              This will disconnect all developers. Audit data is retained for 90 days.
            </p>
            <p className="text-xs text-red-700">
              Type <strong>ConductGuard</strong> to confirm uninstall.
            </p>
            <input
              value={uninstallConfirmValue}
              onChange={e => setUninstallConfirmValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter") handleUninstall()
                if (e.key === "Escape") { setConfirmUninstall(false); setUninstallConfirmValue("") }
              }}
              placeholder="ConductGuard"
              className="w-full text-sm border border-red-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-red-300"
            />
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => { setConfirmUninstall(false); setUninstallConfirmValue("") }}
                className="flex-1 text-sm font-medium text-stone-600 border border-stone-200 rounded-lg px-4 py-2 hover:bg-stone-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUninstall}
                disabled={uninstalling || uninstallConfirmValue !== "ConductGuard"}
                className="flex-1 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg px-4 py-2 transition-colors disabled:opacity-50"
              >
                Uninstall
              </button>
            </div>
          </div>
        </div>
      )}
    </ModuleCard>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ModulesPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <ModulesPageInner />
  return <ModulesPageInner />
}

function ModulesPageInner() {
  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="mb-8">
          <p className="text-xs text-stone-400 mb-1">Settings · Modules</p>
          <h1 className="text-xl font-semibold text-stone-900">Modules</h1>
          <p className="text-sm text-stone-500 mt-1">
            Extend your workspace with first-party modules.
          </p>
        </div>

        <div className="space-y-4">
          <ConductGuardModule />
        </div>
      </div>
    </AppShell>
  )
}
