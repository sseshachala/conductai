"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"

// ─── Types ────────────────────────────────────────────────────────────────────

type PolicyAction = "block" | "warn" | "audit" | "approval" | "inject"
type MatchTool = "bash" | "edit" | "write" | "read" | "*"

interface Policy {
  id: string
  team_id: string
  rule_id: string
  description: string
  match_tool: MatchTool
  match_pattern: string
  match_path_pattern?: string
  action: PolicyAction
  message?: string
  enabled: boolean
  builtin: boolean
  category?: string
  last_triggered?: string | null
  updated_at?: string
}

// ─── Category mapping ─────────────────────────────────────────────────────────

const RULE_CATEGORIES: Record<string, string> = {
  "no-rm-rf": "Destructive Operations",
  "no-git-reset-hard": "Destructive Operations",
  "no-force-push": "Destructive Operations",
  "no-drop-table": "Destructive Operations",
  "no-truncate-table": "Destructive Operations",
  "no-delete-without-where": "Destructive Operations",
  "no-env-commits": "Secrets & Credentials",
  "no-hardcoded-secrets": "Secrets & Credentials",
  "no-aws-keys": "Secrets & Credentials",
  "no-private-key-files": "Secrets & Credentials",
  "approve-prod-deploy": "Production Gates",
  "approve-db-migration-prod": "Production Gates",
  "approve-terraform-destroy": "Production Gates",
  "approve-kubectl-delete": "Production Gates",
  "approve-prod-env-edit": "Production Gates",
  "audit-migrations": "Audit",
  "audit-ci-config": "Audit",
  "audit-dockerfile": "Audit",
}

const CATEGORY_ORDER = [
  "Destructive Operations",
  "Secrets & Credentials",
  "Production Gates",
  "Audit",
  "Custom Rules",
]

