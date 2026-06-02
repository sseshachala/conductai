"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Category mapping
// ---------------------------------------------------------------------------

const RULE_CATEGORIES: Record<string, string> = {
  // Destructive Operations
  "no-rm-rf": "Destructive Operations",
  "no-git-reset-hard": "Destructive Operations",
  "no-force-push": "Destructive Operations",
  "no-drop-table": "Destructive Operations",
  "no-truncate-table": "Destructive Operations",
  "no-delete-without-where": "Destructive Operations",
  // Secrets & Credentials
  "no-env-commits": "Secrets & Credentials",
  "no-hardcoded-secrets": "Secrets & Credentials",
  "no-aws-keys": "Secrets & Credentials",
  "no-private-key-files": "Secrets & Credentials",
  // Production Gates
  "approve-prod-deploy": "Production Gates",
  "approve-db-migration-prod": "Production Gates",
  "approve-terraform-destroy": "Production Gates",
  "approve-kubectl-delete": "Production Gates",
  "approve-prod-env-edit": "Production Gates",
  // Audit
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

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

const ACTION_BADGE: Record<PolicyAction, { label: string; className: string }> = {
  block: { label: "BLOCK", className: "bg-red-100 text-red-700 border border-red-200" },
  warn: { label: "WARN", className: "bg-amber-100 text-amber-700 border border-amber-200" },
  approval: { label: "APPROVAL", className: "bg-blue-100 text-blue-700 border border-blue-200" },
  audit: { label: "AUDIT", className: "bg-stone-100 text-stone-600 border border-stone-200" },
  inject: { label: "INJECT", className: "bg-indigo-100 text-indigo-700 border border-indigo-200" },
}

function ActionBadge({ action }: { action: PolicyAction }) {
  const { label, className } = ACTION_BADGE[action] ?? ACTION_BADGE.audit
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold tracking-wide ${className}`}>
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Toggle
// ---------------------------------------------------------------------------

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${
        enabled ? "bg-indigo-600" : "bg-stone-200"
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
          enabled ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Add rule modal
// ---------------------------------------------------------------------------

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
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      <div className="relative z-10 w-full max-w-lg rounded-xl bg-white shadow-xl border border-stone-200">
        <div className="px-6 py-4 border-b border-stone-100 flex items-center justify-between">
          <h2 className="text-base font-semibold text-stone-900">Add rule</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-stone-400 hover:text-stone-600 transition-colors text-lg leading-none"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {/* Rule ID */}
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">
              Rule ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={form.rule_id}
              onChange={e => set("rule_id", e.target.value)}
              placeholder="no-rm-rf"
              className={`w-full rounded-md border px-3 py-1.5 text-sm text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent ${
                errors.rule_id ? "border-red-400" : "border-stone-200"
              }`}
            />
            {errors.rule_id && <p className="mt-1 text-xs text-red-500">{errors.rule_id}</p>}
            <p className="mt-1 text-xs text-stone-400">Slug format: lowercase letters, numbers, hyphens only.</p>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={e => set("description", e.target.value)}
              placeholder="Prevents recursive deletion of directories"
              className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Match tool */}
            <div>
              <label className="block text-xs font-medium text-stone-700 mb-1">Match tool</label>
              <select
                value={form.match_tool}
                onChange={e => set("match_tool", e.target.value as MatchTool)}
                className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option value="*">* (any)</option>
                <option value="bash">bash</option>
                <option value="edit">edit</option>
                <option value="write">write</option>
                <option value="read">read</option>
              </select>
            </div>

            {/* Action */}
            <div>
              <label className="block text-xs font-medium text-stone-700 mb-1">Action</label>
              <select
                value={form.action}
                onChange={e => set("action", e.target.value as PolicyAction)}
                className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option value="block">block</option>
                <option value="warn">warn</option>
                <option value="audit">audit</option>
                <option value="approval">approval</option>
                <option value="inject">inject</option>
              </select>
            </div>
          </div>

          {/* Match pattern */}
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">
              Match pattern (regex) <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={form.match_pattern}
              onChange={e => set("match_pattern", e.target.value)}
              placeholder={String.raw`rm\s+-rf`}
              className={`w-full rounded-md border px-3 py-1.5 text-sm font-mono text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent ${
                errors.match_pattern ? "border-red-400" : "border-stone-200"
              }`}
            />
            {errors.match_pattern && <p className="mt-1 text-xs text-red-500">{errors.match_pattern}</p>}
          </div>

          {/* Match path pattern */}
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">
              Match path pattern (regex, optional)
            </label>
            <input
              type="text"
              value={form.match_path_pattern}
              onChange={e => set("match_path_pattern", e.target.value)}
              placeholder=".github/workflows/.*"
              className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm font-mono text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Message */}
          <div>
            <label className="block text-xs font-medium text-stone-700 mb-1">Message</label>
            <input
              type="text"
              value={form.message}
              onChange={e => set("message", e.target.value)}
              placeholder="This operation is not permitted by your team policy."
              className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-stone-400">Shown to the developer when the rule fires.</p>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-md text-sm text-stone-600 hover:text-stone-900 hover:bg-stone-50 border border-stone-200 transition-colors"
            >
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

// ---------------------------------------------------------------------------
// Rule row
// ---------------------------------------------------------------------------

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

function RuleRow({
  policy,
  onToggle,
  onDelete,
  canWrite,
}: {
  policy: Policy
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  canWrite: boolean
}) {
  return (
    <tr className="group border-b border-stone-100 last:border-b-0">
      <td className="py-3 pl-4 pr-3 w-10">
        {canWrite
          ? <Toggle enabled={policy.enabled} onChange={() => onToggle(policy.id)} />
          : <span className={`inline-block w-9 h-5 rounded-full ${policy.enabled ? "bg-indigo-600" : "bg-stone-200"} opacity-50 cursor-not-allowed`} />
        }
      </td>
      <td className="py-3 pr-4 min-w-[160px]">
        <span className="font-mono text-sm text-stone-800">{policy.rule_id}</span>
        {policy.description && (
          <p className="text-xs text-stone-400 mt-0.5 truncate max-w-[200px]">{policy.description}</p>
        )}
      </td>
      <td className="py-3 pr-4 w-28">
        <ActionBadge action={policy.action} />
      </td>
      <td className="py-3 pr-4 hidden md:table-cell">
        <code className="text-xs text-stone-500 font-mono break-all">{policy.match_pattern}</code>
      </td>
      <td className="py-3 pr-4 text-xs text-stone-400 w-28 text-right whitespace-nowrap">
        {formatLastTriggered(policy.last_triggered)}
      </td>
      <td className="py-3 pr-4 w-8 text-right">
        {policy.builtin || !canWrite ? (
          <span
            className="text-stone-300 text-sm select-none"
            title={policy.builtin ? "Built-in rule — cannot be deleted" : undefined}
          >
            {policy.builtin && (
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5 inline-block">
                <path fillRule="evenodd" d="M8 1a3 3 0 0 0-3 3v1H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1V4a3 3 0 0 0-3-3Zm0 1.5A1.5 1.5 0 0 1 9.5 4v1h-3V4A1.5 1.5 0 0 1 8 2.5Z" clipRule="evenodd" />
              </svg>
            )}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onDelete(policy.id)}
            className="text-stone-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
            title="Delete rule"
            aria-label={`Delete rule ${policy.rule_id}`}
          >
            {/* trash icon */}
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5 inline-block">
              <path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35L12.95 5.5h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" />
            </svg>
          </button>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Category section
// ---------------------------------------------------------------------------

function CategorySection({
  category,
  policies,
  onToggle,
  onDelete,
  canWrite,
}: {
  category: string
  policies: Policy[]
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  canWrite: boolean
}) {
  return (
    <div className="mb-6">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-2 px-4">
        {category}
      </h2>
      <div className="rounded-lg border border-stone-200 bg-white overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-stone-100 bg-stone-50">
              <th className="py-2 pl-4 pr-3 w-10" />
              <th className="py-2 pr-4 text-xs font-medium text-stone-500">Rule ID</th>
              <th className="py-2 pr-4 w-28 text-xs font-medium text-stone-500">Action</th>
              <th className="py-2 pr-4 hidden md:table-cell text-xs font-medium text-stone-500">Pattern</th>
              <th className="py-2 pr-4 w-28 text-xs font-medium text-stone-500 text-right">Last triggered</th>
              <th className="py-2 pr-4 w-8" />
            </tr>
          </thead>
          <tbody>
            {policies.map(p => (
              <RuleRow key={p.id} policy={p} onToggle={onToggle} onDelete={onDelete} canWrite={canWrite} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sync status footer
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PoliciesPage() {
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

  // Clear skeleton when team resolution finishes with no result
  useEffect(() => {
    if (!teamLoading && !teamId) setLoading(false)
  }, [teamLoading, teamId])

  // Fetch on mount / when teamId resolves
  useEffect(() => {
    async function load() {
      if (!teamId) return
      setLoading(true)
      setError(null)
      try {
        const headers = await authHeaders()
        const qs = `?team_id=${encodeURIComponent(teamId)}`
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

  // Toggle enable/disable with optimistic update
  async function handleToggle(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev) return

    // Optimistic update
    setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: !p.enabled } : p))

    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/${id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ enabled: !prev.enabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      // Revert on failure
      setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: prev.enabled } : p))
    }
  }

  // Delete custom rule
  async function handleDelete(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev || prev.builtin) return

    // Optimistic remove
    setPolicies(ps => ps.filter(p => p.id !== id))

    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/${id}`, {
        method: "DELETE",
        headers,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      // Revert
      setPolicies(ps => [...ps, prev].sort((a, b) => a.rule_id.localeCompare(b.rule_id)))
    }
  }

  // Add rule
  async function handleAddRule(formData: {
    rule_id: string
    description: string
    match_tool: MatchTool
    match_pattern: string
    match_path_pattern: string
    action: PolicyAction
    message: string
  }) {
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
      if (teamId) body.team_id = teamId

      const res = await fetch(`${apiUrl}/guard/policies`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const created: Policy = await res.json()
      setPolicies(ps => [...ps, created])
      setShowModal(false)
    } catch (e) {
      // Surface error inside modal — rethrow to keep modal open
      throw e
    } finally {
      setSubmitting(false)
    }
  }

  // Group policies by category
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

  // Latest updated_at for sync footer
  const latestUpdated = policies
    .map(p => p.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1)

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Policies</h1>
            <p className="text-sm text-stone-500 mt-1">
              Set rules that apply to all developer AI tool sessions.
            </p>
          </div>
          {canWrite && (
            <Link
              href="/guard/policies/new"
              className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4">
                <path d="M8.75 3.75a.75.75 0 0 0-1.5 0v3.5h-3.5a.75.75 0 0 0 0 1.5h3.5v3.5a.75.75 0 0 0 1.5 0v-3.5h3.5a.75.75 0 0 0 0-1.5h-3.5v-3.5Z" />
              </svg>
              Add rule
            </Link>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="space-y-4">
            {[1, 2].map(i => (
              <div key={i} className="rounded-lg border border-stone-200 bg-white p-4 space-y-2 animate-pulse">
                <div className="h-3 w-32 rounded bg-stone-100" />
                <div className="h-10 w-full rounded bg-stone-50" />
                <div className="h-10 w-full rounded bg-stone-50" />
              </div>
            ))}
          </div>
        )}

        {/* Policy groups */}
        {!loading && !error && orderedCategories.length === 0 && (
          <div className="rounded-lg border border-stone-200 bg-white px-6 py-12 text-center">
            <p className="text-sm text-stone-400">No policies yet. Add a rule to get started.</p>
          </div>
        )}

        {!loading && !error && orderedCategories.map(cat => (
          <CategorySection
            key={cat}
            category={cat}
            policies={grouped[cat]}
            onToggle={handleToggle}
            onDelete={handleDelete}
            canWrite={canWrite}
          />
        ))}

        {/* Sync status footer */}
        {!loading && !error && policies.length > 0 && (
          <p className="text-xs text-stone-400 text-center pb-2">
            Policy last updated: {formatUpdatedAt(latestUpdated)} · Synced to developers
          </p>
        )}
      </div>

      {/* Add rule modal */}
      {showModal && (
        <AddRuleModal
          onClose={() => setShowModal(false)}
          onSubmit={handleAddRule}
          submitting={submitting}
        />
      )}
    </AppShell>
  )
}
