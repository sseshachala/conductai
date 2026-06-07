"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell, SEVERITY_STYLES } from "../_components"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface Policy {
  id: string
  rule_id: string
  description: string | null
  pattern: string | null
  finding_type: string
  severity: string
  enabled: boolean
  builtin: boolean
}

// ─── Category mapping ─────────────────────────────────────────────────────────

const RULE_CATEGORIES: Record<string, string> = {
  "secret-sk-key":      "Secrets & Credentials",
  "secret-gh-pat":      "Secrets & Credentials",
  "secret-aws-key":     "Secrets & Credentials",
  "secret-password":    "Secrets & Credentials",
  "secret-api-key":     "Secrets & Credentials",
  "secret-stripe":      "Secrets & Credentials",
  "secret-slack":       "Secrets & Credentials",
  "secret-private-key": "Secrets & Credentials",
  "path-traversal":          "Path Traversal",
  "path-traversal-encoded":  "Path Traversal",
  "code-eval":      "Injection Attacks",
  "cmd-injection":  "Injection Attacks",
  "sql-injection":  "Injection Attacks",
  "ssl-cert-none":    "Crypto Issues",
  "tls-verify-false": "Crypto Issues",
  "weak-hash-md5":    "Crypto Issues",
  "weak-hash-sha1":   "Crypto Issues",
}

const CATEGORY_ORDER = [
  "Secrets & Credentials",
  "Injection Attacks",
  "Path Traversal",
  "Crypto Issues",
  "Custom Rules",
]

function categoryFor(rule_id: string): string {
  return RULE_CATEGORIES[rule_id] ?? "Custom Rules"
}

// ─── Severity avatar ──────────────────────────────────────────────────────────