function categoryFor(rule_id: string): string {
  return RULE_CATEGORIES[rule_id] ?? "Custom Rules"
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

// ─── Action icon avatar ───────────────────────────────────────────────────────

function ActionAvatar({ action }: { action: PolicyAction }) {
  const styles: Record<PolicyAction, { bg: string; color: string }> = {
    block:    { bg: "var(--err-bg)",  color: "var(--err)"  },
    warn:     { bg: "var(--warn-bg)", color: "var(--warn)" },
    audit:    { bg: "var(--info-bg)", color: "var(--info)" },
    approval: { bg: "var(--info-bg)", color: "var(--info)" },
    inject:   { bg: "var(--ok-bg)",   color: "var(--ok)"   },
  }
  const s = styles[action] ?? styles.audit

  const Icon = () => {
    if (action === "block") {
      return (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      )
    }
    if (action === "warn") {
      return (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      )
    }
    // audit / approval / inject
    return (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    )
  }

  return (
    <span style={{
      width: 38,
      height: 38,
      borderRadius: 10,
      flexShrink: 0,
      display: "grid",
      placeItems: "center",
      background: s.bg,
      color: s.color,
    }}>
      <Icon />
    </span>
  )
}

// ─── Action badge ─────────────────────────────────────────────────────────────

const ACTION_BADGE_TONE: Record<PolicyAction, string> = {
  block:    "err",
  warn:     "warn",
  audit:    "info",
  approval: "info",
  inject:   "ok",
}

function ActionBadge({ action }: { action: PolicyAction }) {
  const tone = ACTION_BADGE_TONE[action] ?? "info"
  return (
    <span className={`sbadge ${tone}`} style={{ textTransform: "uppercase", fontSize: 9.5, letterSpacing: ".06em" }}>
      {action}
    </span>
  )
}

// ─── Toggle ───────────────────────────────────────────────────────────────────

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: () => void }) {
  return (
    <span
      onClick={onChange}
      role="switch"
      aria-checked={enabled}
      style={{
        width: 40,
        height: 23,
        borderRadius: 20,
        background: enabled ? "var(--accent)" : "var(--border-2)",
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
          left: enabled ? 19.5 : 2.5,
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatLastTriggered(val: string | null | undefined): string {
  if (!val) return "Never"
  try {
    const d = new Date(val)
    const diffMs = Date.now() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return "Just now"
    if (diffMin < 60) return `${diffMin}m ago`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `${diffH}h ago`
    return `${Math.floor(diffH / 24)}d ago`
  } catch {
    return "—"
  }
}

function formatUpdatedAt(iso: string | undefined): string {
  if (!iso) return "—"
  try {
    const d = new Date(iso)
    const diffMs = Date.now() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return "just now"
    if (diffMin < 60) return `${diffMin} min ago`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `${diffH}h ago`
    return `${Math.floor(diffH / 24)}d ago`
  } catch {
    return "—"
  }
}

// ─── Add rule modal ───────────────────────────────────────────────────────────

interface AddRuleFormData {
  rule_id: string
  description: string
  match_tool: MatchTool
  match_pattern: string
  match_path_pattern: string
  action: PolicyAction
  message: string
}

const EMPTY_FORM: AddRuleFormData = {
  rule_id: "",
  description: "",
  match_tool: "*",
  match_pattern: "",
  match_path_pattern: "",
  action: "block",
  message: "",
}

function AddRuleModal({
  onClose,
  onSubmit,
  submitting,
}: {
  onClose: () => void
  onSubmit: (data: AddRuleFormData) => Promise<void>
  submitting: boolean
}) {
  const [form, setForm] = useState<AddRuleFormData>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<keyof AddRuleFormData, string>>>({})

  function set<K extends keyof AddRuleFormData>(key: K, value: AddRuleFormData[K]) {
    setForm(prev => ({ ...prev, [key]: value }))
    setErrors(prev => ({ ...prev, [key]: undefined }))
  }

  function validate(): boolean {
    const next: Partial<Record<keyof AddRuleFormData, string>> = {}
    if (!form.rule_id.trim()) next.rule_id = "Required"
    else if (!/^[a-z0-9-]+$/.test(form.rule_id.trim())) next.rule_id = "Only lowercase letters, numbers, and hyphens"
    if (!form.match_pattern.trim()) next.match_pattern = "Required"
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    await onSubmit(form)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl bg-white shadow-xl border border-stone-200">
        <div className="px-6 py-4 border-b border-stone-100 flex items-center justify-between">
          <h2 className="text-base font-semibold text-stone-900">Add rule</h2>
          <button type="button" onClick={onClose} className="text-stone-400 hover:text-stone-600 text-lg leading-none" aria-label="Close">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Rule ID <span className="text-red-500">*</span></label>
            <input
              type="text"
              value={form.rule_id}
              onChange={e => set("rule_id", e.target.value)}
              placeholder="no-rm-rf"
              className={`w-full rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 ${errors.rule_id ? "border-red-400" : "border-stone-200"}`}
            />
            {errors.rule_id && <p className="mt-1 text-xs text-red-500">{errors.rule_id}</p>}
            <p className="mt-1 text-xs text-stone-400">Slug format: lowercase letters, numbers, hyphens only.</p>
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={e => set("description", e.target.value)}
              placeholder="Prevents recursive deletion of directories"
              className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-stone-700 mb-1">Match tool</label>
              <select
                value={form.match_tool}
                onChange={e => set("match_tool", e.target.value as MatchTool)}
                className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="*">* (any)</option>
                <option value="bash">bash</option>
                <option value="edit">edit</option>
                <option value="write">write</option>
                <option value="read">read</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-stone-700 mb-1">Action</label>
              <select
                value={form.action}
                onChange={e => set("action", e.target.value as PolicyAction)}
                className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="block">block</option>
                <option value="warn">warn</option>
                <option value="audit">audit</option>
                <option value="approval">approval</option>
                <option value="inject">inject</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Match pattern (regex) <span className="text-red-500">*</span></label>
            <input
              type="text"
              value={form.match_pattern}
              onChange={e => set("match_pattern", e.target.value)}
              placeholder={String.raw`rm\s+-rf`}
              className={`w-full rounded-md border px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 ${errors.match_pattern ? "border-red-400" : "border-stone-200"}`}
            />
            {errors.match_pattern && <p className="mt-1 text-xs text-red-500">{errors.match_pattern}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Match path pattern (regex, optional)</label>
            <input
              type="text"
              value={form.match_path_pattern}
              onChange={e => set("match_path_pattern", e.target.value)}
              placeholder=".github/workflows/.*"
              className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Message</label>
            <input
              type="text"
              value={form.message}
              onChange={e => set("message", e.target.value)}
              placeholder="This operation is not permitted by your team policy."
              className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="mt-1 text-xs text-stone-400">Shown to the developer when the rule fires.</p>
          </div>
          <div className="flex items-center justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-1.5 rounded-md text-sm text-stone-600 hover:text-stone-900 hover:bg-stone-50 border border-stone-200 transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-1.5 rounded-md text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Adding…" : "Add rule"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PoliciesPage() {
  return <AppShell><PoliciesContent /></AppShell>
}

function PoliciesContent() {
  const { getToken } = useAuth()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [policies, setPolicies] = useState<Policy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""
  const canWrite = permissions.canEditPolicies

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) {
      const t = await getToken()
      if (t) headers["Authorization"] = `Bearer ${t}`
    }
    return headers
  }, [getToken])

  useEffect(() => {
    if (!teamLoading && !teamId) setLoading(false)
  }, [teamLoading, teamId])

  useEffect(() => {
    async function load() {
      if (!teamId) return
      setLoading(true)
      setError(null)
      try {
        const headers = await authHeaders()
        const qs = `?workspace_id=${encodeURIComponent(teamId)}`
        const res = await fetch(`${apiUrl}/guard/policies${qs}`, { headers })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: Policy[] = await res.json()
        setPolicies(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load policies.")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [apiUrl, authHeaders, teamId])

  async function handleToggle(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev) return
    setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: !p.enabled } : p))
    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/${id}`, {
        method: "PATCH", headers,
        body: JSON.stringify({ enabled: !prev.enabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: prev.enabled } : p))
    }
  }

  async function handleDelete(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev || prev.builtin) return
    setPolicies(ps => ps.filter(p => p.id !== id))
    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/${id}`, { method: "DELETE", headers })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      setPolicies(ps => [...ps, prev].sort((a, b) => a.rule_id.localeCompare(b.rule_id)))
    }
  }

  async function handleAddRule(formData: AddRuleFormData) {
    setSubmitting(true)
    try {
      const headers = await authHeaders()
      const body: Record<string, unknown> = {
        rule_id: formData.rule_id.trim(),
        description: formData.description.trim(),
        match_tool: formData.match_tool,
        match_pattern: formData.match_pattern.trim(),
        action: formData.action,
        message: formData.message.trim(),
        enabled: true,
        builtin: false,
      }
      if (formData.match_path_pattern.trim()) body.match_path_pattern = formData.match_path_pattern.trim()
      if (teamId) body.workspace_id = teamId

      const res = await fetch(`${apiUrl}/guard/policies`, {
        method: "POST", headers,
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const created: Policy = await res.json()
      setPolicies(ps => [...ps, created])
      setShowModal(false)
    } catch (e) {
      throw e
    } finally {
      setSubmitting(false)
    }
  }

  // Group by category
  const grouped = policies.reduce<Record<string, Policy[]>>((acc, p) => {
    const cat = categoryFor(p.rule_id)
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(p)
    return acc
  }, {})

  const orderedCategories = [
    ...CATEGORY_ORDER.filter(c => grouped[c]),
    ...Object.keys(grouped).filter(c => !CATEGORY_ORDER.includes(c)),
  ]

  const latestUpdated = policies
    .map(p => p.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1)

  return (
    <>
      <GuardShell>
        {/* Sub-header row */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <span style={{ fontSize: 13.5, color: "var(--text-3)" }}>
            Rules sync to every developer&apos;s machine within <strong style={{ color: "var(--text)" }}>60 seconds</strong>.
            {" "}{policies.filter(p => p.enabled).length} active.
          </span>
          {canWrite && (
            <button
              onClick={() => setShowModal(true)}
              className="btn btn-primary btn-sm"
              style={{ marginLeft: "auto" }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
              New policy
            </button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 mb-4">{error}</div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
            {[1, 2, 3].map(i => (
              <div key={i} className="card" style={{ padding: 18, height: 72 }} />
            ))}
          </div>
        )}

        {/* Empty */}
        {!loading && !error && orderedCategories.length === 0 && (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No policies yet. Add a rule to get started.</p>
          </div>
        )}

        {/* Policy cards — grouped by category */}
        {!loading && !error && orderedCategories.map(cat => (
          <div key={cat} style={{ marginBottom: 24 }}>
            <div className="eyebrow" style={{ marginBottom: 10, paddingLeft: 2 }}>{cat}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {grouped[cat].map(p => (
                <div
                  key={p.id}
                  className="card"
                  style={{
                    padding: "15px 18px",
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    opacity: p.enabled ? 1 : 0.62,
                  }}
                >
                  <ActionAvatar action={p.action} />

                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 3 }}>
                      <span className="mono" style={{ fontWeight: 650, fontSize: 13.5 }}>{p.rule_id}</span>
                      <ActionBadge action={p.action} />
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>
                      {p.description || p.message || "—"}
                    </div>
                  </div>

                  {/* Match info */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 150 }}>
                    <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                      match <strong style={{ color: "var(--text-2)" }}>{p.match_tool}</strong>
                    </div>
                    <div
                      className="mono"
                      style={{ fontSize: 11.5, color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                    >
                      pattern <span style={{ color: "var(--err)" }}>{p.match_pattern}</span>
                    </div>
                  </div>

                  {/* Hits + last triggered */}
                  <div style={{ textAlign: "center", minWidth: 72 }}>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {formatLastTriggered(p.last_triggered)}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 1 }}>last triggered</div>
                  </div>

                  {/* Delete (custom rules only) */}
                  {!p.builtin && canWrite && (
                    <button
                      type="button"
                      onClick={() => handleDelete(p.id)}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4, flexShrink: 0 }}
                      title="Delete rule"
                      aria-label={`Delete rule ${p.rule_id}`}
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                        <path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35L12.95 5.5h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" />
                      </svg>
                    </button>
                  )}
                  {p.builtin && (
                    <span style={{ color: "var(--border-2)", flexShrink: 0 }} title="Built-in rule — cannot be deleted">
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                        <path fillRule="evenodd" d="M8 1a3 3 0 0 0-3 3v1H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1V4a3 3 0 0 0-3-3Zm0 1.5A1.5 1.5 0 0 1 9.5 4v1h-3V4A1.5 1.5 0 0 1 8 2.5Z" clipRule="evenodd" />
                      </svg>
                    </span>
                  )}

                  {/* Toggle */}
                  {canWrite
                    ? <Toggle enabled={p.enabled} onChange={() => handleToggle(p.id)} />
                    : (
                      <span
                        style={{
                          width: 40, height: 23, borderRadius: 20,
                          background: p.enabled ? "var(--accent)" : "var(--border-2)",
                          display: "inline-block", opacity: 0.5, flexShrink: 0,
                        }}
                      />
                    )
                  }
                </div>
              ))}
            </div>
          </div>
        ))}

        {/* Sync status footer */}
        {!loading && !error && policies.length > 0 && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", paddingBottom: 8 }}>
            Policy last updated: {formatUpdatedAt(latestUpdated)} · Synced to developers
          </p>
        )}
      </GuardShell>

      {/* Add rule modal */}
      {showModal && (
        <AddRuleModal
          onClose={() => setShowModal(false)}
          onSubmit={handleAddRule}
          submitting={submitting}
        />
      )}
    </>
  )
}
