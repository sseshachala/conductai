"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface GuardTeam {
  id: string
  name: string
  invite_code: string
  developer_count: number
  policy_count: number
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

  const [team, setTeam] = useState<GuardTeam | null>(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState(false)
  const [confirmUninstall, setConfirmUninstall] = useState(false)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTeamPicker, setShowTeamPicker] = useState(false)
  const [selectedOrg, setSelectedOrg] = useState<OrgOption | null>(null)

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
    const guardWsId = wsId ?? (typeof window !== "undefined" ? localStorage.getItem("guard_workspace_id") ?? undefined : undefined) ?? activeWorkspace?.id
    try {
      const h = await buildHeaders(guardWsId)
      const res = await fetch(`${base}/guard/teams/installed${guardWsId ? `?workspace_id=${guardWsId}` : ""}`, { headers: h })
      if (res.ok) {
        const data = await res.json()
        if (data.installed) {
          if (data.team_id && typeof window !== "undefined") localStorage.setItem("guard_team_id", data.team_id)
          const teamRes = await fetch(`${base}/guard/teams/me${guardWsId ? `?workspace_id=${guardWsId}` : ""}`, { headers: h })
          if (teamRes.ok) {
            const t = await teamRes.json()
            if (t.id && typeof window !== "undefined") localStorage.setItem("guard_team_id", t.id)
            setTeam(t)
          } else {
            setTeam({ id: data.team_id, name: data.team_name ?? "", invite_code: data.invite_code ?? "", developer_count: 0, policy_count: 0 })
          }
        } else {
          setTeam(null)
        }
      }
    } catch {
      setTeam(null)
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
      const res = await fetch(`${base}/guard/teams`, {
        method: "POST",
        headers: h,
        body: JSON.stringify({ name: `${org.name} Guard`, org_id: org.id }),
      })
      if (!res.ok) {
        const body = await res.text()
        setError(`Installation failed — ${body || res.statusText}`)
        return
      }
      if (typeof window !== "undefined") {
        localStorage.setItem("guard_workspace_id", org.id)
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
    setUninstalling(true)
    try {
      const teamId = typeof window !== "undefined" ? localStorage.getItem("guard_team_id") : null
      if (teamId) {
        const h = await buildHeaders()
        await fetch(`${base}/guard/teams/${teamId}`, { method: "DELETE", headers: h })
      }
    } catch {
      // Non-fatal — clear local state regardless
    } finally {
      if (typeof window !== "undefined") {
        localStorage.removeItem("guard_team_id")
        localStorage.removeItem("guard_workspace_id")
        window.dispatchEvent(new CustomEvent("guard-install-changed", { detail: { installed: false } }))
      }
      setTeam(null)
      setConfirmUninstall(false)
      setUninstalling(false)
    }
  }

  // ── Copy invite code ──────────────────────────────────────────────────────────

  async function handleCopy() {
    if (!team?.invite_code) return
    await navigator.clipboard.writeText(`conduct guard join ${team.invite_code}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ── Regenerate invite code ────────────────────────────────────────────────────

  async function handleRegenerate() {
    if (!team) return
    setRegenerating(true)
    try {
      const h = await buildHeaders()
      const res = await fetch(`${base}/guard/teams/${team.id}/invite/regenerate`, {
        method: "POST",
        headers: h,
      })
      if (res.ok) {
        const data: GuardTeam = await res.json()
        setTeam(data)
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

  const isInstalled = !!team

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
      {isInstalled && team && (
        <div className="border-t border-stone-100 pt-4 space-y-4">
          {/* Invite command */}
          <div>
            <p className="text-xs font-medium text-stone-700 mb-2">Invite your developers:</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 font-mono text-xs bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-700 truncate">
                conduct guard join {team.invite_code || "…"}
              </code>
              <button
                onClick={handleCopy}
                className="text-xs font-medium text-stone-600 hover:text-stone-900 border border-stone-200 rounded-lg px-3 py-2 transition-colors whitespace-nowrap"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
              <button
                onClick={handleRegenerate}
                disabled={regenerating}
                className="text-xs font-medium text-stone-500 hover:text-stone-800 border border-stone-200 rounded-lg px-3 py-2 transition-colors whitespace-nowrap disabled:opacity-50"
              >
                {regenerating ? "…" : "Regenerate"}
              </button>
            </div>
          </div>

          {/* Stats + dashboard link */}
          <div className="flex items-center justify-between">
            <p className="text-xs text-stone-500">
              {team.developer_count} developer{team.developer_count !== 1 ? "s" : ""} connected
              &nbsp;·&nbsp;
              {team.policy_count} polic{team.policy_count !== 1 ? "ies" : "y"} active
            </p>
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
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => setConfirmUninstall(false)}
                className="flex-1 text-sm font-medium text-stone-600 border border-stone-200 rounded-lg px-4 py-2 hover:bg-stone-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUninstall}
                disabled={uninstalling}
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
