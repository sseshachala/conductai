"use client"

import { useState, useCallback, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import GuardNav from "@/components/guard/GuardNav"

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
// Templates
// ---------------------------------------------------------------------------

const TEMPLATES = [
  { label: "Approve merge to main",        prompt: "Require approval before merging to the main or master branch" },
  { label: "Meaningful commit messages",   prompt: "Warn when commit messages are shorter than 10 characters or left empty" },
  { label: "No PII in files",              prompt: "Block writing files that contain email addresses or phone numbers" },
  { label: "No SELECT *",                  prompt: "Warn when SQL queries use SELECT * instead of explicit column names" },
  { label: "No hardcoded IPs",             prompt: "Block hardcoded IP addresses in source code files" },
  { label: "Audit dependency changes",     prompt: "Audit any changes to package.json, requirements.txt, or pyproject.toml" },
  { label: "Non-standard registries",      prompt: "Warn when installing packages from non-standard or private registries" },
  { label: "No privileged ports",          prompt: "Block opening or binding to ports below 1024 in code" },
  { label: "Approve K8s manifests",        prompt: "Require approval before modifying Kubernetes manifest files" },
  { label: "Audit Terraform state",        prompt: "Audit any changes to Terraform state files (.tfstate)" },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTeamId(): string {
  if (typeof window === "undefined") return ""
  return localStorage.getItem("guard_team_id") ?? ""
}

// ---------------------------------------------------------------------------
// Field components
// ---------------------------------------------------------------------------

function FieldLabel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-1">
      <label className="block text-xs font-medium text-stone-600">{children}</label>
      {hint && <p className="text-[11px] text-stone-400 mt-0.5">{hint}</p>}
    </div>
  )
}

function TextInput({
  value,
  onChange,
  placeholder,
  mono,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  mono?: boolean
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent ${mono ? "font-mono" : ""}`}
    />
  )
}

// ---------------------------------------------------------------------------
// Review card
// ---------------------------------------------------------------------------

function ReviewCard({
  policy,
  onChange,
  onSave,
  saving,
  saveError,
}: {
  policy: GeneratedPolicy
  onChange: (p: GeneratedPolicy) => void
  onSave: () => void
  saving: boolean
  saveError: string | null
}) {
  function set<K extends keyof GeneratedPolicy>(key: K, value: GeneratedPolicy[K]) {
    onChange({ ...policy, [key]: value })
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white shadow-sm">
      <div className="px-5 py-4 border-b border-stone-100 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-stone-900">Review generated rule</h2>
          <p className="text-xs text-stone-400 mt-0.5">Edit any field before saving.</p>
        </div>
        <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold tracking-wide bg-indigo-100 text-indigo-700 border border-indigo-200">
          AI-generated
        </span>
      </div>

      <div className="px-5 py-4 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
        {/* rule_id */}
        <div>
          <FieldLabel hint="Slug format: lowercase letters, numbers, hyphens only.">Rule ID</FieldLabel>
          <TextInput
            value={policy.rule_id}
            onChange={v => set("rule_id", v)}
            placeholder="no-rm-rf"
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
            className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
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
            className="w-full rounded-md border border-stone-200 px-3 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
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
        <div className="sm:col-span-2">
          <FieldLabel>Message shown to developer</FieldLabel>
          <TextInput
            value={policy.message}
            onChange={v => set("message", v)}
            placeholder="This operation is not permitted by your team policy."
          />
        </div>
      </div>

      {saveError && (
        <div className="mx-5 mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {saveError}
        </div>
      )}

      <div className="px-5 py-4 border-t border-stone-100 flex items-center justify-end gap-3">
        <Link
          href="/guard/policies"
          className="px-4 py-1.5 rounded-md text-sm text-stone-600 hover:text-stone-900 hover:bg-stone-50 border border-stone-200 transition-colors"
        >
          Discard
        </Link>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? (
            <>
              <svg className="animate-spin w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
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
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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
      const teamId = getTeamId()
      const res = await fetch(`${apiUrl}/guard/policies/generate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ prompt: text, team_id: teamId }),
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
      const teamId = getTeamId()
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
      if (teamId) body.team_id = teamId

      const res = await fetch(`${apiUrl}/guard/policies`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const detail = await res.text().catch(() => "")
        throw new Error(detail || `HTTP ${res.status}`)
      }
      router.push("/guard/policies")
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save rule. Please try again.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold text-stone-900 mb-1">Guard</h1>
          <GuardNav />
        </div>

        {/* Back link + page title */}
        <div className="flex items-center gap-2">
          <Link
            href="/guard/policies"
            className="inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-800 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path fillRule="evenodd" d="M9.78 4.22a.75.75 0 0 1 0 1.06L7.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L5.47 8.53a.75.75 0 0 1 0-1.06l3.25-3.25a.75.75 0 0 1 1.06 0Z" clipRule="evenodd" />
            </svg>
            Back to policies
          </Link>
        </div>

        <div>
          <h2 className="text-base font-semibold text-stone-900">Create a rule with AI</h2>
          <p className="text-sm text-stone-500 mt-1">
            Describe what you want to control in plain English — the AI will suggest the rule fields for you to review and save.
          </p>
        </div>

        {/* Template chips */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-stone-500">Start from a template</p>
          <div className="flex flex-wrap gap-2">
            {TEMPLATES.map((t) => (
              <button
                key={t.label}
                type="button"
                disabled={generating}
                onClick={() => {
                  setPrompt(t.prompt)
                  setGeneratedPolicy(null)
                  setSaveError(null)
                  setGenerateError(null)
                }}
                className="text-xs px-3 py-1.5 rounded-full border border-stone-200 bg-white text-stone-600 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Prompt input card */}
        <div className="rounded-xl border border-stone-200 bg-white shadow-sm px-5 py-4 space-y-3">
          <label htmlFor="policy-prompt" className="block text-xs font-medium text-stone-600">
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
            className="w-full rounded-lg border border-stone-200 px-3 py-2.5 text-sm text-stone-900 placeholder-stone-400 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-stone-400">Press Enter to generate, or Shift+Enter for a new line.</p>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating || !prompt.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {generating ? (
                <>
                  <svg className="animate-spin w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Generating…
                </>
              ) : "Generate"}
            </button>
          </div>
        </div>

        {/* Generating pulse skeleton */}
        {generating && (
          <div className="rounded-xl border border-stone-200 bg-white shadow-sm px-5 py-4 animate-pulse space-y-3">
            <div className="h-3 w-48 rounded bg-stone-100" />
            <div className="grid grid-cols-2 gap-4">
              <div className="h-8 rounded bg-stone-50" />
              <div className="h-8 rounded bg-stone-50" />
              <div className="h-8 rounded bg-stone-50" />
              <div className="h-8 rounded bg-stone-50" />
              <div className="col-span-2 h-8 rounded bg-stone-50" />
            </div>
          </div>
        )}

        {/* Generate error */}
        {generateError && !generating && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-start gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 mt-0.5 shrink-0">
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
            saving={saving}
            saveError={saveError}
          />
        )}
      </div>
    </AppShell>
  )
}
