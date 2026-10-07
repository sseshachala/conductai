"use client"

import { useState } from "react"
import type { MatchTool, PolicyAction } from "./shared"
import { fieldStyle, fieldMonoStyle, fieldMonoErrStyle, labelStyle } from "./shared"

// ─── Add rule modal ───────────────────────────────────────────────────────────

export const AI_SURFACES = [
  { value: "claude-code",    label: "Claude Code" },
  { value: "claude-ai",     label: "Claude.ai" },
  { value: "claude-desktop", label: "Claude Desktop" },
  { value: "codex-cli",     label: "Codex CLI" },
  { value: "codex-desktop", label: "Codex Desktop" },
  { value: "openai-chatgpt", label: "ChatGPT" },
  { value: "cursor",        label: "Cursor" },
  { value: "windsurf",      label: "Windsurf" },
]

// Template picker — 6 starter scenarios
export interface RuleTemplate {
  label: string
  description: string
  hint: string
  form: Partial<AddRuleFormData>
}

export const RULE_TEMPLATES: RuleTemplate[] = [
  {
    label: "Block shell from chat surfaces",
    description: "Prevent AI chat tools from running shell commands",
    hint: "Claude.ai, ChatGPT, and Claude Desktop should never run shell commands",
    form: {
      description: "Block shell commands from chat surfaces",
      persona: "agent",
      match_tool: "shell",
      match_ai_tool: "claude-ai,claude-desktop,openai-chatgpt",
      match_pattern: ".*",
      action: "block",
      message: "Shell commands are not permitted from chat surfaces. Use Claude Code or Cursor instead.",
    },
  },
  {
    label: "Warn on production deploys",
    description: "Flag any AI-triggered deploy to production",
    hint: "Catch deploys before they go live",
    form: {
      description: "Warn on production deploys",
      persona: "agent",
      match_tool: "shell",
      match_pattern: "deploy.*(prod|production)|vercel.*--prod|railway.*prod",
      action: "warn",
      message: "Production deploy triggered by AI agent — verify this is intentional.",
    },
  },
  {
    label: "Block .env file reads",
    description: "Prevent AI from reading secret files",
    hint: "AI should never access .env files directly",
    form: {
      description: "Block reading .env files",
      persona: "agent",
      match_tool: "*",
      match_pattern: "\\.env(\\b|$)",
      action: "block",
      message: ".env files contain secrets. Use your secrets manager instead.",
    },
  },
  {
    label: "Block force push",
    description: "Prevent AI from rewriting git history",
    hint: "Force push can destroy teammates' work",
    form: {
      description: "Block git force push",
      persona: "agent",
      match_tool: "shell",
      match_pattern: "git\\s+push\\s+(--force|-f)\\b",
      action: "block",
      message: "Force push blocked. Coordinate with your team before rewriting history.",
    },
  },
  {
    label: "Warn on hardcoded secrets",
    description: "Catch secrets written into code files",
    hint: "API keys and passwords should never be hardcoded",
    form: {
      description: "Warn when AI writes hardcoded secrets",
      persona: "agent",
      match_tool: "filesystem-write",
      match_pattern: "(API_KEY|SECRET|PASSWORD|TOKEN)\\s*=\\s*['\"][A-Za-z0-9+/]{16,}",
      action: "warn",
      message: "Possible hardcoded secret in generated code. Use environment variables.",
    },
  },
  {
    label: "Audit writes to production paths",
    description: "Log all AI writes to production config files",
    hint: "Silent audit trail for production file changes",
    form: {
      description: "Audit writes to production configuration",
      persona: "agent",
      match_tool: "filesystem-write",
      match_path_pattern: "(/prod/|/production/|\\.env\\.prod|render\\.yaml|vercel\\.json|Dockerfile)",
      match_pattern: ".*",
      action: "audit",
      message: "Write to production configuration detected — logged for audit trail.",
    },
  },
]

// Slugify a description into a rule ID
export function toRuleId(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60)
}

