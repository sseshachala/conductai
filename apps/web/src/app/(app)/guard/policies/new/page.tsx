"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { POLICY_TEMPLATES } from "@/lib/guardPolicyTemplates"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PolicyAction = "block" | "warn" | "audit" | "approval" | "inject"
type MatchTool = "bash" | "edit" | "write" | "read" | "*"

interface GeneratedPolicy {
  rule_id: string
  description: string
  match_tool: MatchTool
  match_pattern: string
  match_path_pattern: string
  action: PolicyAction
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

        {/* match_tool */}
        <div>
          <FieldLabel>Match tool</FieldLabel>
          <select
            value={policy.match_tool}
            onChange={e => set("match_tool", e.target.value as MatchTool)}
            style={inputStyle}
          >
            <option value="*">* (any)</option>
            <option value="bash">bash</option>
            <option value="edit">edit</option>
            <option value="write">write</option>
            <option value="read">read</option>
          </select>
        </div>

        {/* action */}
        <div>
          <FieldLabel>Action</FieldLabel>
          <select
            value={policy.action}
            onChange={e => set("action", e.target.value as PolicyAction)}
            style={inputStyle}
          >
            <option value="block">block</option>
            <option value="warn">warn</option>
            <option value="audit">audit</option>
            <option value="approval">approval</option>
            <option value="inject">inject</option>
          </select>
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
          disabled={saving}
          className="btn btn-primary btn-sm"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, opacity: saving ? 0.5 : 1, cursor: saving ? "not-allowed" : undefined }}
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
  const { getToken } = useAuth()
  const { teamId } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!permissionsLoading && !permissions.canEditPolicies) {
      router.replace("/guard/policies")
    }
  }, [permissionsLoading, permissions.canEditPolicies, router])

  const [prompt, setPrompt] = useState("")
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)

  const [generatedPolicy, setGeneratedPolicy] = useState<GeneratedPolicy | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ""

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) {
      const t = await getToken()
      if (t) h["Authorization"] = `Bearer ${t}`
    }
    return h
  }, [getToken])

  async function handleGenerate() {
    const text = prompt.trim()
    if (!text) return

    setGenerating(true)
    setGenerateError(null)
    setGeneratedPolicy(null)
    setSaveError(null)

    try {
      const headers = await authHeaders()
      const res = await fetch(`${apiUrl}/guard/policies/generate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ prompt: text, workspace_id: teamId }),
      })
      if (!res.ok) {
        const detail = await res.text().catch(() => "")
        throw new Error(detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setGeneratedPolicy({
        rule_id: data.rule_id ?? "",
        description: data.description ?? "",
        match_tool: (data.match_tool as MatchTool) ?? "*",
        match_pattern: data.match_pattern ?? "",
        match_path_pattern: data.match_path_pattern ?? "",
        action: (data.action as PolicyAction) ?? "block",
        message: data.message ?? "",
      })
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : "Failed to generate rule. Please try again.")
    } finally {
      setGenerating(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleGenerate()
    }
  }

  async function handleSave() {
    if (!generatedPolicy) return

    setSaving(true)
    setSaveError(null)

    try {
      const headers = await authHeaders()
      const body: Record<string, unknown> = {
        rule_id: generatedPolicy.rule_id.trim(),
        description: generatedPolicy.description.trim(),
        match_tool: generatedPolicy.match_tool,
        match_pattern: generatedPolicy.match_pattern.trim(),
        action: generatedPolicy.action,
        message: generatedPolicy.message.trim(),
        enabled: true,
        builtin: false,
      }
      if (generatedPolicy.match_path_pattern.trim()) {
        body.match_path_pattern = generatedPolicy.match_path_pattern.trim()
      }
      if (teamId) body.workspace_id = teamId

      const res = await fetch(`${apiUrl}/guard/policies`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        if (res.status === 422) {
          const json = await res.json().catch(() => null)
          const d = json?.detail
          if (Array.isArray(d) && d.length > 0) {
            const field = Array.isArray(d[0]?.loc) ? d[0].loc.join(".") : null
            const msg = d[0]?.msg ?? "Validation error"
            throw new Error(field ? `${field}: ${msg}` : msg)
          }
        }
        const detail = await res.text().catch(() => "")
        throw new Error(detail || `HTTP ${res.status}`)
      }
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
            onClick={() => {
              const hasContent = prompt.trim() || generatedPolicy?.rule_id || generatedPolicy?.match_pattern
              if (hasContent && !confirm("Discard this policy? Your changes will be lost.")) return
              router.push("/guard/policies")
            }}
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
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>Create a rule with AI</h2>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 4 }}>
            Describe what you want to control in plain English — the AI will suggest the rule fields for you to review and save.
          </p>
        </div>

        {/* Template chips */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <p style={{ fontSize: 12, fontWeight: 500, color: "var(--text-3)" }}>Start from a template</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {POLICY_TEMPLATES.map((t) => (
              <button
                key={t.label}
                type="button"
                disabled={generating}
                onClick={() => {
                  setPrompt(t.prompt)
                  setGeneratedPolicy(null)
                  setSaveError(null)
                  setGenerateError(null)
                  // auto-generate after setting the prompt
                  setTimeout(() => {
                    setPrompt(t.prompt)
                    // call generate via the prompt value directly
                    void (async () => {
                      setGenerating(true)
                      setGenerateError(null)
                      setGeneratedPolicy(null)
                      setSaveError(null)
                      try {
                        const headers = await authHeaders()
                        const res = await fetch(`${apiUrl}/guard/policies/generate`, {
                          method: "POST",
                          headers,
                          body: JSON.stringify({ prompt: t.prompt, workspace_id: teamId }),
                        })
                        if (!res.ok) {
                          const detail = await res.text().catch(() => "")
                          throw new Error(detail || `HTTP ${res.status}`)
                        }
                        const data = await res.json()
                        setGeneratedPolicy({
                          rule_id: data.rule_id ?? "",
                          description: data.description ?? "",
                          match_tool: (data.match_tool as MatchTool) ?? "*",
                          match_pattern: data.match_pattern ?? "",
                          match_path_pattern: data.match_path_pattern ?? "",
                          action: (data.action as PolicyAction) ?? "block",
                          message: data.message ?? "",
                        })
                      } catch (e) {
                        setGenerateError(e instanceof Error ? e.message : "Failed to generate rule. Please try again.")
                      } finally {
                        setGenerating(false)
                      }
                    })()
                  }, 0)
                }}
                style={{
                  fontSize: 12,
                  padding: "6px 12px",
                  borderRadius: 9999,
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                  color: "var(--text-3)",
                  cursor: generating ? "not-allowed" : "pointer",
                  opacity: generating ? 0.4 : 1,
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Prompt input card */}
        <div className="card" style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
          <label
            htmlFor="policy-prompt"
            style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--text-3)" }}
          >
            Describe your policy
          </label>
          <textarea
            id="policy-prompt"
            ref={textareaRef}
            rows={3}
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={generating}
            placeholder="e.g. block anyone from running rm -rf, or require approval before prod deploys"
            style={{
              width: "100%",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "10px 12px",
              fontSize: 13,
              color: "var(--text)",
              background: "var(--surface)",
              resize: "none",
              outline: "none",
              opacity: generating ? 0.5 : 1,
              cursor: generating ? "not-allowed" : "auto",
              boxSizing: "border-box",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Press Enter to generate, or Shift+Enter for a new line.</p>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating || !prompt.trim()}
              className="btn btn-primary btn-sm"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                opacity: generating || !prompt.trim() ? 0.5 : 1,
                cursor: generating || !prompt.trim() ? "not-allowed" : undefined,
              }}
            >
              {generating ? (
                <>
                  <svg style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle style={{ opacity: 0.25 }} cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path style={{ opacity: 0.75 }} fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Generating…
                </>
              ) : "Generate"}
            </button>
          </div>
        </div>

        {/* Generating pulse skeleton */}
        {generating && (
          <div className="card" style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12, animation: "pulse 1.5s ease-in-out infinite" }}>
            <div style={{ height: 12, width: 192, borderRadius: 4, background: "var(--surface-3)" }} />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
              <div style={{ height: 32, borderRadius: 4, background: "var(--surface-2)" }} />
              <div style={{ height: 32, borderRadius: 4, background: "var(--surface-2)" }} />
              <div style={{ height: 32, borderRadius: 4, background: "var(--surface-2)" }} />
              <div style={{ height: 32, borderRadius: 4, background: "var(--surface-2)" }} />
              <div style={{ gridColumn: "1 / -1", height: 32, borderRadius: 4, background: "var(--surface-2)" }} />
            </div>
          </div>
        )}

        {/* Generate error */}
        {generateError && !generating && (
          <div style={{
            borderRadius: 8,
            border: "1px solid var(--err-bd)",
            background: "var(--err-bg)",
            padding: "12px 16px",
            fontSize: 13,
            color: "var(--err)",
            display: "flex",
            alignItems: "flex-start",
            gap: 8,
          }}>
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" style={{ width: 16, height: 16, marginTop: 1, flexShrink: 0 }}>
              <path fillRule="evenodd" d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1ZM7.25 4.75a.75.75 0 0 1 1.5 0v3.5a.75.75 0 0 1-1.5 0v-3.5Zm.75 7a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z" clipRule="evenodd" />
            </svg>
            <span>{generateError}</span>
          </div>
        )}

        {/* Review card */}
        {generatedPolicy && !generating && (
          <ReviewCard
            policy={generatedPolicy}
            onChange={setGeneratedPolicy}
            onSave={handleSave}
            onDiscard={() => {
              const hasContent = prompt.trim() || generatedPolicy?.rule_id || generatedPolicy?.match_pattern
              if (hasContent && !confirm("Discard this policy? Your changes will be lost.")) return
              router.push("/guard/policies")
            }}
            saving={saving}
            saveError={saveError}
          />
        )}
      </div>
    </AppShell>
  )
}
