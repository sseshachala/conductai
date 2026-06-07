"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { SecureShell } from "../_components"
import { useWorkspace } from "@/lib/WorkspaceContext"

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

const FINDING_TYPES = ["injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "other"]
const SEVERITIES = ["critical", "high", "medium", "low", "info"]

const SEV_COLORS: Record<string, { bg: string; color: string }> = {
  critical: { bg: "#fee2e2", color: "#dc2626" },
  high:     { bg: "#fff7ed", color: "#ea580c" },
  medium:   { bg: "#fefce8", color: "#ca8a04" },
  low:      { bg: "#eff6ff", color: "#2563eb" },
  info:     { bg: "#f5f5f4", color: "#78716c" },
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <span
      onClick={onClick}
      role="switch"
      aria-checked={on}
      style={{
        width: 36, height: 21, borderRadius: 20,
        background: on ? "var(--accent)" : "var(--border-2)",
        position: "relative", cursor: "pointer", flexShrink: 0,
        transition: "background .15s", display: "inline-block",
      }}
    >
      <span style={{
        position: "absolute", top: 2.5, left: on ? 17 : 2.5,
        width: 16, height: 16, borderRadius: "50%",
        background: "#fff", transition: "left .15s",
        boxShadow: "var(--shadow-sm)",
      }} />
    </span>
  )
}

export default function SecurePoliciesPage() {
  return <AppShell><PoliciesContent /></AppShell>
}

function PoliciesContent() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [policies, setPolicies] = useState<Policy[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ rule_id: "", description: "", pattern: "", finding_type: "other", severity: "medium" })

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const wsId = activeWorkspace?.id

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
      const res = await fetch(`${base}/secure/policies?workspace_id=${wsId}`, { headers: await authHeaders() })
      if (res.ok) setPolicies(await res.json())
    } catch {}
    finally { setLoading(false) }
  }, [base, wsId, authHeaders])

  useEffect(() => { load() }, [load])

  async function togglePolicy(p: Policy) {
    if (!wsId) return
    const headers = await authHeaders()
    await fetch(`${base}/secure/policies/${p.id}?workspace_id=${wsId}`, {
      method: "PATCH", headers, body: JSON.stringify({ enabled: !p.enabled }),
    })
    setPolicies(ps => ps.map(x => x.id === p.id ? { ...x, enabled: !x.enabled } : x))
  }

  async function deletePolicy(id: string) {
    if (!wsId) return
    await fetch(`${base}/secure/policies/${id}?workspace_id=${wsId}`, {
      method: "DELETE", headers: await authHeaders(),
    })
    setPolicies(ps => ps.filter(p => p.id !== id))
  }

  async function createPolicy() {
    if (!wsId || !form.rule_id.trim() || !form.pattern.trim()) return
    setSaving(true)
    try {
      const res = await fetch(`${base}/secure/policies?workspace_id=${wsId}`, {
        method: "POST", headers: await authHeaders(), body: JSON.stringify(form),
      })
      if (res.ok) { await load(); setShowForm(false); setForm({ rule_id: "", description: "", pattern: "", finding_type: "other", severity: "medium" }) }
    } catch {}
    finally { setSaving(false) }
  }

  const builtin = policies.filter(p => p.builtin)
  const custom = policies.filter(p => !p.builtin)

  const inputStyle: React.CSSProperties = {
    fontSize: 13, padding: "7px 12px", border: "1px solid var(--border-2)",
    borderRadius: 8, background: "transparent", color: "var(--text)", outline: "none", width: "100%",
  }

  return (
    <SecureShell>

      {/* Builtin policies */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div className="eyebrow">Detection rules</div>
        <button className="btn btn-ghost btn-sm" onClick={() => setShowForm(v => !v)}>
          {showForm ? "Cancel" : "+ Add rule"}
        </button>
      </div>

      {/* Add rule form */}
      {showForm && (
        <div className="card" style={{ padding: "16px 20px", marginBottom: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Rule ID</div>
              <input style={inputStyle} value={form.rule_id} onChange={e => setForm(f => ({ ...f, rule_id: e.target.value }))} placeholder="my-custom-rule" />
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Description</div>
              <input style={inputStyle} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="What this rule detects" />
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Pattern (regex)</div>
            <input style={{ ...inputStyle, fontFamily: "ui-monospace, monospace" }} value={form.pattern} onChange={e => setForm(f => ({ ...f, pattern: e.target.value }))} placeholder={String.raw`\bHARDCODED_SECRET\b`} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 12, alignItems: "flex-end" }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Type</div>
              <select style={{ ...inputStyle, cursor: "pointer" }} value={form.finding_type} onChange={e => setForm(f => ({ ...f, finding_type: e.target.value }))}>
                {FINDING_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>Severity</div>
              <select style={{ ...inputStyle, cursor: "pointer" }} value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}>
                {SEVERITIES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase()+s.slice(1)}</option>)}
              </select>
            </div>
            <button className="btn btn-primary btn-sm" onClick={createPolicy} disabled={saving || !form.rule_id || !form.pattern}>
              {saving ? "Saving…" : "Add rule"}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card" style={{ overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "40px 160px 1fr 120px 90px 70px 40px", gap: 12, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          {["On", "Rule ID", "Pattern", "Type", "Severity", "Builtin", ""].map(h => (
            <div key={h} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: 20, fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
        ) : policies.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No policies yet.
          </div>
        ) : [...builtin, ...custom].map((p, i, arr) => {
          const sev = SEV_COLORS[p.severity] ?? SEV_COLORS.info
          return (
            <div
              key={p.id}
              style={{ display: "grid", gridTemplateColumns: "40px 160px 1fr 120px 90px 70px 40px", gap: 12, padding: "11px 20px", borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center" }}
            >
              <Toggle on={p.enabled} onClick={() => togglePolicy(p)} />
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.rule_id}>{p.rule_id}</div>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.pattern ?? undefined}>{p.pattern || p.description || "—"}</div>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>{p.finding_type}</div>
              <span style={{ display: "inline-block", padding: "2px 9px", borderRadius: 20, fontSize: 11, fontWeight: 700, background: sev.bg, color: sev.color }}>{p.severity}</span>
              {p.builtin
                ? <span style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    built-in
                  </span>
                : <span />
              }
              {!p.builtin
                ? <button
                    onClick={() => deletePolicy(p.id)}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4, borderRadius: 6 }}
                    title="Delete rule"
                    onMouseEnter={e => (e.currentTarget.style.color = "var(--err)")}
                    onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M3 6h18M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2"/>
                    </svg>
                  </button>
                : <span />
              }
            </div>
          )
        })}
      </div>

      <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 12 }}>
        Built-in rules match the fast-path classifier patterns and cannot be deleted — only disabled.
      </div>
    </SecureShell>
  )
}