export interface AddRuleFormData {
  rule_id: string
  description: string
  match_tool: MatchTool
  match_ai_tool: string
  match_pattern: string
  match_path_pattern: string
  action: PolicyAction
  inject_guidance: boolean
  guidance: string
  message: string
  // Legacy value ``proxy`` stays accepted on read; new writes use ``gateway``.
  persona: "agent" | "proxy" | "gateway"
}

export const EMPTY_FORM: AddRuleFormData = {
  rule_id: "",
  description: "",
  match_tool: "*",
  match_ai_tool: "",
  match_pattern: "",
  match_path_pattern: "",
  action: "block",
  inject_guidance: false,
  guidance: "",
  message: "",
  persona: "agent",
}


export function AddRuleModal({
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
  const [view, setView] = useState<"templates" | "form">("templates")
  const [form, setForm] = useState<AddRuleFormData>({ ...EMPTY_FORM, persona: initialPersona ?? "agent" })
  const [guidanceReviewed, setGuidanceReviewed] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<keyof AddRuleFormData, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)

  function set<K extends keyof AddRuleFormData>(key: K, value: AddRuleFormData[K]) {
    setForm(prev => {
      const next = { ...prev, [key]: value }
      // auto-generate rule_id from description unless user has manually edited it
      if (key === "description") {
        next.rule_id = toRuleId(value as string)
      }
      return next
    })
    setErrors(prev => ({ ...prev, [key]: undefined }))
  }

  function applyTemplate(t: RuleTemplate) {
    setForm({ ...EMPTY_FORM, persona: initialPersona ?? "agent", ...t.form, rule_id: toRuleId(t.form.description ?? "") })
    setErrors({})
    setView("form")
  }

  function validate(): boolean {
    const next: Partial<Record<keyof AddRuleFormData, string>> = {}
    if (!form.match_pattern.trim()) next.match_pattern = "Required"
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    // ensure rule_id is set — fallback to pattern-based slug
    const finalForm = {
      ...form,
      rule_id: form.rule_id.trim() || toRuleId(form.description || form.match_pattern),
    }
    setSubmitError(null)
    try {
      await onSubmit(finalForm)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to add rule. Please try again.")
    }
  }

  const drawerShell = (children: React.ReactNode, title: string) => (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.25)", zIndex: 50 }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} aria-hidden="true" />
      <div style={{
        position: "absolute", top: 0, right: 0, bottom: 0, zIndex: 10,
        width: 480, maxWidth: "100vw", overflowY: "auto",
        background: "var(--surface)", boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
        borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column",
      }}>
        <div style={{
          padding: "16px 24px", borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {view === "form" && (
              <button type="button" onClick={() => setView("templates")} style={{
                background: "none", border: "none", cursor: "pointer", padding: "2px 4px",
                fontSize: 13, color: "var(--text-muted)", lineHeight: 1,
              }}>←</button>
            )}
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{title}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" style={{
            background: "none", border: "none", cursor: "pointer",
            fontSize: 17, lineHeight: 1, color: "var(--text-muted)", padding: 2,
          }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )

  // ── Step 1: template picker ──────────────────────────────────────────────
  if (view === "templates") {
    return drawerShell(
      <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-3)" }}>
          Pick a starting point or build from scratch.
        </p>
        {RULE_TEMPLATES.map(t => (
          <button
            key={t.label}
            type="button"
            onClick={() => applyTemplate(t)}
            style={{
              textAlign: "left", padding: "12px 14px", borderRadius: 10, cursor: "pointer",
              border: "1px solid var(--border)", background: "var(--surface)",
              display: "flex", flexDirection: "column", gap: 3,
              transition: "border-color .15s, background .15s",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)" }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)" }}
          >
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{t.label}</span>
            <span style={{ fontSize: 11.5, color: "var(--text-3)" }}>{t.hint}</span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => { setForm({ ...EMPTY_FORM, persona: initialPersona ?? "agent" }); setView("form") }}
          style={{
            marginTop: 4, textAlign: "left", padding: "12px 14px", borderRadius: 10, cursor: "pointer",
            border: "1px dashed var(--border)", background: "transparent",
            fontSize: 13, fontWeight: 500, color: "var(--text-3)",
          }}
        >
          Custom rule — start from scratch
        </button>
      </div>,
      "New policy rule"
    )
  }

  // ── Step 2: form ─────────────────────────────────────────────────────────
  return drawerShell(
    <form onSubmit={handleSubmit} style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>

      {/* Enforces on — renamed persona */}
      <div>
        <label style={labelStyle}>Enforces on</label>
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          {([
            { value: "agent", label: "Agent", hint: "bash, file writes, web requests" },
            { value: "proxy", label: "Gateway", hint: "what gets sent to the model" },
          ] as const).map(p => (
            <button
              key={p.value}
              type="button"
              onClick={() => set("persona", p.value)}
              style={{
                flex: 1, padding: "8px 0", borderRadius: 8, fontSize: 12.5, fontWeight: 500,
                border: `1px solid ${form.persona === p.value ? "var(--accent)" : "var(--border)"}`,
                background: form.persona === p.value ? "var(--accent-bg, #eff6ff)" : "var(--surface)",
                color: form.persona === p.value ? "var(--accent)" : "var(--text-3)",
                cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
              }}
            >
              <span>{p.label}</span>
              <span style={{ fontSize: 10.5, fontWeight: 400, opacity: 0.7 }}>{p.hint}</span>
            </button>
          ))}
        </div>
      </div>

      {/* What to detect */}
      <div>
        <label style={labelStyle}>
          What to detect <span style={{ color: "var(--err)" }}>*</span>
          <span style={{
            marginLeft: 6, fontSize: 10, fontWeight: 600, padding: "1px 6px",
            borderRadius: 4, background: "var(--surface-2)", color: "var(--text-3)",
            border: "1px solid var(--border)", verticalAlign: "middle",
          }}>regex</span>
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

      {/* When AI uses + What to do */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <label style={labelStyle}>When AI uses</label>
          <select value={form.match_tool} onChange={e => set("match_tool", e.target.value as MatchTool)} style={fieldStyle}>
            <option value="*">Any tool</option>
            <option value="shell">Shell — bash, terminal</option>
            <option value="filesystem-write">File write — edit, write</option>
            <option value="filesystem-read">File read — read, grep</option>
            <option value="network">Network — fetch, curl</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>What to do</label>
          <select value={form.action} onChange={e => set("action", e.target.value as PolicyAction)} style={fieldStyle}>
            <option value="block">Block</option>
            <option value="approval">Require approval</option>
            <option value="warn">Warn</option>
            <option value="audit">Audit</option>
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 12, color: "var(--text-2)", cursor: "pointer" }}>
            <input type="checkbox" checked={form.inject_guidance} onChange={e => { set("inject_guidance", e.target.checked); if (e.target.checked) setGuidanceReviewed(false) }} style={{ margin: 0 }} />
            Also inject guidance to model <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(rule message becomes a system-prompt safety net)</span>
          </label>
          {form.inject_guidance && !guidanceReviewed && (
            <div style={{ marginTop: 8, padding: "10px 12px", background: "var(--surface-2)", borderRadius: 8, borderLeft: "3px solid var(--warn)", fontSize: 12, color: "var(--text-2)" }}>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>Guidance to model</div>
              <div style={{ color: "var(--text-muted)", marginBottom: 6 }}>
                Prepended to the model&apos;s system prompt. Write model-directed text (imperative, one paragraph) — distinct from the human-facing message.
              </div>
              <textarea
                value={form.guidance || form.message}
                onChange={e => set("guidance", e.target.value)}
                rows={4}
                placeholder="e.g. Do not echo any PII verbatim. Refer to individuals by role only."
                style={{ ...fieldStyle, fontFamily: "var(--font-mono, monospace)", fontSize: 12, marginBottom: 8 }}
              />
              <div style={{ display: "flex", gap: 6 }}>
                <button type="button" onClick={() => { if (!form.guidance) set("guidance", form.message); setGuidanceReviewed(true) }} className="btn btn-primary btn-sm">Confirm guidance</button>
                <button type="button" onClick={() => { set("inject_guidance", false); set("guidance", ""); setGuidanceReviewed(false) }} className="btn btn-ghost btn-sm">Cancel</button>
              </div>
            </div>
          )}
          {form.inject_guidance && guidanceReviewed && (
            <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "var(--ok)" }}>
              <span>✓ Guidance reviewed</span>
              <button type="button" onClick={() => setGuidanceReviewed(false)} className="btn btn-ghost btn-sm" style={{ padding: "0 6px", fontSize: 11 }}>Edit</button>
            </div>
          )}
        </div>
      </div>

      {/* Only on these surfaces */}
      <div>
        <label style={labelStyle}>Only on these surfaces <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(leave blank for all)</span></label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
          {AI_SURFACES.map(s => {
            const selected = form.match_ai_tool.split(",").map(v => v.trim()).filter(Boolean).includes(s.value)
            return (
              <button
                key={s.value}
                type="button"
                onClick={() => {
                  const cur = form.match_ai_tool.split(",").map(v => v.trim()).filter(Boolean)
                  set("match_ai_tool", (selected ? cur.filter(v => v !== s.value) : [...cur, s.value]).join(","))
                }}
                style={{
                  fontSize: 11.5, padding: "3px 10px", borderRadius: 9999, cursor: "pointer",
                  border: `1px solid ${selected ? "var(--accent)" : "var(--border)"}`,
                  background: selected ? "var(--accent-weak)" : "var(--surface)",
                  color: selected ? "var(--accent-text)" : "var(--text-3)",
                  fontWeight: selected ? 600 : 400,
                }}
              >{s.label}</button>
            )
          })}
        </div>
      </div>

      {/* Advanced toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(v => !v)}
        style={{
          background: "none", border: "none", cursor: "pointer", padding: 0,
          fontSize: 12, color: "var(--text-3)", textAlign: "left", display: "flex", alignItems: "center", gap: 4,
        }}
      >
        <span style={{ fontSize: 10 }}>{showAdvanced ? "▾" : "▸"}</span>
        Advanced options
      </button>

      {showAdvanced && (
        <>
          {/* Description — auto-generates rule_id */}
          <div>
            <label style={labelStyle}>Description</label>
            <input
              type="text"
              value={form.description}
              onChange={e => set("description", e.target.value)}
              placeholder="Block recursive deletes"
              style={fieldStyle}
            />
            {form.rule_id && (
              <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-muted)" }}>
                Rule ID: <code style={{ fontFamily: "monospace" }}>{form.rule_id}</code>
              </p>
            )}
          </div>

          {/* In this file path */}
          <div>
            <label style={labelStyle}>
              In this file path
              <span style={{
                marginLeft: 6, fontSize: 10, fontWeight: 600, padding: "1px 6px",
                borderRadius: 4, background: "var(--surface-2)", color: "var(--text-3)",
                border: "1px solid var(--border)", verticalAlign: "middle",
              }}>regex</span>
            </label>
            <input
              type="text"
              value={form.match_path_pattern}
              onChange={e => set("match_path_pattern", e.target.value)}
              placeholder=".github/workflows/.*"
              style={fieldMonoStyle}
            />
          </div>

          {/* Message to developer */}
          <div>
            <label style={labelStyle}>Message shown to developer</label>
            <input
              type="text"
              value={form.message}
              onChange={e => set("message", e.target.value)}
              placeholder="This operation is not permitted by your team policy."
              style={fieldStyle}
            />
          </div>
        </>
      )}

      {submitError && <p style={{ margin: 0, fontSize: 11.5, color: "var(--err)" }}>{submitError}</p>}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, paddingTop: 4, marginTop: "auto" }}>
        <button type="button" onClick={onClose} className="btn btn-ghost btn-sm">Cancel</button>
        <button
          type="submit"
          disabled={submitting || (form.inject_guidance && !guidanceReviewed)}
          className="btn btn-primary btn-sm"
          style={{ opacity: submitting || (form.inject_guidance && !guidanceReviewed) ? 0.5 : 1, cursor: submitting || (form.inject_guidance && !guidanceReviewed) ? "not-allowed" : "pointer" }}
          title={form.inject_guidance && !guidanceReviewed ? "Confirm the guidance to save." : undefined}
        >
          {submitting ? "Adding…" : "Add rule"}
        </button>
      </div>
    </form>,
    "New policy rule"
  )
}