function SeverityAvatar({ severity }: { severity: string }) {
  const key = severity as keyof typeof SEVERITY_STYLES
  const s = SEVERITY_STYLES[key] ?? SEVERITY_STYLES.info

  const Icon = () => {
    if (severity === "critical" || severity === "high") {
      return (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      )
    }
    if (severity === "medium") {
      return (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      )
    }
    // low / info
    return (
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
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

// ─── Severity pill ────────────────────────────────────────────────────────────

function SeverityPill({ severity }: { severity: string }) {
  const key = severity as keyof typeof SEVERITY_STYLES
  const s = SEVERITY_STYLES[key] ?? SEVERITY_STYLES.info
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "2px 9px", borderRadius: 20,
      fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

// ─── Field styles ─────────────────────────────────────────────────────────────

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

// ─── Add rule modal ───────────────────────────────────────────────────────────

interface AddRuleFormData {
  rule_id: string
  description: string
  pattern: string
  finding_type: string
  severity: string
}

const EMPTY_FORM: AddRuleFormData = {
  rule_id: "",
  description: "",
  pattern: "",
  finding_type: "other",
  severity: "medium",
}

const FINDING_TYPES = ["injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "other"]
const SEVERITIES = ["critical", "high", "medium", "low", "info"]

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
    if (!form.pattern.trim()) next.pattern = "Required"
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    await onSubmit(form)
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

          {/* Rule ID */}
          <div>
            <label style={labelStyle}>
              Rule ID <span style={{ color: "var(--err)" }}>*</span>
            </label>
            <input
              type="text"
              value={form.rule_id}
              onChange={e => set("rule_id", e.target.value)}
              placeholder="my-custom-rule"
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
              placeholder="What this rule detects"
              style={fieldStyle}
            />
          </div>

          {/* Pattern */}
          <div>
            <label style={labelStyle}>
              Pattern (regex) <span style={{ color: "var(--err)" }}>*</span>
            </label>
            <input
              type="text"
              value={form.pattern}
              onChange={e => set("pattern", e.target.value)}
              placeholder={String.raw`\bHARDCODED_SECRET\b`}
              style={errors.pattern ? fieldMonoErrStyle : fieldMonoStyle}
            />
            {errors.pattern && (
              <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--err)" }}>{errors.pattern}</p>
            )}
          </div>

          {/* Finding type + Severity */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Finding type</label>
              <select
                value={form.finding_type}
                onChange={e => set("finding_type", e.target.value)}
                style={fieldStyle}
              >
                {FINDING_TYPES.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Severity</label>
              <select
                value={form.severity}
                onChange={e => set("severity", e.target.value)}
                style={fieldStyle}
              >
                {SEVERITIES.map(s => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Footer actions */}
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

export default function SecurePoliciesPage() {
  return <AppShell><PoliciesContent /></AppShell>
}

function PoliciesContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [policies, setPolicies] = useState<Policy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [confirmDeleteValue, setConfirmDeleteValue] = useState("")

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const wsId = activeWorkspace?.id

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) {
      const t = await getToken()
      if (t) headers["Authorization"] = `Bearer ${t}`
    }
    return headers
  }, [getToken])

  useEffect(() => {
    async function load() {
      if (!wsId) { setLoading(false); return }
      setLoading(true)
      setError(null)
      try {
        const headers = await authHeaders()
        const res = await fetch(`${base}/secure/policies?workspace_id=${encodeURIComponent(wsId)}`, { headers })
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
  }, [base, authHeaders, wsId])

  async function handleToggle(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev || !wsId) return
    setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: !p.enabled } : p))
    try {
      const headers = await authHeaders()
      const res = await fetch(`${base}/secure/policies/${id}?workspace_id=${encodeURIComponent(wsId)}`, {
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
    if (!prev || prev.builtin || !wsId) return
    if (confirmDeleteValue !== prev.rule_id) return
    setConfirmDeleteId(null)
    setConfirmDeleteValue("")
    setPolicies(ps => ps.filter(p => p.id !== id))
    try {
      const headers = await authHeaders()
      const res = await fetch(`${base}/secure/policies/${id}?workspace_id=${encodeURIComponent(wsId)}`, {
        method: "DELETE", headers,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch {
      setPolicies(ps => [...ps, prev].sort((a, b) => a.rule_id.localeCompare(b.rule_id)))
    }
  }

  async function handleAddRule(formData: AddRuleFormData) {
    if (!wsId) return
    setSubmitting(true)
    try {
      const headers = await authHeaders()
      const body = {
        rule_id: formData.rule_id.trim(),
        description: formData.description.trim() || null,
        pattern: formData.pattern.trim(),
        finding_type: formData.finding_type,
        severity: formData.severity,
        enabled: true,
        builtin: false,
      }
      const res = await fetch(`${base}/secure/policies?workspace_id=${encodeURIComponent(wsId)}`, {
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

  return (
    <>
      <SecureShell>
        {/* Sub-header row */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <span style={{ fontSize: 13.5, color: "var(--text-3)" }}>
            Detection rules applied to every Claude Code session.
            {" "}{policies.filter(p => p.enabled).length} active.
          </span>
          <button
            onClick={() => setShowModal(true)}
            className="btn btn-primary btn-sm"
            style={{ marginLeft: "auto" }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New rule
          </button>
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              borderRadius: 10,
              border: "1px solid var(--err-bd)",
              background: "var(--err-bg)",
              padding: "10px 16px",
              fontSize: 13,
              color: "var(--err)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
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
                    flexDirection: "column",
                    gap: 10,
                    opacity: p.enabled ? 1 : 0.62,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    <SeverityAvatar severity={p.severity} />

                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 3 }}>
                        <span className="mono" style={{ fontWeight: 650, fontSize: 13.5 }}>{p.rule_id}</span>
                        <SeverityPill severity={p.severity} />
                        {/* Finding type badge */}
                        <span style={{
                          display: "inline-flex", alignItems: "center",
                          padding: "2px 8px", borderRadius: 20,
                          fontSize: 10.5, fontWeight: 600,
                          background: "var(--surface-2)", color: "var(--text-3)",
                          whiteSpace: "nowrap",
                        }}>
                          {p.finding_type}
                        </span>
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>
                        {p.description || "—"}
                      </div>
                    </div>

                    {/* Pattern preview */}
                    {p.pattern && (
                      <div
                        className="mono"
                        style={{
                          fontSize: 11.5,
                          color: "var(--text-muted)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          maxWidth: 200,
                          flexShrink: 0,
                        }}
                        title={p.pattern}
                      >
                        {p.pattern}
                      </div>
                    )}

                    {/* Builtin lock OR delete button */}
                    {p.builtin ? (
                      <span
                        style={{ color: "var(--border-2)", flexShrink: 0 }}
                        title="Built-in rule — cannot be deleted"
                      >
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                          <path fillRule="evenodd" d="M8 1a3 3 0 0 0-3 3v1H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1V4a3 3 0 0 0-3-3Zm0 1.5A1.5 1.5 0 0 1 9.5 4v1h-3V4A1.5 1.5 0 0 1 8 2.5Z" clipRule="evenodd" />
                        </svg>
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          if (confirmDeleteId === p.id) {
                            setConfirmDeleteId(null)
                            setConfirmDeleteValue("")
                          } else {
                            setConfirmDeleteId(p.id)
                            setConfirmDeleteValue("")
                          }
                        }}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4, flexShrink: 0 }}
                        title="Delete rule"
                        aria-label={`Delete rule ${p.rule_id}`}
                      >
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                          <path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35L12.95 5.5h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" />
                        </svg>
                      </button>
                    )}

                    {/* Toggle */}
                    <Toggle enabled={p.enabled} onChange={() => handleToggle(p.id)} />
                  </div>

                  {/* Confirm delete row — custom rules only */}
                  {!p.builtin && confirmDeleteId === p.id && (
                    <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
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
                          style={{
                            flex: 1, minWidth: 0, fontSize: 11.5,
                            border: "1px solid var(--err-bd, #fecaca)",
                            borderRadius: 8, padding: "6px 10px", outline: "none",
                            background: "var(--surface)", color: "var(--text)",
                          }}
                        />
                        <button
                          onClick={() => handleDelete(p.id)}
                          disabled={confirmDeleteValue !== p.rule_id}
                          className="btn btn-sm"
                          style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmDeleteValue !== p.rule_id ? 0.4 : 1 }}
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => { setConfirmDeleteId(null); setConfirmDeleteValue("") }}
                          className="btn btn-ghost btn-sm"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}

        {/* Footer note */}
        {!loading && !error && policies.length > 0 && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", paddingBottom: 8 }}>
            Built-in rules match fast-path classifier patterns and cannot be deleted — only disabled.
          </p>
        )}
      </SecureShell>

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
