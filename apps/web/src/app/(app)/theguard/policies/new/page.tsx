"use client"

import { useState, useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
// ponytail: AI generation removed — API key not configured on this deployment
import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PolicyAction = "block" | "warn" | "audit" | "approval"
type MatchTool = "shell" | "filesystem-write" | "filesystem-read" | "network" | "*"

const AI_SURFACES = [
  { value: "claude-code",      label: "Claude Code" },
  { value: "claude-ai",        label: "Claude.ai" },
  { value: "claude-desktop",   label: "Claude Desktop" },
  { value: "codex-cli",        label: "Codex CLI" },
  { value: "codex-desktop",    label: "Codex Desktop" },
  { value: "openai-chatgpt",   label: "ChatGPT" },
  { value: "cursor",           label: "Cursor" },
  { value: "windsurf",         label: "Windsurf" },
]

interface GeneratedPolicy {
  rule_id: string
  description: string
  persona: "agent" | "proxy"
  match_tool: MatchTool
  match_ai_tool: string   // comma-separated surface values, or "" = any
  match_pattern: string
  match_path_pattern: string
  action: PolicyAction
  inject_guidance: boolean
  guidance: string
  message: string
}

// ---------------------------------------------------------------------------
// Field components
// ---------------------------------------------------------------------------

function FieldLabel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--text-3)" }}>{children}</label>
      {hint && <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{hint}</p>}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  height: 36,
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "0 12px",
  fontSize: 13,
  background: "var(--surface)",
  color: "var(--text)",
  outline: "none",
  boxSizing: "border-box",
}

