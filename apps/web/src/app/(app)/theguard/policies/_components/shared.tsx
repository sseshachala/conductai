"use client"

import { useState } from "react"
import type { GuardPolicy, GuardPolicyAction, GuardPolicyPatch, RuleFire } from "@/lib/api/guard"

// ─── Types ────────────────────────────────────────────────────────────────────

export type PolicyAction = GuardPolicyAction
export type Policy = GuardPolicy

// #1141: legacy rows stored with action:"inject" surface as audit + guidance.
// Mirrors backend _build_rules migration so the UI never renders "inject".
export function normalizePolicy(p: Policy): Policy {
  if ((p.action as string) === "inject") {
    return { ...p, action: "audit", inject_guidance: true }
  }
  return p
}
export type MatchTool = "shell" | "filesystem-write" | "filesystem-read" | "network" | "*"

export const ACTION_RESTRICTIVENESS: Record<PolicyAction, number> = {
  audit: 1,
  warn: 3,
  approval: 4,
  block: 5,
}

export const PACK_LABELS: { id: string; name: string }[] = [
  { id: "conduct-owasp", name: "OWASP Top 10" },
  { id: "conduct-soc2",    name: "SOC 2" },
  { id: "conduct-hipaa",   name: "HIPAA" },
  { id: "conduct-pci-dss", name: "PCI-DSS" },
  { id: "conduct-base",    name: "Base" },
]

// ─── Lock icon ────────────────────────────────────────────────────────────────

