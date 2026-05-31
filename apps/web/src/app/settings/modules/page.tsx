"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth, useOrganization } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"

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

function ConductGuardModule() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()

  const [team, setTeam] = useState<GuardTeam | null>(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState(false)
  const [confirmUninstall, setConfirmUninstall] = useState(false)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Helpers ──────────────────────────────────────────────────────────────────

  const buildHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) {
      const t = await getToken()
      if (t) h["Authorization"] = `Bearer ${t}`
    }
    return h
  }, [getToken])

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  // ── Load installed state ─────────────────────────────────────────────────────

  useEffect(() => {
    async function init() {
      setLoading(true)
      const storedTeamId = typeof window !== "undefined"
        ? localStorage.getItem("guard_team_id")
        : null

      if (!storedTeamId) {
        setLoading(false)
        return
      }

      try {
        const h = await buildHeaders()
        const res = await fetch(`${base}/guard/teams/me`, { headers: h })
        if (res.ok) {
          const data: GuardTeam = await res.json()
          setTeam(data)
        } else {
          // Team no longer exists on the server — clear stale local state
          localStorage.removeItem("guard_team_id")
        }
      } catch {
        // Non-fatal: keep stored id, show installed UI optimistically
        setTeam({ id: storedTeamId, name: "", invite_code: "", developer_count: 0, policy_count: 0 })
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [buildHeaders, base])

  // ── Install ──────────────────────────────────────────────────────────────────

  async function handleInstall() {
    setInstalling(true)
    setError(null)
    try {
      const orgName = organization?.name ?? "My Organisation"
      const orgId   = organization?.id   ?? ""
      const h = await buildHeaders()
      const res = await fetch(`${base}/guard/teams`, {
        method: "POST",
        headers: h,
        body: JSON.stringify({ name: `${orgName} Guard Team`, org_id: orgId }),
      })
      if (!res.ok) {
        const body = await res.text()
        setError(`Installation failed — ${body || res.statusText}`)
        return
      }
      const data: GuardTeam = await res.json()
      localStorage.setItem("guard_team_id", data.id)
      setTeam(data)
      // Dispatch storage event so AppShell can react without a reload
      window.dispatchEvent(new Event("storage"))
    } catch {
      setError("Installation failed — check your connection and try again.")
    } finally {
      setInstalling(false)
    }
  }

  // ── Uninstall ─────────────────────────────────────────────────────────────────

  async function handleUninstall() {
    setUninstalling(true)
    localStorage.removeItem("guard_team_id")
    window.dispatchEvent(new Event("storage"))
    setTeam(null)
    setConfirmUninstall(false)
    setUninstalling(false)
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
            "Real-time activity feed across Claude Code, Codex, Cursor",
            "Policy enforcement — pushed to all developers automatically",
            "Token spend tracking and per-developer budgets",
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
          Org-level — applies across all projects in your workspace.
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