function TextInput({
  value,
  onChange,
  onBlur,
  placeholder,
  mono,
  error,
}: {
  value: string
  onChange: (v: string) => void
  onBlur?: () => void
  placeholder?: string
  mono?: boolean
  error?: string
}) {
  return (
    <div>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        style={{
          ...inputStyle,
          fontFamily: mono ? "var(--font-mono, monospace)" : undefined,
          borderColor: error ? "var(--err-bd)" : undefined,
        }}
      />
      {error && <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--err)" }}>{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Review card
// ---------------------------------------------------------------------------

function ReviewCard({
  policy,
  onChange,
  onSave,
  onDiscard,
  saving,
  saveError,
}: {
  policy: GeneratedPolicy
  onChange: (p: GeneratedPolicy) => void
  onSave: () => void
  onDiscard: () => void
  saving: boolean
  saveError: string | null
}) {
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof GeneratedPolicy, string>>>({})
  const [guidanceReviewed, setGuidanceReviewed] = useState(false)

  function set<K extends keyof GeneratedPolicy>(key: K, value: GeneratedPolicy[K]) {
    onChange({ ...policy, [key]: value })
    setFieldErrors(prev => ({ ...prev, [key]: undefined }))
  }

  function validate(): boolean {
    const errs: Partial<Record<keyof GeneratedPolicy, string>> = {}
    if (!policy.rule_id.trim()) errs.rule_id = "Required"
    else if (!/^[a-z0-9-]+$/.test(policy.rule_id.trim())) errs.rule_id = "Lowercase letters, numbers, and hyphens only"
    if (!policy.match_pattern.trim()) errs.match_pattern = "Required"
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  function handleSaveClick() {
    if (validate()) onSave()
  }

  return (
    <div className="card">
      <div style={{
        padding: "16px 20px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <div>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Review generated rule</h2>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>Edit any field before saving.</p>
        </div>
        <span style={{
          display: "inline-block",
          padding: "2px 8px",
          borderRadius: 9999,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.04em",
          background: "var(--accent-weak)",
          color: "var(--accent-text)",
          border: "1px solid var(--accent)",
        }}>
          AI-generated
        </span>
      </div>

      <div style={{
        padding: "16px 20px",
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        columnGap: 24,
        rowGap: 16,
      }}>
        {/* rule_id */}
        <div>
          <FieldLabel hint="Slug format: lowercase letters, numbers, hyphens only.">Rule ID</FieldLabel>
          <TextInput
            value={policy.rule_id}
            onChange={v => set("rule_id", v)}
            onBlur={() => {
              const v = policy.rule_id.trim()
              if (v && !/^[a-z0-9-]+$/.test(v)) {
                setFieldErrors(prev => ({ ...prev, rule_id: "Lowercase letters, numbers, and hyphens only" }))
              }
            }}
            placeholder="no-rm-rf"
            error={fieldErrors.rule_id}
          />
        </div>

        {/* description */}
        <div>
          <FieldLabel>Description</FieldLabel>
          <TextInput
            value={policy.description}
            onChange={v => set("description", v)}
            placeholder="What this rule prevents"
          />
        </div>

        {/* persona */}
        <div>
          <FieldLabel hint="Agent: what AI does on your machine. Proxy: what leaves your network to the LLM.">Persona</FieldLabel>
          <div style={{ display: "flex", gap: 8 }}>
            {(["agent", "proxy"] as const).map(p => (
              <button
                key={p}
                type="button"
                onClick={() => set("persona", p)}
                style={{
                  flex: 1, height: 36, borderRadius: 8, fontSize: 13, fontWeight: 500,
                  border: `1px solid ${policy.persona === p ? "var(--accent)" : "var(--border)"}`,
                  background: policy.persona === p ? "var(--accent-bg, #eff6ff)" : "var(--surface)",
                  color: policy.persona === p ? "var(--accent)" : "var(--text-3)",
                  cursor: "pointer",
                }}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* match_tool */}
        <div>
          <FieldLabel>Match tool</FieldLabel>
          <select
            value={policy.match_tool}
            onChange={e => set("match_tool", e.target.value as MatchTool)}
            style={inputStyle}
          >
            <option value="*">* (any)</option>
            <option value="shell">shell — bash, run_command, execute</option>
            <option value="filesystem-write">filesystem-write — write, edit, str_replace_editor</option>
            <option value="filesystem-read">filesystem-read — read, glob, grep, list_directory</option>
            <option value="network">network — web_fetch, http_request, curl</option>
          </select>
        </div>

        {/* match_ai_tool — surface filter */}
        <div style={{ gridColumn: "1 / -1" }}>
          <FieldLabel hint="Leave blank to apply to all surfaces">AI surface (optional)</FieldLabel>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
            {AI_SURFACES.map(s => {
              const selected = policy.match_ai_tool.split(",").map(v => v.trim()).filter(Boolean).includes(s.value)
              return (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => {
                    const current = policy.match_ai_tool.split(",").map(v => v.trim()).filter(Boolean)
                    const next = selected ? current.filter(v => v !== s.value) : [...current, s.value]
                    set("match_ai_tool", next.join(","))
                  }}
                  style={{
                    padding: "4px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer", border: "1px solid",
                    borderColor: selected ? "var(--accent)" : "var(--border)",
                    background: selected ? "var(--accent-weak)" : "var(--surface)",
                    color: selected ? "var(--accent-text)" : "var(--text-muted)",
                    fontWeight: selected ? 600 : 400,
                  }}
                >
                  {s.label}
                </button>
              )
            })}
          </div>
          {policy.match_ai_tool && (
            <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>
              match_ai_tool: &quot;{policy.match_ai_tool}&quot;
            </div>
          )}
        </div>

        {/* action */}
        <div>
          <FieldLabel>Action</FieldLabel>
          <select
            value={policy.action}
            onChange={e => set("action", e.target.value as PolicyAction)}
            style={inputStyle}
          >
            <option value="block">block — stop the tool call</option>
            <option value="warn">warn — allow but notify</option>
            <option value="audit">audit — log silently</option>
            <option value="approval">approval — block, require manual override</option>
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, fontSize: 12, color: "var(--text-3)", cursor: "pointer" }}>
            <input type="checkbox" checked={policy.inject_guidance} onChange={e => { set("inject_guidance", e.target.checked); if (e.target.checked) setGuidanceReviewed(false) }} style={{ margin: 0 }} />
            Also inject guidance to model <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(message becomes a system-prompt safety net)</span>
          </label>
          {policy.inject_guidance && !guidanceReviewed && (
            <div style={{ marginTop: 8, padding: "10px 12px", background: "var(--surface-2)", borderRadius: 8, borderLeft: "3px solid var(--warn)", fontSize: 12, color: "var(--text-2)" }}>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>Guidance to model</div>
              <div style={{ color: "var(--text-muted)", marginBottom: 6 }}>
                Prepended to the model&apos;s system prompt. Write model-directed text (imperative, one paragraph).
              </div>
              <textarea
                value={policy.guidance || policy.message}
                onChange={e => set("guidance", e.target.value)}
                rows={4}
                placeholder="e.g. Do not echo any PII verbatim. Refer to individuals by role only."
                style={{ ...inputStyle, fontFamily: "var(--font-mono, monospace)", fontSize: 12, marginBottom: 8 }}
              />
              <div style={{ display: "flex", gap: 6 }}>
                <button type="button" onClick={() => { if (!policy.guidance) set("guidance", policy.message); setGuidanceReviewed(true) }} className="btn btn-primary btn-sm">Confirm guidance</button>
                <button type="button" onClick={() => { set("inject_guidance", false); set("guidance", ""); setGuidanceReviewed(false) }} className="btn btn-ghost btn-sm">Cancel</button>
              </div>
            </div>
          )}
          {policy.inject_guidance && guidanceReviewed && (
            <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "var(--ok)" }}>
              <span>✓ Guidance reviewed</span>
              <button type="button" onClick={() => setGuidanceReviewed(false)} className="btn btn-ghost btn-sm" style={{ padding: "0 6px", fontSize: 11 }}>Edit</button>
            </div>
          )}
        </div>

        {/* match_pattern */}
        <div>
          <FieldLabel>Match pattern (regex)</FieldLabel>
          <TextInput
            value={policy.match_pattern}
            onChange={v => set("match_pattern", v)}
            placeholder={String.raw`rm\s+-rf`}
            mono
            error={fieldErrors.match_pattern}
          />
        </div>

        {/* match_path_pattern */}
        <div>
          <FieldLabel>Match path pattern (regex, optional)</FieldLabel>
          <TextInput
            value={policy.match_path_pattern}
            onChange={v => set("match_path_pattern", v)}
            placeholder=".github/workflows/.*"
            mono
          />
        </div>

        {/* message — full width */}
        <div style={{ gridColumn: "1 / -1" }}>
          <FieldLabel>Message shown to developer</FieldLabel>
          <TextInput
            value={policy.message}
            onChange={v => set("message", v)}
            placeholder="This operation is not permitted by your team policy."
          />
        </div>
      </div>

      {saveError && (
        <div style={{
          margin: "0 20px 16px",
          borderRadius: 8,
          border: "1px solid var(--err-bd)",
          background: "var(--err-bg)",
          padding: "10px 16px",
          fontSize: 13,
          color: "var(--err)",
        }}>
          {saveError}
        </div>
      )}

      <div style={{
        padding: "16px 20px",
        borderTop: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 12,
      }}>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onDiscard}
        >
          Discard
        </button>
        <button
          type="button"
          onClick={handleSaveClick}
          disabled={saving || (policy.inject_guidance && !guidanceReviewed)}
          className="btn btn-primary btn-sm"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, opacity: saving || (policy.inject_guidance && !guidanceReviewed) ? 0.5 : 1, cursor: saving || (policy.inject_guidance && !guidanceReviewed) ? "not-allowed" : undefined }}
          title={policy.inject_guidance && !guidanceReviewed ? "Confirm the guidance to save." : undefined}
        >
          {saving ? (
            <>
              <svg style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle style={{ opacity: 0.25 }} cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path style={{ opacity: 0.75 }} fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Saving…
            </>
          ) : "Save rule"}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NewPolicyPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialPersona = (searchParams.get("persona") === "proxy" ? "proxy" : "agent") as "agent" | "proxy"
  const { authFetch } = useAuthFetch()
  const { teamId } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  useEffect(() => {
    if (!permissionsLoading && !permissions.canEditPolicies) {
      router.replace("/guard/policies")
    }
  }, [permissionsLoading, permissions.canEditPolicies, router])

  const [policy, setPolicy] = useState<GeneratedPolicy>({
    rule_id: "", description: "", persona: initialPersona,
    match_tool: "*", match_ai_tool: "", match_pattern: "",
    match_path_pattern: "", action: "block", inject_guidance: false, guidance: "", message: "",
  })
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    try {
      const body: Record<string, unknown> = {
        rule_id: policy.rule_id.trim(),
        description: policy.description.trim(),
        match_tool: policy.match_tool,
        match_pattern: policy.match_pattern.trim(),
        action: policy.action,
        inject_guidance: policy.inject_guidance,
        guidance: policy.guidance.trim() || undefined,
        message: policy.message.trim(),
        enabled: true,
        builtin: false,
        persona: policy.persona,
      }
      if (policy.match_ai_tool.trim()) body.match_ai_tool = policy.match_ai_tool.trim()
      if (policy.match_path_pattern.trim()) body.match_path_pattern = policy.match_path_pattern.trim()
      if (teamId) body.workspace_id = teamId
      await guard.policies.create(authFetch, body)
      sessionStorage.setItem("guard.policies.saved", "Rule saved successfully.")
      router.push("/guard/policies")
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save rule. Please try again.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell>
      <div style={{
        maxWidth: 672,
        margin: "0 auto",
        padding: "32px 24px",
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}>
        {/* Back link */}
        <div>
          <button
            type="button"
            onClick={() => router.push("/guard/policies")}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: 13,
              color: "var(--text-3)",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: 0,
              textDecoration: "none",
            }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" style={{ width: 14, height: 14 }}>
              <path fillRule="evenodd" d="M9.78 4.22a.75.75 0 0 1 0 1.06L7.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L5.47 8.53a.75.75 0 0 1 0-1.06l3.25-3.25a.75.75 0 0 1 1.06 0Z" clipRule="evenodd" />
            </svg>
            Back to policies
          </button>
        </div>

        {/* Page heading */}
        <div>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>Create a rule</h2>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 4 }}>
            Fill in the fields below and save.
          </p>
        </div>

        <ReviewCard
          policy={policy}
          onChange={setPolicy}
          onSave={handleSave}
          onDiscard={() => router.push("/guard/policies")}
          saving={saving}
          saveError={saveError}
        />
      </div>
    </AppShell>
  )
}
