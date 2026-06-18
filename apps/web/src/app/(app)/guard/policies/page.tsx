"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"

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
  pack_id?: string | null
  last_triggered?: string | null
  updated_at?: string
  persona_affinity?: string[]
}

const PACK_LABELS: { id: string; name: string }[] = [
  { id: "conduct-owasp",   name: "OWASP Top 10" },
  { id: "conduct-soc2",    name: "SOC 2" },
  { id: "conduct-hipaa",   name: "HIPAA" },
  { id: "conduct-pci-dss", name: "PCI-DSS" },
  { id: "conduct-base",    name: "Base" },
]


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

// Shared field styles
const fieldStyle: React.CSSProperties = {
  width: "100%",
  borderRadius: 8,
  border: "1px solid var(--border)",
  padding: "6px 10px",
  fontSize: 13,
  color: "var(--text)",
  background: "var(--surface)",
  outline: "none",
  boxSizing: "border-box",
}

const fieldErrStyle: React.CSSProperties = {
  ...fieldStyle,
  borderColor: "var(--err-bd)",
}

const fieldMonoStyle: React.CSSProperties = {
  ...fieldStyle,
  fontFamily: "var(--font-mono, monospace)",
}

const fieldMonoErrStyle: React.CSSProperties = {
  ...fieldMonoStyle,
  borderColor: "var(--err-bd)",
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 11.5,
  fontWeight: 500,
  color: "var(--text-2)",
  marginBottom: 4,
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
  const { getToken } = useAuth()
  const [form, setForm] = useState<AddRuleFormData>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<keyof AddRuleFormData, string>>>({})
  const [aiPrompt, setAiPrompt] = useState("")
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  async function handleGenerate() {
    const text = aiPrompt.trim()
    if (!text) return
    setAiGenerating(true)
    setAiError(null)
    try {
      const token = getToken ? await getToken() : null
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (token) headers["Authorization"] = `Bearer ${token}`
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await fetch(`${apiUrl}/guard/policies/generate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ prompt: text }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setForm({
        rule_id: data.rule_id ?? "",
        description: data.description ?? "",
        match_tool: (data.match_tool as MatchTool) ?? "*",
        match_pattern: data.match_pattern ?? "",
        match_path_pattern: data.match_path_pattern ?? "",
        action: (data.action as PolicyAction) ?? "block",
        message: data.message ?? "",
      })
      setErrors({})
    } catch {
      setAiError("Couldn't generate a rule — try being more specific.")
    } finally {
      setAiGenerating(false)
    }
  }

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
    setSubmitError(null)
    try {
      await onSubmit(form)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to add rule. Please try again.")
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.3)",
        backdropFilter: "blur(4px)",
        zIndex: 50,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        onClick={onClose}
        style={{ position: "absolute", inset: 0 }}
        aria-hidden="true"
      />
      <div
        style={{
          position: "relative",
          zIndex: 10,
          width: "100%",
          maxWidth: 520,
          borderRadius: 14,
          background: "var(--surface)",
          boxShadow: "var(--shadow-lg)",
          border: "1px solid var(--border)",
        }}
      >
        {/* Modal header */}
        <div
          style={{
            padding: "16px 24px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "var(--text)" }}>Add rule</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 17,
              lineHeight: 1,
              color: "var(--text-muted)",
              padding: 2,
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal form */}
        <form onSubmit={handleSubmit} style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* AI generate */}
          <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={labelStyle}>Generate with AI</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 2 }}>
              {[
                { label: "Approve merge to main",    prompt: "Require approval before merging to the main or master branch" },
                { label: "No PII in files",          prompt: "Block writing files that contain email addresses or phone numbers" },
                { label: "No hardcoded IPs",         prompt: "Block hardcoded IP addresses in source code files" },
                { label: "Audit dependency changes", prompt: "Audit any changes to package.json, requirements.txt, or pyproject.toml" },
                { label: "No SELECT *",              prompt: "Warn when SQL queries use SELECT * instead of explicit column names" },
                { label: "Approve K8s manifests",    prompt: "Require approval before modifying Kubernetes manifest files" },
              ].map(t => (
                <button
                  key={t.label}
                  type="button"
                  disabled={aiGenerating}
                  onClick={() => setAiPrompt(t.prompt)}
                  style={{
                    fontSize: 11.5,
                    padding: "4px 10px",
                    borderRadius: 9999,
                    border: "1px solid var(--border)",
                    background: aiPrompt === t.prompt ? "var(--accent-weak)" : "var(--surface)",
                    color: "var(--text-3)",
                    cursor: aiGenerating ? "not-allowed" : "pointer",
                    opacity: aiGenerating ? 0.4 : 1,
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="text"
                value={aiPrompt}
                onChange={e => setAiPrompt(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); handleGenerate() } }}
                placeholder="Block any prompt asking for AWS credentials…"
                style={{ ...fieldStyle, flex: 1 }}
                disabled={aiGenerating}
              />
              <button
                type="button"
                onClick={handleGenerate}
                disabled={aiGenerating || !aiPrompt.trim()}
                className="btn btn-ghost btn-sm"
                style={{ whiteSpace: "nowrap", opacity: aiGenerating || !aiPrompt.trim() ? 0.5 : 1 }}
              >
                {aiGenerating ? "Generating…" : "Generate"}
              </button>
            </div>
            {aiError && <p style={{ margin: 0, fontSize: 11.5, color: "var(--err)" }}>{aiError}</p>}
          </div>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
            <span style={{ fontSize: 11.5, color: "var(--text-muted)", whiteSpace: "nowrap" }}>or fill manually</span>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>

          {/* Rule ID */}
          <div>
            <label style={labelStyle}>
              Rule ID <span style={{ color: "var(--err)" }}>*</span>
            </label>
            <input
              type="text"
              value={form.rule_id}
              onChange={e => set("rule_id", e.target.value)}
              onBlur={() => {
                const v = form.rule_id.trim()
                if (v && !/^[a-z0-9-]+$/.test(v)) {
                  setErrors(prev => ({ ...prev, rule_id: "Lowercase letters, numbers, and hyphens only" }))
                }
              }}
              placeholder="no-rm-rf"
              style={errors.rule_id ? fieldErrStyle : fieldStyle}
            />
            {errors.rule_id && (
              <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--err)" }}>{errors.rule_id}</p>
            )}
            <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--text-muted)" }}>
              Slug format: lowercase letters, numbers, hyphens only.
            </p>
          </div>

          {/* Description */}
          <div>
            <label style={labelStyle}>Description</label>
            <input
              type="text"
              value={form.description}
              onChange={e => set("description", e.target.value)}
              placeholder="Prevents recursive deletion of directories"
              style={fieldStyle}
            />
          </div>

          {/* Match tool + Action */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Match tool</label>
              <select
                value={form.match_tool}
                onChange={e => set("match_tool", e.target.value as MatchTool)}
                style={fieldStyle}
              >
                <option value="*">* (any)</option>
                <option value="bash">bash</option>
                <option value="edit">edit</option>
                <option value="write">write</option>
                <option value="read">read</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Action</label>
              <select
                value={form.action}
                onChange={e => set("action", e.target.value as PolicyAction)}
                style={fieldStyle}
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
            <label style={labelStyle}>
              Match pattern (regex) <span style={{ color: "var(--err)" }}>*</span>
            </label>
            <input
              type="text"
              value={form.match_pattern}
              onChange={e => set("match_pattern", e.target.value)}
              placeholder={String.raw`rm\s+-rf`}
              style={errors.match_pattern ? fieldMonoErrStyle : fieldMonoStyle}
            />
            {errors.match_pattern && (
              <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--err)" }}>{errors.match_pattern}</p>
            )}
          </div>

          {/* Match path pattern */}
          <div>
            <label style={labelStyle}>Match path pattern (regex, optional)</label>
            <input
              type="text"
              value={form.match_path_pattern}
              onChange={e => set("match_path_pattern", e.target.value)}
              placeholder=".github/workflows/.*"
              style={fieldMonoStyle}
            />
          </div>

          {/* Message */}
          <div>
            <label style={labelStyle}>Message</label>
            <input
              type="text"
              value={form.message}
              onChange={e => set("message", e.target.value)}
              placeholder="This operation is not permitted by your team policy."
              style={fieldStyle}
            />
            <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--text-muted)" }}>
              Shown to the developer when the rule fires.
            </p>
          </div>

          {/* Footer actions */}
          {submitError && (
            <p style={{ margin: 0, fontSize: 11.5, color: "var(--err)" }}>{submitError}</p>
          )}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, paddingTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              className="btn btn-ghost btn-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn btn-primary btn-sm"
              style={{ opacity: submitting ? 0.5 : 1, cursor: submitting ? "not-allowed" : "pointer" }}
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
  const [refreshing, setRefreshing] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [confirmDeleteValue, setConfirmDeleteValue] = useState("")
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [installedPacks, setInstalledPacks] = useState<Set<string>>(new Set())
  const [activePackFilter, setActivePackFilter] = useState<string | null>(null)
  const [activePersonaFilter, setActivePersonaFilter] = useState<string | null>(null)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)

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

  useEffect(() => {
    if (!teamId) return
    authHeaders().then(headers =>
      fetch(`${apiUrl}/compliance/packs/installed?workspace_id=${encodeURIComponent(teamId)}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d?.installed) {
            setInstalledPacks(new Set<string>(d.installed))
          }
        })
        .catch(() => {})
    )
  }, [apiUrl, teamId, authHeaders])

  useEffect(() => {
    const msg = sessionStorage.getItem("guard.policies.saved")
    if (msg) {
      sessionStorage.removeItem("guard.policies.saved")
      setSuccessBanner(msg)
      const t = setTimeout(() => setSuccessBanner(null), 5000)
      return () => clearTimeout(t)
    }
  }, [])

  async function handleRefreshBuiltins() {
    if (!teamId) return
    setRefreshing(true)
    try {
      const headers = await authHeaders()
      const res = await fetch(
        `${apiUrl}/guard/policies/reinstall-base?workspace_id=${encodeURIComponent(teamId)}`,
        { method: "POST", headers }
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // reload policies list
      const listRes = await fetch(`${apiUrl}/guard/policies?workspace_id=${encodeURIComponent(teamId)}`, { headers })
      if (listRes.ok) setPolicies(await listRes.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed.")
    } finally {
      setRefreshing(false)
    }
  }

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
    } catch (e) {
      setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: prev.enabled } : p))
      setError(e instanceof Error ? e.message : "Failed to update rule. Please try again.")
    }
  }

  async function handleDelete(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev || prev.builtin) return
    if (confirmDeleteValue !== prev.rule_id) return
    setConfirmDeleteId(null)
    setConfirmDeleteValue("")
    setPolicies(ps => ps.filter(p => p.id !== id))
    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/${id}`, { method: "DELETE", headers })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch (e) {
      setPolicies(ps => [...ps, prev].sort((a, b) => a.rule_id.localeCompare(b.rule_id)))
      setError(e instanceof Error ? e.message : "Failed to delete rule. Please try again.")
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

  const baseVisible = activePackFilter
    ? policies.filter(p => p.pack_id === activePackFilter)
    : policies
  const visiblePolicies = activePersonaFilter
    ? baseVisible.filter(p => (p.persona_affinity ?? []).includes(activePersonaFilter))
    : baseVisible

  const latestUpdated = policies
    .map(p => p.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1)

  function toggleExpand(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <>
      <GuardShell>
        {/* Sub-header row */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <span style={{ fontSize: 13.5, color: "var(--text-3)" }}>
            Rules sync to every developer&apos;s machine within <strong style={{ color: "var(--text)" }}>60 seconds</strong>.
            {" "}{visiblePolicies.filter(p => p.enabled).length} active.
          </span>
          {canWrite && (
            <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button
                onClick={handleRefreshBuiltins}
                disabled={refreshing}
                className="btn btn-sm"
                style={{ opacity: refreshing ? 0.6 : 1 }}
                title="Re-sync built-in policies from latest YAML definitions"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                {refreshing ? "Refreshing…" : "Refresh built-ins"}
              </button>
              <button
                onClick={() => setShowModal(true)}
                className="btn btn-primary btn-sm"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New policy
              </button>
            </div>
          )}
        </div>

        {/* Success */}
        {successBanner && (
          <div style={{ borderRadius: 10, border: "1px solid var(--success-bd, #bbf7d0)", background: "var(--success-bg, #f0fdf4)", padding: "10px 16px", fontSize: 13, color: "var(--success, #15803d)", marginBottom: 16 }}>
            {successBanner}
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ borderRadius: 10, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="card" style={{ padding: 18, height: 96 }} />
            ))}
          </div>
        )}

        {/* Empty */}
        {!loading && !error && policies.length === 0 && (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No policies yet. Install a skill pack to get started.</p>
          </div>
        )}

        {!loading && !error && policies.length > 0 && (
          <>
            <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
            {/* Left sidebar */}
            <div style={{ width: 190, flexShrink: 0 }}>
              {/* All */}
              {(() => {
                const active = !activePackFilter
                return (
                  <button
                    onClick={() => setActivePackFilter(null)}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      width: "100%", background: active ? "var(--accent-bg, #eff6ff)" : "none",
                      border: "none", borderRadius: 8, padding: "7px 10px",
                      fontSize: 12.5, fontWeight: active ? 600 : 400,
                      color: active ? "var(--accent)" : "var(--text-3)",
                      cursor: "pointer", textAlign: "left", marginBottom: 2,
                    }}
                  >
                    <span>All</span>
                    <span style={{
                      marginLeft: 8, fontSize: 10.5,
                      background: active ? "var(--accent)" : "var(--surface-2, #f4f4f5)",
                      color: active ? "#fff" : "var(--text-muted)",
                      borderRadius: 99, padding: "1px 7px", fontWeight: 600,
                    }}>{policies.filter(p => p.enabled).length}/{policies.length}</span>
                  </button>
                )
              })()}

              {installedPacks.size > 0 && (
                <>
                  <div style={{ height: 1, background: "var(--border)", margin: "8px 4px" }} />
                  <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".08em", padding: "2px 10px 6px" }}>Skill Packs</div>
                  {PACK_LABELS.filter(p => installedPacks.has(p.id)).map(pack => {
                    const active = activePackFilter === pack.id
                    const count = policies.filter(p => p.pack_id === pack.id).length
                    return (
                      <button
                        key={pack.id}
                        onClick={() => setActivePackFilter(active ? null : pack.id)}
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          width: "100%", background: active ? "var(--accent-bg, #eff6ff)" : "none",
                          border: "none", borderRadius: 8, padding: "7px 10px",
                          fontSize: 12.5, fontWeight: active ? 600 : 400,
                          color: active ? "var(--accent)" : "var(--text-3)",
                          cursor: "pointer", textAlign: "left", marginBottom: 2,
                        }}
                      >
                        <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pack.name}</span>
                        <span style={{
                          marginLeft: 6, fontSize: 9.5, fontWeight: 700, flexShrink: 0,
                          background: "var(--accent-weak)", color: "var(--accent-text)",
                          borderRadius: 99, padding: "1px 6px",
                        }}>{count}</span>
                      </button>
                    )
                  })}
                </>
              )}
              {(() => {
                const personaDefs = [
                  { id: "conservative", label: "Conservative", emoji: "🔴" },
                  { id: "standard",     label: "Standard",     emoji: "🟡" },
                  { id: "developer",    label: "Developer",    emoji: "🟢" },
                ] as const
                const personaCounts = personaDefs.map(pd => policies.filter(p => (p.persona_affinity ?? []).includes(pd.id)).length)
                if (personaCounts.every(c => c === 0)) return null
                return (
                  <>
                    <div style={{ height: 1, background: "var(--border)", margin: "8px 4px" }} />
                    <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".08em", padding: "2px 10px 6px" }}>Persona</div>
                    {personaDefs.map(({ id, label, emoji }, idx) => {
                      const active = activePersonaFilter === id
                      const count = personaCounts[idx]
                      return (
                        <button
                          key={id}
                          onClick={() => setActivePersonaFilter(active ? null : id)}
                          style={{
                            display: "flex", alignItems: "center", justifyContent: "space-between",
                            width: "100%", background: active ? "var(--accent-bg, #eff6ff)" : "none",
                            border: "none", borderRadius: 8, padding: "7px 10px",
                            fontSize: 12.5, fontWeight: active ? 600 : 400,
                            color: active ? "var(--accent)" : "var(--text-3)",
                            cursor: "pointer", textAlign: "left", marginBottom: 2,
                          }}
                        >
                          <span>{emoji} {label}</span>
                          <span style={{
                            marginLeft: 6, fontSize: 10.5, flexShrink: 0,
                            background: active ? "var(--accent)" : "var(--surface-2, #f4f4f5)",
                            color: active ? "#fff" : "var(--text-muted)",
                            borderRadius: 99, padding: "1px 7px", fontWeight: 600,
                          }}>{count}</span>
                        </button>
                      )
                    })}
                  </>
                )
              })()}
            </div>

            {/* Right: header + 2-column card grid */}
            <div style={{ flex: 1, minWidth: 0 }}>
              {activePackFilter && (
                <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
                    {PACK_LABELS.find(p => p.id === activePackFilter)?.name ?? activePackFilter}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    — {visiblePolicies.filter(p => p.enabled).length} of {visiblePolicies.length} active
                  </span>
                </div>
              )}
            {visiblePolicies.length === 0 && (
              <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
                <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No policies match this filter.</p>
              </div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10, alignItems: "start" }}>
              {visiblePolicies.map(p => {
                const expanded = expandedIds.has(p.id)
                const hasDetails = !!(p.match_pattern || p.match_path_pattern || p.message)
                return (
                  <div
                    key={p.id}
                    className="card"
                    style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 0, opacity: p.enabled ? 1 : 0.62 }}
                  >
                    {/* Card header */}
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                      <ActionAvatar action={p.action} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", marginBottom: 4 }}>
                          <span className="mono" style={{ fontWeight: 650, fontSize: 12.5 }}>{p.rule_id}</span>
                          <ActionBadge action={p.action} />
                          {(p.builtin || p.pack_id) && (
                            <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px" }}>
                              {p.pack_id ? (PACK_LABELS.find(pl => pl.id === p.pack_id)?.name ?? p.pack_id) : "base"}
                            </span>
                          )}
                        </div>
                        <p style={{ margin: 0, fontSize: 12, color: "var(--text-3)", lineHeight: 1.45 }}>
                          {p.description || p.message || "—"}
                        </p>
                      </div>

                      {/* Right controls */}
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                        {!p.builtin && canWrite && (
                          <button
                            type="button"
                            onClick={() => {
                              if (confirmDeleteId === p.id) {
                                setConfirmDeleteId(null); setConfirmDeleteValue("")
                              } else {
                                setConfirmDeleteId(p.id); setConfirmDeleteValue("")
                              }
                            }}
                            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 3 }}
                            title="Delete rule"
                          >
                            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                              <path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35L12.95 5.5h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" />
                            </svg>
                          </button>
                        )}
                        {canWrite
                          ? <Toggle enabled={p.enabled} onChange={() => handleToggle(p.id)} />
                          : <span style={{ width: 40, height: 23, borderRadius: 20, background: p.enabled ? "var(--accent)" : "var(--border-2)", display: "inline-block", opacity: 0.5 }} />
                        }
                      </div>
                    </div>

                    {/* Footer: last triggered + persona chips + expand toggle */}
                    <div style={{ display: "flex", alignItems: "center", marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        Last hit: <strong style={{ color: "var(--text-2)" }}>{formatLastTriggered(p.last_triggered)}</strong>
                      </span>
                      {(p.persona_affinity ?? []).length > 0 && (p.persona_affinity ?? []).length < 3 && (
                        <span style={{ display: "flex", gap: 3, marginLeft: 8, alignItems: "center" }}>
                          {(p.persona_affinity ?? []).map(pa => (
                            <span key={pa} title={pa} style={{
                              fontSize: 10, background: "var(--surface-2)", borderRadius: 99,
                              padding: "1px 6px", color: "var(--text-3)", fontWeight: 500,
                            }}>
                              {pa === "conservative" ? "🔴" : pa === "standard" ? "🟡" : "🟢"} {pa}
                            </span>
                          ))}
                        </span>
                      )}
                      {hasDetails && (
                        <button
                          onClick={() => toggleExpand(p.id)}
                          style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", fontSize: 11.5, color: "var(--accent)", display: "flex", alignItems: "center", gap: 3, padding: 0 }}
                        >
                          {expanded ? "Hide details" : "Show details"}
                          <svg
                            width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                            style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform .15s" }}
                          >
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </button>
                      )}
                    </div>

                    {/* Expanded detail panel */}
                    {expanded && hasDetails && (
                      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 7 }}>
                        {p.match_tool && (
                          <div>
                            <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Applies to</span>
                            <div className="mono" style={{ fontSize: 12, color: "var(--text-2)", marginTop: 2 }}>{p.match_tool}</div>
                          </div>
                        )}
                        {p.match_pattern && (
                          <div>
                            <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Pattern</span>
                            <div className="mono" style={{ fontSize: 11.5, color: "var(--err)", marginTop: 2, wordBreak: "break-all", background: "var(--err-bg)", borderRadius: 6, padding: "4px 8px" }}>{p.match_pattern}</div>
                          </div>
                        )}
                        {p.match_path_pattern && (
                          <div>
                            <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Path pattern</span>
                            <div className="mono" style={{ fontSize: 11.5, color: "var(--warn)", marginTop: 2, wordBreak: "break-all", background: "var(--warn-bg)", borderRadius: 6, padding: "4px 8px" }}>{p.match_path_pattern}</div>
                          </div>
                        )}
                        {p.message && (
                          <div>
                            <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Developer message</span>
                            <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 2, fontStyle: "italic" }}>&ldquo;{p.message}&rdquo;</div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Delete confirm */}
                    {!p.builtin && canWrite && confirmDeleteId === p.id && (
                      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        <p style={{ margin: 0, fontSize: 11, color: "var(--err)" }}>
                          Type <strong>{p.rule_id}</strong> to confirm deletion.
                        </p>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <input
                            value={confirmDeleteValue}
                            onChange={e => setConfirmDeleteValue(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === "Enter") handleDelete(p.id)
                              if (e.key === "Escape") { setConfirmDeleteId(null); setConfirmDeleteValue("") }
                            }}
                            placeholder={p.rule_id}
                            style={{ flex: 1, minWidth: 0, fontSize: 11.5, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "6px 10px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
                          />
                          <button onClick={() => handleDelete(p.id)} disabled={confirmDeleteValue !== p.rule_id} className="btn btn-sm" style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmDeleteValue !== p.rule_id ? 0.4 : 1 }}>Confirm</button>
                          <button onClick={() => { setConfirmDeleteId(null); setConfirmDeleteValue("") }} className="btn btn-ghost btn-sm">Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Footer */}
            {policies.length > 0 && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", paddingTop: 16, paddingBottom: 8 }}>
                Policy last updated: {formatUpdatedAt(latestUpdated)} · Synced to developers
              </p>
            )}
            </div>{/* end right col */}
            </div>{/* end sidebar+grid flex */}
          </>
        )}
      </GuardShell>

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
