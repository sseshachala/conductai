"use client"

import { useState, useEffect, useCallback } from "react"
import { useSearchParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { POLICY_TEMPLATES } from "@/lib/guardPolicyTemplates"

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
  persona?: "agent" | "proxy"
  non_overridable?: boolean
}

const PACK_LABELS: { id: string; name: string }[] = [
  { id: "conduct-owasp", name: "OWASP Top 10" },
  { id: "conduct-soc2",    name: "SOC 2" },
  { id: "conduct-hipaa",   name: "HIPAA" },
  { id: "conduct-pci-dss", name: "PCI-DSS" },
  { id: "conduct-base",    name: "Base" },
]

// ─── Lock icon ────────────────────────────────────────────────────────────────

function LockIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ color: "var(--text-muted)", flexShrink: 0 }}
      aria-label="Non-overridable"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
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
  persona: "agent" | "proxy"
}

const EMPTY_FORM: AddRuleFormData = {
  rule_id: "",
  description: "",
  match_tool: "*",
  match_pattern: "",
  match_path_pattern: "",
  action: "block",
  message: "",
  persona: "agent",
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
  initialPersona,
}: {
  onClose: () => void
  onSubmit: (data: AddRuleFormData) => Promise<void>
  submitting: boolean
  initialPersona?: "agent" | "proxy"
}) {
  const { getToken } = useAuth()
  const [form, setForm] = useState<AddRuleFormData>({ ...EMPTY_FORM, persona: initialPersona ?? "agent" })
  const [errors, setErrors] = useState<Partial<Record<keyof AddRuleFormData, string>>>({})
  const [aiPrompt, setAiPrompt] = useState("")
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [environments, setEnvironments] = useState<Array<{ id: string; name: string }>>([])
  const [aiEnvId, setAiEnvId] = useState<string>("")

  useEffect(() => {
    async function loadEnvs() {
      try {
        const token = getToken ? await getToken() : null
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""
        const res = await fetch(`${apiUrl}/environments`, { headers })
        if (!res.ok) return
        const data: Array<{ id: string; name: string }> = await res.json()
        setEnvironments(data)
        const def = data.find(e => e.name === "Default") ?? data[0]
        if (def) setAiEnvId(def.id)
      } catch {
        // non-fatal — picker just shows empty
      }
    }
    loadEnvs()
  }, [getToken])

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
        body: JSON.stringify({ prompt: text, environment_id: aiEnvId || undefined }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail ?? `HTTP ${res.status}`)
      }
      const data = await res.json()
      setForm(prev => ({
        ...prev,
        rule_id: data.rule_id ?? "",
        description: data.description ?? "",
        match_tool: (data.match_tool as MatchTool) ?? "*",
        match_pattern: data.match_pattern ?? "",
        match_path_pattern: data.match_path_pattern ?? "",
        action: (data.action as PolicyAction) ?? "block",
        message: data.message ?? "",
      }))
      setErrors({})
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "Couldn't generate a rule — try being more specific.")
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
        background: "rgba(0,0,0,0.25)",
        zIndex: 50,
      }}
    >
      <div
        onClick={onClose}
        style={{ position: "absolute", inset: 0 }}
        aria-hidden="true"
      />
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          zIndex: 10,
          width: 480,
          maxWidth: "100vw",
          overflowY: "auto",
          background: "var(--surface)",
          boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
          borderLeft: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
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
        <form onSubmit={handleSubmit} style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>

          {/* AI generate */}
          <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={labelStyle}>Generate with AI</label>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11.5, color: "var(--text-3)" }}>Environment</span>
              <select
                value={aiEnvId}
                onChange={e => setAiEnvId(e.target.value)}
                disabled={aiGenerating || environments.length === 0}
                style={{ ...fieldStyle, flex: 1, maxWidth: 220 }}
              >
                {environments.length === 0 && <option value="">No environments</option>}
                {environments.map(env => (
                  <option key={env.id} value={env.id}>{env.name}</option>
                ))}
              </select>
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>Uses this environment's Anthropic key</span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 2 }}>
              {POLICY_TEMPLATES.map(t => (
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

          {/* Persona */}
          <div>
            <label style={labelStyle}>Persona</label>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              {(["agent", "proxy"] as const).map(p => (
                <button
                  key={p}
                  type="button"
                  onClick={() => set("persona", p)}
                  style={{
                    flex: 1, padding: "6px 0", borderRadius: 8, fontSize: 12.5, fontWeight: 500,
                    border: `1px solid ${form.persona === p ? "var(--accent)" : "var(--border)"}`,
                    background: form.persona === p ? "var(--accent-bg, #eff6ff)" : "var(--surface)",
                    color: form.persona === p ? "var(--accent)" : "var(--text-3)",
                    cursor: "pointer",
                  }}
                >
                  {p === "agent" ? "Agent" : "Proxy"}
                </button>
              ))}
            </div>
            <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--text-muted)" }}>
              Agent: rules enforced on AI tools and agents. Proxy: rules enforced at the LLM gateway.
            </p>
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
  const searchParams = useSearchParams()
  useEffect(() => {
    const p = searchParams.get("persona")
    if (p) setTimeout(() => document.getElementById(`section-${p}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 300)
  }, [searchParams])
  const { teamId, loading: teamLoading, error: teamError } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [policies, setPolicies] = useState<Policy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [modalPersona, setModalPersona] = useState<"agent" | "proxy">("agent")
  const [submitting, setSubmitting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [confirmDeleteValue, setConfirmDeleteValue] = useState("")
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [editId, setEditId] = useState<string | null>(null)
  const [editAction, setEditAction] = useState<PolicyAction>("block")
  const [editMessage, setEditMessage] = useState("")
  const [editSaving, setEditSaving] = useState(false)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""
  const canWrite = !permissionsLoading && permissions.canEditPolicies

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
        const qs = `?workspace_id=${encodeURIComponent(teamId ?? "")}`
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
        `${apiUrl}/guard/policies/reinstall-base?workspace_id=${encodeURIComponent(teamId ?? "")}`,
        { method: "POST", headers }
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // reload policies list
      const listRes = await fetch(`${apiUrl}/guard/policies?workspace_id=${encodeURIComponent(teamId ?? "")}`, { headers })
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
      const res = await fetch(`${apiUrl}/guard/policies/${id}?workspace_id=${encodeURIComponent(teamId ?? "")}`, {
        method: "PATCH", headers,
        body: JSON.stringify({ enabled: !prev.enabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch (e) {
      setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: prev.enabled } : p))
      setError(e instanceof Error ? e.message : "Failed to update rule. Please try again.")
    }
  }

  async function handleEditSave(id: string) {
    setEditSaving(true)
    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/${id}?workspace_id=${encodeURIComponent(teamId ?? "")}`, {
        method: "PATCH", headers,
        body: JSON.stringify({ action: editAction, message: editMessage || undefined }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setPolicies(ps => ps.map(p => p.id === id ? { ...p, action: editAction, message: editMessage || p.message } : p))
      setEditId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save")
    } finally {
      setEditSaving(false)
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
      const res = await fetch(`${apiUrl}/guard/policies/${id}?workspace_id=${encodeURIComponent(teamId ?? "")}`, { method: "DELETE", headers })
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
      const rule: Record<string, unknown> = {
        rule_id: formData.rule_id.trim(),
        description: formData.description.trim(),
        match_tool: formData.match_tool,
        match_pattern: formData.match_pattern.trim(),
        action: formData.action,
        message: formData.message.trim(),
        enabled: true,
        builtin: false,
        persona: formData.persona,
      }
      if (formData.match_path_pattern.trim()) rule.match_path_pattern = formData.match_path_pattern.trim()

      // Lint before saving
      const lintRes = await fetch(
        `${apiUrl}/guard/policies/lint?workspace_id=${encodeURIComponent(teamId ?? "")}`,
        { method: "POST", headers, body: JSON.stringify({ rules: [rule] }) }
      )
      if (lintRes.ok) {
        const { errors } = await lintRes.json() as { errors: { field: string; message: string }[] }
        if (errors.length > 0) {
          throw new Error(errors.map(e => `${e.field}: ${e.message}`).join(" · "))
        }
      }

      const body = { ...rule }
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

  // Split into proxy vs agent sections; old rules without `persona` default to "agent"
  const proxyPolicies = policies.filter(p => p.persona === "proxy")
  const agentPolicies = policies.filter(p => !p.persona || p.persona === "agent")

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
            {" "}{policies.filter(p => p.enabled).length} active.
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

        {/* Guard not installed */}
        {!loading && teamError && (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>ConductGuard not set up</p>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 0 }}>
              Run <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "1px 6px", borderRadius: 4 }}>conduct guard install</code> in your terminal to get started.
            </p>
          </div>
        )}

        {/* Empty */}
        {!loading && !teamError && !error && policies.length === 0 && (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No policies yet. Install a skill pack to get started.</p>
          </div>
        )}

        {!loading && !error && policies.length > 0 && (
          <>
            {/* Main content — two sections */}
            <div style={{ flex: 1, minWidth: 0 }}>
            {(() => {
              function renderCard(p: Policy) {
                const expanded = expandedIds.has(p.id)
                const hasDetails = !!(p.match_pattern || p.match_path_pattern || p.message)
                const locked = !!p.non_overridable
                return (
                  <div key={p.id} style={{ opacity: p.enabled ? 1 : 0.55 }}>
                    {/* Main row */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 12px", borderRadius: 8, background: "var(--surface)", border: "1px solid var(--border)" }}>
                      <ActionBadge action={p.action} />
                      <span className="mono" style={{ fontWeight: 650, fontSize: 12, color: "var(--text-1)", whiteSpace: "nowrap" }}>{p.rule_id}</span>
                      {locked && <LockIcon />}
                      <span style={{ flex: 1, fontSize: 12, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.description || p.message || "—"}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap", flexShrink: 0 }}>{formatLastTriggered(p.last_triggered)}</span>
                      {hasDetails && (
                        <button onClick={() => toggleExpand(p.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2, flexShrink: 0 }} title="Details">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform .15s" }}><polyline points="6 9 12 15 18 9" /></svg>
                        </button>
                      )}
                      {!locked && canWrite && p.builtin && (
                        <button type="button" onClick={() => { setEditId(editId === p.id ? null : p.id); setEditAction(p.action); setEditMessage(p.message ?? "") }} style={{ background: "none", border: "none", cursor: "pointer", color: editId === p.id ? "var(--accent)" : "var(--text-muted)", padding: 2, flexShrink: 0 }} title="Override">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                      )}
                      {!p.builtin && !locked && canWrite && (
                        <button type="button" onClick={() => { if (confirmDeleteId === p.id) { setConfirmDeleteId(null); setConfirmDeleteValue("") } else { setConfirmDeleteId(p.id); setConfirmDeleteValue("") } }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2, flexShrink: 0 }} title="Delete">
                          <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35L12.95 5.5h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" /></svg>
                        </button>
                      )}
                      {locked
                        ? <span style={{ fontSize: 10, color: "var(--text-muted)", flexShrink: 0 }}>Required</span>
                        : canWrite
                          ? <Toggle enabled={p.enabled} onChange={() => handleToggle(p.id)} />
                          : <span style={{ width: 32, height: 18, borderRadius: 20, background: p.enabled ? "var(--accent)" : "var(--border-2)", display: "inline-block", opacity: 0.5, flexShrink: 0 }} />
                      }
                    </div>

                    {/* Edit override panel */}
                    {editId === p.id && (
                      <div style={{ margin: "4px 0 4px 12px", padding: "10px 12px", background: "var(--surface-2)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <label style={{ fontSize: 11.5, color: "var(--text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>Action</label>
                          <select value={editAction} onChange={e => setEditAction(e.target.value as PolicyAction)} style={{ ...fieldStyle, width: "auto", fontSize: 12 }}>
                            <option value="block">Block</option>
                            <option value="warn">Warn</option>
                            <option value="audit">Audit</option>
                          </select>
                        </div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <label style={{ fontSize: 11.5, color: "var(--text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>Message</label>
                          <input value={editMessage} onChange={e => setEditMessage(e.target.value)} placeholder={p.message ?? "Override message (optional)"} style={{ ...fieldStyle, fontSize: 12 }} />
                        </div>
                        <div style={{ display: "flex", gap: 6 }}>
                          <button onClick={() => handleEditSave(p.id)} disabled={editSaving} className="btn btn-primary btn-sm">{editSaving ? "Saving…" : "Save override"}</button>
                          <button onClick={() => setEditId(null)} className="btn btn-ghost btn-sm">Cancel</button>
                        </div>
                      </div>
                    )}

                    {/* Expanded details */}
                    {expanded && hasDetails && (
                      <div style={{ margin: "4px 0 4px 12px", padding: "8px 12px", background: "var(--surface-2)", borderRadius: 8, display: "flex", flexWrap: "wrap", gap: 12 }}>
                        {p.match_tool && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Tool </span><span className="mono" style={{ fontSize: 11.5, color: "var(--text-2)" }}>{p.match_tool}</span></div>}
                        {p.match_pattern && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Pattern </span><span className="mono" style={{ fontSize: 11, color: "var(--err)", background: "var(--err-bg)", borderRadius: 4, padding: "1px 6px" }}>{p.match_pattern}</span></div>}
                        {p.match_path_pattern && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Path </span><span className="mono" style={{ fontSize: 11, color: "var(--warn)", background: "var(--warn-bg)", borderRadius: 4, padding: "1px 6px" }}>{p.match_path_pattern}</span></div>}
                        {p.message && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Message </span><span style={{ fontSize: 11.5, color: "var(--text-2)", fontStyle: "italic" }}>&ldquo;{p.message}&rdquo;</span></div>}
                      </div>
                    )}
                  </div>
                )
              }

              function SectionHeader({ title, description, onAdd }: { title: string; description: string; onAdd: () => void }) {
                return (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                    <div>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: "var(--text-muted)" }}>{title}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>{description}</span>
                    </div>
                    <span style={{ height: 1, flex: 1, background: "var(--border)" }} />
                    {canWrite && (
                      <button type="button" onClick={onAdd} className="btn btn-ghost btn-sm" style={{ fontSize: 11.5, padding: "3px 10px" }}>
                        + Add rule
                      </button>
                    )}
                  </div>
                )
              }

              return (
                <>
                  {/* Proxy section */}
                  <div id="section-proxy" style={{ marginBottom: 28 }}>
                    <SectionHeader
                      title="Proxy Rules"
                      description="Governs what leaves your network to the LLM provider"
                      onAdd={() => { setModalPersona("proxy"); setShowModal(true) }}
                    />
                    {proxyPolicies.length === 0
                      ? <div className="card" style={{ padding: "24px", textAlign: "center" }}><p style={{ fontSize: 12, color: "var(--text-muted)" }}>No proxy rules.</p></div>
                      : <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>{proxyPolicies.map(p => renderCard(p))}</div>
                    }
                  </div>

                  {/* Agent section */}
                  <div id="section-agent" style={{ marginBottom: 20 }}>
                    <SectionHeader
                      title="Agent Rules"
                      description="Governs what AI agents do on your machine"
                      onAdd={() => { setModalPersona("agent"); setShowModal(true) }}
                    />
                    {agentPolicies.length === 0
                      ? <div className="card" style={{ padding: "24px", textAlign: "center" }}><p style={{ fontSize: 12, color: "var(--text-muted)" }}>No agent rules.</p></div>
                      : <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>{agentPolicies.map(p => renderCard(p))}</div>
                    }
                  </div>
                </>
              )
            })()}

            {/* Footer */}
            {policies.length > 0 && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", paddingTop: 16, paddingBottom: 8 }}>
                Policy last updated: {formatUpdatedAt(latestUpdated)} · Synced to developers
              </p>
            )}
            </div>{/* end main col */}
          </>
        )}
      </GuardShell>

      {showModal && (
        <AddRuleModal
          onClose={() => setShowModal(false)}
          onSubmit={handleAddRule}
          submitting={submitting}
          initialPersona={modalPersona}
        />
      )}

      {/* Delete confirm modal */}
      {confirmDeleteId && (() => {
        const target = policies.find(p => p.id === confirmDeleteId)
        if (!target) return null
        return (
          <div
            style={{
              position: "fixed", inset: 0, zIndex: 200,
              background: "rgba(0,0,0,0.45)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
            onClick={() => { setConfirmDeleteId(null); setConfirmDeleteValue("") }}
          >
            <div
              className="card"
              style={{ width: 400, padding: "24px", display: "flex", flexDirection: "column", gap: 14 }}
              onClick={e => e.stopPropagation()}
            >
              <div>
                <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", margin: 0 }}>Delete policy</h2>
                <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 6 }}>
                  This cannot be undone. Type <strong style={{ color: "var(--err)" }}>{target.rule_id}</strong> to confirm.
                </p>
              </div>
              <input
                autoFocus
                value={confirmDeleteValue}
                onChange={e => setConfirmDeleteValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter") handleDelete(target.id)
                  if (e.key === "Escape") { setConfirmDeleteId(null); setConfirmDeleteValue("") }
                }}
                placeholder={target.rule_id}
                style={{ fontSize: 13, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "8px 12px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button onClick={() => { setConfirmDeleteId(null); setConfirmDeleteValue("") }} className="btn btn-ghost btn-sm">Cancel</button>
                <button
                  onClick={() => handleDelete(target.id)}
                  disabled={confirmDeleteValue !== target.rule_id}
                  className="btn btn-sm"
                  style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmDeleteValue !== target.rule_id ? 0.4 : 1 }}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )
      })()}
    </>
  )
}