export function LockIcon() {
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

export function ActionAvatar({ action }: { action: PolicyAction }) {
  const styles: Record<PolicyAction, { bg: string; color: string }> = {
    block:    { bg: "var(--err-bg)",  color: "var(--err)"  },
    warn:     { bg: "var(--warn-bg)", color: "var(--warn)" },
    audit:    { bg: "var(--info-bg)", color: "var(--info)" },
    approval: { bg: "var(--info-bg)", color: "var(--info)" },
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
    // audit / approval
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

export const ACTION_BADGE_TONE: Record<PolicyAction, string> = {
  block:    "err",
  warn:     "warn",
  audit:    "info",
  approval: "info",
}

export function ActionBadge({ action }: { action: PolicyAction }) {
  const tone = ACTION_BADGE_TONE[action] ?? "info"
  return (
    <span className={`sbadge ${tone}`} style={{ textTransform: "uppercase", fontSize: 9.5, letterSpacing: ".06em" }}>
      {action}
    </span>
  )
}

// ─── Gates ────────────────────────────────────────────────────────────────────
// #1733/#1750 Phase B — locked enum [action, prompt, response]. Shows *where*
// a rule fires: `action` = MCP tool call; `prompt` = outbound LLM proxy;
// `response` = inbound LLM proxy.

export type Gate = "action" | "prompt" | "response"

export const ALL_GATES: readonly Gate[] = ["action", "prompt", "response"] as const

export const GATE_TONE: Record<Gate, string> = {
  action:   "info",
  prompt:   "warn",
  response: "ok",
}

export function GateChips({ gates }: { gates?: string[] | null }) {
  const list = (gates && gates.length ? gates : ["action"]).filter((g): g is Gate =>
    (ALL_GATES as readonly string[]).includes(g),
  )
  if (!list.length) return null
  return (
    <span style={{ display: "inline-flex", gap: 3, flexShrink: 0 }}>
      {list.map((g) => (
        <span
          key={g}
          className={`sbadge ${GATE_TONE[g]}`}
          style={{ textTransform: "uppercase", fontSize: 9, letterSpacing: ".06em", padding: "0 5px" }}
          title={`Fires at ${g} gate`}
        >
          {g}
        </span>
      ))}
    </span>
  )
}

// ─── SurfaceBadges (#1755 Slice 2) ─────────────────────────────────────────
// Per-PEP verification chips: green when the PEP can enforce the rule, muted
// when not_supported. Sourced from PolicyOut.derived_<surface> (backend
// derives from rule.gates × PEP_CAPABILITIES). Falls back to muted when the
// backend hasn't populated the field yet (never breaks the row).

export type SurfaceStatus = "hard" | "not_supported"
export const SURFACES: readonly { key: string; label: string }[] = [
  { key: "mcp",     label: "MCP" },
  { key: "proxy",   label: "Gateway" },
  { key: "runtime", label: "Runtime" },
  { key: "hook",    label: "Hook" },
] as const

export function _normalizeStatus(v?: string | null): SurfaceStatus {
  return v === "hard" ? "hard" : "not_supported"
}

export function SurfaceBadges({ policy }: { policy: Policy }) {
  const statuses: Record<string, SurfaceStatus> = {
    mcp:     _normalizeStatus(policy.derived_mcp),
    proxy:   _normalizeStatus(policy.derived_proxy),
    runtime: _normalizeStatus(policy.derived_runtime),
    hook:    _normalizeStatus(policy.derived_hook),
  }
  return (
    <span style={{ display: "inline-flex", gap: 3, flexShrink: 0 }} title="PEP surfaces that can enforce this rule (green = hard)">
      {SURFACES.map(({ key, label }) => {
        const status = statuses[key]
        const isHard = status === "hard"
        return (
          <span
            key={key}
            className={`sbadge ${isHard ? "ok" : ""}`}
            style={{
              textTransform: "uppercase",
              fontSize: 9,
              letterSpacing: ".06em",
              padding: "0 5px",
              opacity: isHard ? 1 : 0.35,
              color: isHard ? undefined : "var(--text-muted)",
              background: isHard ? undefined : "var(--surface-2)",
              border: isHard ? undefined : "1px solid var(--border)",
            }}
            title={`${label} PEP: ${status}`}
          >
            {label}
          </span>
        )
      })}
    </span>
  )
}

// ─── RuleFiresPanel (#1755 Slice 2) ───────────────────────────────────────
// Shows the last N events that fired this rule. Server projects through
// redact_secrets — raw input_summary NEVER lands here (Property 9). The
// panel renders a redacted preview + short sha256 prefix + byte size so
// consumers can dedupe / spot volume without needing the payload.

export function _formatFireTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toISOString().replace("T", " ").replace(/\..*/, "")
  } catch {
    return iso
  }
}

export function RuleFiresPanel({ state }: { state?: { loading: boolean; fires: RuleFire[]; error?: string } }) {
  if (!state) return null
  if (state.loading) {
    return (
      <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontStyle: "italic" }}>
        Loading recent firings…
      </div>
    )
  }
  if (state.error) {
    return (
      <div style={{ fontSize: 11.5, color: "var(--err)" }}>
        Could not load firings: {state.error}
      </div>
    )
  }
  if (state.fires.length === 0) {
    return (
      <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontStyle: "italic" }}>
        No recent firings for this rule.
      </div>
    )
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {state.fires.map(fire => (
        <div key={fire.id} style={{ display: "flex", flexDirection: "column", gap: 2, padding: "4px 8px", background: "var(--surface)", borderRadius: 5, border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11, color: "var(--text-2)" }}>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
              {_formatFireTime(fire.ts)}
            </span>
            <span className={`sbadge ${fire.decision === "blocked" ? "err" : fire.decision === "warned" ? "warn" : "info"}`} style={{ textTransform: "uppercase", fontSize: 9, letterSpacing: ".06em", padding: "0 5px" }}>
              {fire.decision}
            </span>
            <span style={{ color: "var(--text-muted)" }}>{fire.ai_tool}</span>
            {fire.tool_call && (
              <span className="mono" style={{ color: "var(--text-muted)" }}>{fire.tool_call}</span>
            )}
            <span style={{ marginLeft: "auto", color: "var(--text-muted)", fontSize: 10 }}>
              {fire.input_size_bytes} B
              {fire.input_hash_prefix && (
                <>
                  {" · "}
                  <span className="mono">sha256:{fire.input_hash_prefix}…</span>
                </>
              )}
            </span>
          </div>
          {fire.input_summary_redacted && (
            <div className="mono" style={{ fontSize: 11, color: "var(--text-2)", background: "var(--surface-2)", borderRadius: 4, padding: "2px 6px", wordBreak: "break-all" }}>
              {fire.input_summary_redacted}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Toggle ───────────────────────────────────────────────────────────────────

export function Toggle({ enabled, onChange }: { enabled: boolean; onChange: () => void }) {
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

export function formatLastTriggered(val: string | null | undefined): string {
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

export function formatUpdatedAt(iso: string | undefined): string {
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

export function formatExceptionExpiry(iso: string | null | undefined): string {
  if (!iso) return "No expiry recorded"
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

export function defaultExpiryValue(): string {
  const date = new Date(Date.now() + 24 * 60 * 60 * 1000)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export function minimumExpiryValue(): string {
  const date = new Date(Date.now() + 60_000)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export interface PolicyExceptionRequest {
  policyId: string
  patch: GuardPolicyPatch
  title: string
  description: string
  closeEditor?: boolean
}

export function PolicyExceptionModal({
  request,
  submitting,
  onClose,
  onSubmit,
}: {
  request: PolicyExceptionRequest
  submitting: boolean
  onClose: () => void
  onSubmit: (reason: string, expiresAt: string) => Promise<void>
}) {
  const [reason, setReason] = useState("")
  const [expiry, setExpiry] = useState(defaultExpiryValue)
  const [minimumExpiry] = useState(minimumExpiryValue)
  const [errors, setErrors] = useState<{ reason?: string; expiry?: string; submit?: string }>({})

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const next: typeof errors = {}
    const trimmedReason = reason.trim()
    const expiryDate = new Date(expiry)
    if (!trimmedReason) next.reason = "Explain why this temporary exception is needed."
    if (!expiry || Number.isNaN(expiryDate.getTime())) {
      next.expiry = "Choose a valid expiry date and time."
    } else if (expiryDate.getTime() <= Date.now()) {
      next.expiry = "Expiry must be in the future."
    }
    if (next.reason || next.expiry) {
      setErrors(next)
      return
    }

    setErrors({})
    try {
      await onSubmit(trimmedReason, expiryDate.toISOString())
    } catch (err) {
      setErrors({ submit: err instanceof Error ? err.message : "Failed to save the exception." })
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 210,
        background: "rgba(0,0,0,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <form
        className="card"
        onSubmit={handleSubmit}
        onClick={e => e.stopPropagation()}
        style={{ width: 440, maxWidth: "100%", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}
      >
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", margin: 0 }}>{request.title}</h2>
          <p style={{ fontSize: 13, lineHeight: 1.5, color: "var(--text-3)", margin: "6px 0 0" }}>
            {request.description}
          </p>
        </div>
        <div>
          <label style={labelStyle}>Reason <span style={{ color: "var(--err)" }}>*</span></label>
          <textarea
            autoFocus
            value={reason}
            onChange={e => { setReason(e.target.value); setErrors(prev => ({ ...prev, reason: undefined, submit: undefined })) }}
            placeholder="Why is this exception required?"
            rows={3}
            style={{ ...(errors.reason ? fieldErrStyle : fieldStyle), resize: "vertical" }}
          />
          {errors.reason && <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--err)" }}>{errors.reason}</p>}
        </div>
        <div>
          <label style={labelStyle}>Expires <span style={{ color: "var(--err)" }}>*</span></label>
          <input
            type="datetime-local"
            value={expiry}
            min={minimumExpiry}
            onChange={e => { setExpiry(e.target.value); setErrors(prev => ({ ...prev, expiry: undefined, submit: undefined })) }}
            style={errors.expiry ? fieldErrStyle : fieldStyle}
          />
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-muted)" }}>
            Entered in your local timezone; it will be stored with timezone information.
          </p>
          {errors.expiry && <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--err)" }}>{errors.expiry}</p>}
        </div>
        {errors.submit && <p style={{ margin: 0, fontSize: 11.5, color: "var(--err)" }}>{errors.submit}</p>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" onClick={onClose} disabled={submitting} className="btn btn-ghost btn-sm">Cancel</button>
          <button type="submit" disabled={submitting} className="btn btn-primary btn-sm">
            {submitting ? "Saving…" : "Save temporary exception"}
          </button>
        </div>
      </form>
    </div>
  )
}

// Shared field styles
export const fieldStyle: React.CSSProperties = {
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

export const fieldErrStyle: React.CSSProperties = {
  ...fieldStyle,
  borderColor: "var(--err-bd)",
}

export const fieldMonoStyle: React.CSSProperties = {
  ...fieldStyle,
  fontFamily: "var(--font-mono, monospace)",
}

export const fieldMonoErrStyle: React.CSSProperties = {
  ...fieldMonoStyle,
  borderColor: "var(--err-bd)",
}

export const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 11.5,
  fontWeight: 500,
  color: "var(--text-2)",
  marginBottom: 4,
}
