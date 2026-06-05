"use client"

import React, { useState, useEffect, useRef } from "react"
import { BLOCK_STYLES, type BlockType } from "@/lib/block-types"
import {
  BLOCK_CONFIG_SCHEMAS,
  ACTION_FIELDS,
  INTEGRATION_ACTIONS,
  INTEGRATIONS,
  type ConfigField,
} from "@/lib/config-schemas"
import { GitHubRepoField, GitHubBranchField, GitHubRepoAllowlistField } from "./GitHubRepoField"
import { cn } from "@/lib/utils"

interface BlockEditorProps {
  workflowId: string
  blockId: string
  blockType: BlockType
  label: string
  description: string
  blockData: Record<string, unknown>
  onChange: (blockId: string, changes: Record<string, unknown>) => void
  getToken?: (() => Promise<string | null>) | null
  isAdmin?: boolean
  isViewer?: boolean
  selectedEnvId?: string
  githubHookRepo?: string | null
  githubHookId?: string | null
  githubWebhook?: boolean
  playbookSlug?: string | null
  projectSlug?: string | null
  onWebhookChange?: (hookId: string | null, hookRepo: string | null) => void
  onClose?: () => void
}

// ── Client-side model router preview (mirrors model_router.py) ────────────────

const MODEL_LABELS: Record<string, string> = {
  "claude-opus-4-7":            "Claude Opus",
  "claude-sonnet-4-6":          "Claude Sonnet",
  "claude-haiku-4-5-20251001":  "Claude Haiku",
  "gpt-4.1":                    "GPT-4.1",
  "gpt-4.1-mini":               "GPT-4.1 Mini",
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
}

const SLUG_CATEGORY: Record<string, string> = {
  autopilot_quick: "code_implementation", autopilot_full: "code_implementation",
  autopilot_approved: "code_implementation", dependency_updater: "code_implementation",
  security_patch_updater: "code_implementation",
  pr_reviewer: "code_review", copilot_reviewer: "code_review", release_readiness: "code_review",
  security_scanner: "security",
  issue_triage: "triage", ci_notify: "triage", flaky_test_detective: "triage",
  release_notes: "summarization", postmortem_drafter: "summarization", docs_drift_detector: "summarization",
  incident_responder: "reasoning", terraform_reviewer: "reasoning",
}

const POLICY: Record<string, Record<string, [string, string, string]>> = {
  code_implementation: { quality: ["anthropic", "claude-opus-4-7", "code implementation benefits from strongest reasoning"], balanced: ["anthropic", "claude-sonnet-4-6", "balanced model for code implementation"], speed: ["anthropic", "claude-sonnet-4-6", "sonnet is fast enough for code tasks"], cost: ["openai", "gpt-4.1-mini", "cost-efficient model for code implementation"] },
  code_review:         { quality: ["anthropic", "claude-opus-4-7", "code review benefits from strongest reasoning model"], balanced: ["anthropic", "claude-sonnet-4-6", "balanced model for code review"], speed: ["openai", "gpt-4.1-mini", "fast and efficient for code review"], cost: ["openai", "gpt-4.1-mini", "cost-efficient for structured code review output"] },
  security:            { quality: ["anthropic", "claude-opus-4-7", "security scanning requires highest-precision model"], balanced: ["anthropic", "claude-opus-4-7", "security scanning: quality always preferred over cost"], speed: ["anthropic", "claude-sonnet-4-6", "sonnet for security when speed is prioritized"], cost: ["anthropic", "claude-sonnet-4-6", "sonnet minimum viable for security"] },
  triage:              { quality: ["anthropic", "claude-sonnet-4-6", "sonnet sufficient for structured triage tasks"], balanced: ["openai", "gpt-4.1-mini", "balanced and efficient for triage"], speed: ["openai", "gpt-4.1-mini", "fast triage classification"], cost: ["openai", "gpt-4.1-mini", "cost-optimal for simple triage tasks"] },
  summarization:       { quality: ["anthropic", "claude-sonnet-4-6", "sonnet more than sufficient for summarization"], balanced: ["openai", "gpt-4.1-mini", "balanced model for summarization"], speed: ["openai", "gpt-4.1-mini", "fast summarization"], cost: ["openai", "gpt-4.1-mini", "cost-optimal for summarization"] },
  reasoning:           { quality: ["anthropic", "claude-opus-4-7", "reasoning tasks benefit from strongest model"], balanced: ["anthropic", "claude-sonnet-4-6", "balanced model for reasoning tasks"], speed: ["anthropic", "claude-sonnet-4-6", "sonnet balances speed and reasoning depth"], cost: ["openai", "gpt-4.1-mini", "cost-efficient minimum viable reasoning"] },
}

const PREF_DEFAULTS: Record<string, [string, string, string]> = {
  quality: ["anthropic", "claude-opus-4-7", "quality preference: strongest model"],
  balanced: ["anthropic", "claude-sonnet-4-6", "balanced preference: default model"],
  speed: ["openai", "gpt-4.1-mini", "speed preference: efficient model"],
  cost: ["openai", "gpt-4.1-mini", "cost preference: efficient model"],
}

const PROVIDER_DEFAULTS: Record<string, Record<string, [string, string]>> = {
  anthropic: {
    code_implementation: ["claude-sonnet-4-6", "anthropic override: balanced default for code implementation"],
    code_review: ["claude-sonnet-4-6", "anthropic override: balanced default for code review"],
    security: ["claude-opus-4-7", "anthropic override: strongest model for security"],
    triage: ["claude-sonnet-4-6", "anthropic override: balanced default for triage"],
    summarization: ["claude-sonnet-4-6", "anthropic override: balanced default for summarization"],
    reasoning: ["claude-sonnet-4-6", "anthropic override: balanced default for reasoning"],
    unknown: ["claude-sonnet-4-6", "anthropic override: balanced default model"],
  },
  openai: {
    code_implementation: ["gpt-4.1-mini", "openai override: efficient model for code implementation"],
    code_review: ["gpt-4.1-mini", "openai override: efficient model for code review"],
    security: ["gpt-4.1", "openai override: strongest available OpenAI model for security"],
    triage: ["gpt-4.1-mini", "openai override: efficient model for triage"],
    summarization: ["gpt-4.1-mini", "openai override: efficient model for summarization"],
    reasoning: ["gpt-4.1", "openai override: strongest available OpenAI model for reasoning"],
    unknown: ["gpt-4.1-mini", "openai override: balanced default model"],
  },
}

function previewModel(playbookSlug: string | null | undefined, pref: string, providerOverride?: string): [string, string, string] {
  const p = (pref || "balanced").toLowerCase()
  const category = SLUG_CATEGORY[playbookSlug ?? ""] ?? ""
  const override = (providerOverride || "").toLowerCase()
  if (override === "anthropic" || override === "openai") {
    const [model, reason] = PROVIDER_DEFAULTS[override][category || "unknown"] ?? PROVIDER_DEFAULTS[override].unknown
    return [PROVIDER_LABELS[override] ?? override, MODEL_LABELS[model] ?? model, reason]
  }
  const [provider, model, reason] = (category ? POLICY[category]?.[p] : null) ?? PREF_DEFAULTS[p] ?? ["anthropic", "claude-sonnet-4-6", "default"]
  return [PROVIDER_LABELS[provider] ?? provider, MODEL_LABELS[model] ?? model, reason]
}

// ── GitHub webhook status panel ───────────────────────────────────────────────

function GitHubWebhookStatusPanel({
  workflowId, hookId, hookRepo, getToken, onWebhookChange, compact,
}: {
  workflowId: string
  hookId: string | null
  hookRepo: string | null
  getToken?: (() => Promise<string | null>) | null
  onWebhookChange?: (hookId: string | null, hookRepo: string | null) => void
  compact?: boolean
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [sharedWith, setSharedWith] = useState<string | null>(null)

  async function authHeaders() {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const ws = typeof document !== "undefined"
      ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
    if (ws) h["X-Workspace-Id"] = ws
    return h
  }

  async function register() {
    setBusy(true); setErr(null); setSharedWith(null)
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/webhook`, {
        method: "POST", headers: await authHeaders(),
      })
      const data = await r.json()
      if (!r.ok) { setErr(data.detail || `HTTP ${r.status}`); return }
      if (data.shared) setSharedWith(data.shared_with_name ?? "another agent")
      onWebhookChange?.(data.github_hook_id, data.github_hook_repo)
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Network error")
    } finally { setBusy(false) }
  }

  async function deregister() {
    setBusy(true); setErr(null)
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/webhook`, {
        method: "DELETE", headers: await authHeaders(),
      })
      if (!r.ok && r.status !== 204) {
        const data = await r.json().catch(() => ({}))
        setErr(data.detail || `HTTP ${r.status}`); return
      }
      onWebhookChange?.(null, hookRepo)
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Network error")
    } finally { setBusy(false) }
  }

  const registered = !!hookId

  if (compact) {
    return (
      <div className={`rounded-md border px-2.5 py-2 text-xs mt-1.5 flex items-center justify-between gap-3 ${registered ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        <div>
          <p className={`font-semibold ${registered ? "text-emerald-700" : "text-amber-700"}`}>
            {registered ? `✓ Registered on ${hookRepo}` : "Not registered — GitHub won't send events"}
          </p>
          {sharedWith && <p className="text-stone-500 mt-0.5">Shared with &ldquo;{sharedWith}&rdquo;</p>}
          {err && <p className="text-red-600 mt-0.5">{err}</p>}
        </div>
        <div className="flex gap-1 shrink-0">
          {!registered && (
            <button onClick={register} disabled={busy}
              className="rounded bg-amber-600 text-white px-2.5 py-1 font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors text-[10px]">
              {busy ? "Registering…" : "Register"}
            </button>
          )}
          {registered && (
            <button onClick={register} disabled={busy}
              className="rounded bg-emerald-600 text-white px-2.5 py-1 font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors text-[10px]">
              {busy ? "Updating…" : "Update"}
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`rounded-lg border px-3 py-2.5 text-xs mt-2 ${registered ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className={`font-semibold ${registered ? "text-emerald-800" : "text-amber-800"}`}>
            {registered ? `✓ Webhook registered` : "Webhook not registered"}
          </p>
          <p className={`mt-0.5 ${registered ? "text-emerald-700" : "text-amber-700"}`}>
            {registered
              ? <span>on <span className="font-mono">{hookRepo}</span> — GitHub sends events here automatically</span>
              : hookRepo
              ? <span>Configure once you're ready — real GitHub events won't arrive until registered</span>
              : <span>Set a repository in the trigger config first</span>
            }
          </p>
          {sharedWith && <p className="text-stone-500 mt-1">Webhook shared with &ldquo;{sharedWith}&rdquo; — no duplicate hook created on GitHub.</p>}
          {err && <p className="text-red-600 mt-1">{err}</p>}
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {!registered && hookRepo && (
            <button onClick={register} disabled={busy}
              className="rounded-md bg-amber-600 text-white px-3 py-1.5 font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors text-xs">
              {busy ? "Registering…" : "Register Webhook"}
            </button>
          )}
          {registered && (
            <>
              <button onClick={register} disabled={busy}
                className="rounded-md bg-emerald-600 text-white px-3 py-1.5 font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors text-xs">
                {busy ? "Updating…" : "Update"}
              </button>
              <button onClick={deregister} disabled={busy}
                className="rounded-md border border-stone-300 text-stone-600 px-3 py-1.5 font-medium hover:bg-stone-100 disabled:opacity-50 transition-colors text-xs">
                Unregister
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Webhook registration ──────────────────────────────────────────────────────

function WebhookRegisterButton({ owner, repo, getToken }: {
  owner: string; repo: string; getToken?: (() => Promise<string | null>) | null
}) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle")
  const [msg, setMsg] = useState("")

  async function register() {
    setStatus("loading")
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL
      if (!apiUrl) { setStatus("error"); setMsg("NEXT_PUBLIC_API_URL not set"); return }
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
      const ws = typeof document !== "undefined"
        ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
      if (ws) headers["X-Workspace-Id"] = ws
      const url = `${apiUrl}/credentials/github/repos/${owner}/${repo}/webhook`
      const r = await fetch(url, { method: "POST", headers })
      const data = await r.json()
      if (!r.ok) { setStatus("error"); setMsg(data.detail || `HTTP ${r.status}`); return }
      setStatus("done")
      setMsg(data.existing ? "Already registered" : "Webhook registered!")
    } catch (e) {
      setStatus("error"); setMsg(e instanceof Error ? e.message : "Network error")
    }
  }

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2.5 text-xs">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-indigo-800">GitHub webhook</p>
          <p className="text-indigo-600 mt-0.5">
            {status === "done" ? msg : `Auto-register on ${owner}/${repo} to receive issue events`}
            {status === "error" && <span className="text-red-600"> — {msg}</span>}
          </p>
        </div>
        {status !== "done" && (
          <button
            onClick={register}
            disabled={status === "loading"}
            className="shrink-0 rounded-md bg-indigo-600 text-white px-3 py-1.5 font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {status === "loading" ? "Registering…" : "Register"}
          </button>
        )}
        {status === "done" && <span className="text-emerald-600 font-semibold shrink-0">✓ Active</span>}
      </div>
    </div>
  )
}

// ── Vercel webhook registration ───────────────────────────────────────────────

function VercelWebhookRegisterButton({ eventType, getToken }: {
  eventType: string; getToken?: (() => Promise<string | null>) | null
}) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle")
  const [msg, setMsg] = useState("")

  async function register() {
    setStatus("loading")
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL
      if (!apiUrl) { setStatus("error"); setMsg("NEXT_PUBLIC_API_URL not set"); return }
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
      const ws = typeof document !== "undefined"
        ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
      if (ws) headers["X-Workspace-Id"] = ws
      const r = await fetch(`${apiUrl}/credentials/vercel/webhook`, {
        method: "POST",
        headers,
        body: JSON.stringify({ event_type: eventType }),
      })
      const data = await r.json()
      if (!r.ok) { setStatus("error"); setMsg(data.detail || `HTTP ${r.status}`); return }
      setStatus("done")
      setMsg(data.existing ? "Already registered" : "Webhook registered!")
    } catch (e) {
      setStatus("error"); setMsg(e instanceof Error ? e.message : "Network error")
    }
  }

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2.5 text-xs">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-indigo-800">Auto-register with Vercel</p>
          <p className="text-indigo-600 mt-0.5">
            {status === "done" ? msg : "Uses your saved Vercel token to register the workspace-scoped webhook"}
            {status === "error" && <span className="text-red-600"> — {msg}</span>}
          </p>
        </div>
        {status !== "done" && (
          <button
            onClick={register}
            disabled={status === "loading"}
            className="shrink-0 rounded-md bg-indigo-600 text-white px-3 py-1.5 font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {status === "loading" ? "Registering…" : "Register"}
          </button>
        )}
        {status === "done" && <span className="text-emerald-600 font-semibold shrink-0">✓ Active</span>}
      </div>
    </div>
  )
}

// ── Ref chip renderer ─────────────────────────────────────────────────────────

function SystemPromptWithChips({ text }: { text: string }) {
  if (!text) return <span className="text-stone-400 italic">No system prompt defined.</span>

  const parts = text.split(/({{[^}]+}})/)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("{{") && part.endsWith("}}")) {
          const ref = part.slice(2, -2)
          const isLiteral = ref.startsWith("<") || ref.includes(" ")
          return (
            <span
              key={i}
              className={cn(
                "inline-flex items-center rounded px-1 py-0.5 text-[11px] font-mono font-medium mx-0.5",
                isLiteral
                  ? "bg-red-100 text-red-600 border border-red-200"
                  : "bg-violet-100 text-violet-700 border border-violet-200"
              )}
            >
              {part}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

// ── helpers ───────────────────────────────────────────────────────────────────

// Patterns that strongly suggest a hardcoded secret rather than a template ref.
const SECRET_PATTERNS = [
  /^ghp_[A-Za-z0-9]{36}/,           // GitHub personal access token
  /^github_pat_[A-Za-z0-9_]{82}/,    // GitHub fine-grained PAT
  /^ghs_[A-Za-z0-9]{36}/,           // GitHub app installation token
  /^xoxb-[0-9]+-[A-Za-z0-9-]+/,     // Slack bot token
  /^xoxp-[0-9]+-[A-Za-z0-9-]+/,     // Slack user token
  /^xoxa-[0-9]+-[A-Za-z0-9-]+/,     // Slack legacy token
  /^sk-[A-Za-z0-9]{20,}/,           // OpenAI / generic sk- key
  /^pk-[A-Za-z0-9]{20,}/,           // Generic pk- key
  /^Bearer\s+[A-Za-z0-9._-]{20,}/,  // Inline Bearer token
  /^[A-Za-z0-9_-]{40,}$/,           // Long opaque string (≥40 chars, no spaces)
]

const SECRET_FIELD_NAMES = /token|secret|key|password|api_key|access_token|auth/i

function looksLikeSecret(fieldName: string, value: unknown): boolean {
  if (typeof value !== "string" || !value.trim()) return false
  if (value.startsWith("{{") && value.endsWith("}}")) return false  // template ref — fine
  if (SECRET_FIELD_NAMES.test(fieldName)) return true
  return SECRET_PATTERNS.some(re => re.test(value.trim()))
}

function findHardcodedSecrets(params: unknown): string[] {
  if (!params || typeof params !== "object") return []
  return Object.entries(params as Record<string, unknown>)
    .filter(([k, v]) => looksLikeSecret(k, v))
    .map(([k]) => k)
}

function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object") return (acc as Record<string, unknown>)[key]
    return undefined
  }, obj)
}

function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const keys = path.split(".")
  const result = { ...obj }
  let cur: Record<string, unknown> = result
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i]
    cur[k] = cur[k] && typeof cur[k] === "object" ? { ...(cur[k] as Record<string, unknown>) } : {}
    cur = cur[k] as Record<string, unknown>
  }
  cur[keys[keys.length - 1]] = value
  return result
}

// ── Tag input ─────────────────────────────────────────────────────────────────

function TagInput({
  value,
  suggestions,
  placeholder,
  onChange,
}: {
  value: string[]
  suggestions?: string[]
  placeholder?: string
  onChange: (tags: string[]) => void
}) {
  const [inputVal, setInputVal] = useState("")
  const unusedSuggestions = (suggestions ?? []).filter(s => !value.includes(s))

  function addTag(tag: string) {
    const trimmed = tag.trim()
    if (trimmed && !value.includes(trimmed)) onChange([...value, trimmed])
    setInputVal("")
  }

  function removeTag(tag: string) {
    onChange(value.filter(t => t !== tag))
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      addTag(inputVal)
    } else if (e.key === "Backspace" && !inputVal && value.length > 0) {
      removeTag(value[value.length - 1])
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5 min-h-[34px] border border-stone-200 rounded-lg px-2.5 py-1.5 bg-white focus-within:ring-2 focus-within:ring-indigo-200">
        {value.map(tag => (
          <span key={tag} className="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 text-xs font-medium px-2 py-0.5 rounded-full">
            {tag}
            <button type="button" onClick={() => removeTag(tag)} className="text-indigo-400 hover:text-indigo-700 leading-none">×</button>
          </span>
        ))}
        <input
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => { if (inputVal.trim()) addTag(inputVal) }}
          placeholder={value.length === 0 ? placeholder : ""}
          className="flex-1 min-w-[80px] text-sm text-stone-900 bg-transparent outline-none"
        />
      </div>
      {unusedSuggestions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {unusedSuggestions.map(s => (
            <button key={s} type="button" onClick={() => addTag(s)}
              className="text-[11px] px-2 py-0.5 rounded-full border border-stone-200 text-stone-500 hover:border-indigo-300 hover:text-indigo-600 transition-colors">
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Config field renderer ─────────────────────────────────────────────────────

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: ConfigField
  value: unknown
  onChange: (val: unknown) => void
}) {
  const strVal = value === undefined || value === null ? (field.defaultValue !== undefined ? String(field.defaultValue) : "") : String(value)
  const boolVal = value === undefined ? (field.defaultValue as boolean ?? false) : Boolean(value)
  const [visible, setVisible] = React.useState(false)

  const base = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"

  if (field.readOnly) {
    const display = strVal || field.placeholder || ""
    const isRef = display.startsWith("{{") && display.endsWith("}}")
    // Secrets (long opaque strings, no template syntax) stay masked
    const isSecret = !isRef && display.length > 12 && !/\s/.test(display)
    if (isRef) {
      // Template references shown as a violet chip — not masked
      return (
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-50 border border-stone-200 rounded-lg">
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-mono font-medium bg-violet-100 text-violet-700 border border-violet-200">
            {display}
          </span>
        </div>
      )
    }
    if (isSecret) {
      const masked = display.replace(/./g, "•").slice(0, 24)
      return (
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-50 border border-stone-200 rounded-lg">
          <span className="text-xs font-mono text-stone-500 truncate flex-1">{visible ? display : masked}</span>
          <button type="button" onClick={() => setVisible(v => !v)} className="shrink-0 text-stone-400 hover:text-stone-600">
            {visible
              ? <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/><path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd"/></svg>
              : <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M3.707 2.293a1 1 0 00-1.414 1.414l14 14a1 1 0 001.414-1.414l-1.473-1.473A10.014 10.014 0 0019.542 10C18.268 5.943 14.478 3 10 3a9.958 9.958 0 00-4.512 1.074l-1.78-1.781zm4.261 4.26l1.514 1.515a2.003 2.003 0 012.45 2.45l1.514 1.514a4 4 0 00-5.478-5.478z" clipRule="evenodd"/><path d="M12.454 16.697L9.75 13.992a4 4 0 01-3.742-3.741L2.335 6.578A9.98 9.98 0 00.458 10c1.274 4.057 5.064 7 9.542 7 .847 0 1.669-.105 2.454-.303z"/></svg>
            }
          </button>
        </div>
      )
    }
    // Plain read-only value (short, non-secret) — just show it
    return (
      <div className="px-2.5 py-1.5 bg-stone-50 border border-stone-200 rounded-lg text-xs text-stone-600 font-mono">
        {display || <span className="text-stone-400 italic">—</span>}
      </div>
    )
  }

  if (field.type === "toggle") {
    return (
      <button
        type="button"
        onClick={() => onChange(!boolVal)}
        className={cn(
          "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
          boolVal ? "bg-indigo-500" : "bg-stone-200"
        )}
      >
        <span className={cn("inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform",
          boolVal ? "translate-x-4.5" : "translate-x-0.5"
        )} />
      </button>
    )
  }

  if (field.type === "tags") {
    const tags = Array.isArray(value) ? (value as string[]) : (typeof value === "string" && value ? value.split(",").map(s => s.trim()).filter(Boolean) : [])
    return (
      <TagInput
        value={tags}
        suggestions={field.suggestions}
        placeholder={field.placeholder}
        onChange={onChange}
      />
    )
  }

  if (field.type === "select") {
    return (
      <select value={strVal} onChange={e => onChange(e.target.value)} className={base}>
        {field.options?.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    )
  }

  if (field.type === "textarea") {
    return (
      <textarea
        value={strVal}
        onChange={e => onChange(e.target.value)}
        rows={2}
        placeholder={field.placeholder}
        className={cn(base, "resize-none")}
      />
    )
  }

  if (field.type === "number") {
    return (
      <input
        type="number"
        value={strVal}
        onChange={e => onChange(e.target.value)}
        placeholder={field.placeholder}
        className={cn(base, "w-24")}
      />
    )
  }

  return (
    <input
      type="text"
      value={strVal}
      onChange={e => onChange(e.target.value)}
      placeholder={field.placeholder}
      className={base}
    />
  )
}

// ── Guard block panel ─────────────────────────────────────────────────────────

interface GuardPolicy {
  id: string
  rule_id: string
  description: string | null
  action: string
  enabled: boolean
  builtin: boolean
}

const MODE_LABELS: Record<string, { label: string; sub: string; color: string; dot: string }> = {
  block: { label: "Block on violation",  sub: "Halts the run immediately when a policy fires.",     color: "text-red-700",    dot: "bg-red-500"    },
  warn:  { label: "Warn and continue",   sub: "Logs the violation but lets the run finish.",         color: "text-amber-700",  dot: "bg-amber-400"  },
  audit: { label: "Audit only",          sub: "Records violations silently — no run impact.",        color: "text-stone-600",  dot: "bg-stone-400"  },
}

function GuardBlockPanel({
  getToken,
  config,
  onChange,
  isAdmin = false,
  isViewer = false,
}: {
  getToken?: (() => Promise<string | null>) | null
  config: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  isAdmin?: boolean
  isViewer?: boolean
}) {
  const [installed, setInstalled] = useState<boolean | null>(null)
  const [teamId, setTeamId] = useState<string | null>(null)
  const [policies, setPolicies] = useState<GuardPolicy[]>([])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const ws = typeof document !== "undefined"
          ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
          : null
        const base = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")
        const token = await getToken?.()
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`

        const installUrl = ws ? `${base}/guard/config/installed?workspace_id=${ws}` : `${base}/guard/config/installed`
        const installRes = await fetch(installUrl, { headers })
        if (!installRes.ok) { if (!cancelled) setInstalled(false); return }
        const installData = await installRes.json()
        if (cancelled) return
        if (!installData.installed) { setInstalled(false); return }

        setInstalled(true)
        setTeamId(ws ?? installData.workspace_id)

        const polRes = await fetch(`${base}/guard/policies?workspace_id=${ws}`, { headers })
        if (!polRes.ok) return
        const polData: GuardPolicy[] = await polRes.json()
        if (!cancelled) setPolicies(polData.filter(p => p.enabled))
      } catch {
        if (!cancelled) setInstalled(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [getToken])

  const mode = (getNestedValue(config, "config.enforcement_mode") as string) || "block"
  const modeInfo = MODE_LABELS[mode] ?? MODE_LABELS.block
  const modePolicies = policies.filter(p => p.action === mode)

  if (installed === null) {
    return <div className="px-4 py-3 text-[11px] text-stone-400">Checking Guard status…</div>
  }

  if (!installed) {
    return (
      <div className="mx-4 my-3 rounded-lg border border-red-200 bg-red-50 px-3 py-3 space-y-2">
        <p className="text-[11px] font-semibold text-red-700">ConductGuard not installed</p>
        {isAdmin ? (
          <>
            <p className="text-[10px] text-red-600 leading-relaxed">
              This block enforces spend caps, tool blocks, and audit policies — but Guard is not installed for this workspace.
            </p>
            <a
              href="/settings/modules"
              className="inline-block text-[10px] font-semibold text-red-700 border border-red-300 rounded px-2 py-1 hover:bg-red-100 transition-colors"
            >
              Install Guard →
            </a>
          </>
        ) : (
          <p className="text-[10px] text-red-600 leading-relaxed">
            Guard is not installed for this workspace. Ask your workspace admin to install it in Settings → Modules.
          </p>
        )}
      </div>
    )
  }

  const spendCap = (getNestedValue(config, "config.spend_cap_usd") as string) || ""
  const monitoredTools = (getNestedValue(config, "config.monitored_tools") as string[]) || []
  const AI_TOOLS = [
    { id: "claude_code", label: "Claude Code" },
    { id: "cursor",      label: "Cursor"      },
    { id: "codex",       label: "Codex"       },
    { id: "windsurf",    label: "Windsurf"    },
  ]

  function toggleTool(toolId: string) {
    if (isViewer) return
    const next = monitoredTools.includes(toolId)
      ? monitoredTools.filter(t => t !== toolId)
      : [...monitoredTools, toolId]
    onChange("config.monitored_tools", next)
  }

  return (
    <div className="px-4 py-3 space-y-4">
      {/* Enforcement mode */}
      <div>
        <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1.5">Enforcement mode</span>
        <select
          value={mode}
          onChange={e => !isViewer && onChange("config.enforcement_mode", e.target.value)}
          disabled={isViewer}
          className="w-full text-[11px] border border-stone-200 rounded-lg px-2.5 py-1.5 bg-white text-stone-800 focus:outline-none focus:ring-1 focus:ring-stone-300 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <option value="block">Block on violation</option>
          <option value="warn">Warn and continue</option>
          <option value="audit">Audit only</option>
        </select>
        <p className={`text-[10px] mt-1 ${modeInfo.color}`}>{modeInfo.sub}</p>
      </div>

      {/* Spend cap */}
      <div>
        <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1.5">Spend cap (USD)</span>
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[11px] text-stone-400">$</span>
          <input
            type="number"
            min="0"
            step="0.01"
            placeholder="e.g. 5.00"
            value={spendCap}
            onChange={e => !isViewer && onChange("config.spend_cap_usd", e.target.value)}
            disabled={isViewer}
            className="w-full text-[11px] border border-stone-200 rounded-lg pl-6 pr-2.5 py-1.5 bg-white text-stone-800 focus:outline-none focus:ring-1 focus:ring-stone-300 disabled:opacity-60 disabled:cursor-not-allowed"
          />
        </div>
        <p className="text-[10px] text-stone-400 mt-1">Trigger enforcement when spend exceeds this amount per run.</p>
      </div>

      {/* AI tools to monitor */}
      <div>
        <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1.5">Monitor AI tools</span>
        <div className="grid grid-cols-2 gap-1.5">
          {AI_TOOLS.map(tool => (
            <label
              key={tool.id}
              className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 cursor-pointer text-[11px] transition-colors ${
                monitoredTools.includes(tool.id)
                  ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                  : "border-stone-200 bg-stone-50 text-stone-500 hover:border-stone-300"
              } ${isViewer ? "cursor-not-allowed opacity-60" : ""}`}
            >
              <input
                type="checkbox"
                className="w-3 h-3 rounded accent-indigo-600"
                checked={monitoredTools.includes(tool.id)}
                onChange={() => toggleTool(tool.id)}
                disabled={isViewer}
              />
              {tool.label}
            </label>
          ))}
        </div>
        {monitoredTools.length === 0 && (
          <p className="text-[10px] text-stone-400 mt-1">No tools selected — Guard will monitor all tools.</p>
        )}
      </div>

      {/* Policies active for selected mode */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
            {mode} policies
          </span>
          {isAdmin && (
            <a href="/guard/policies" className="text-[10px] text-stone-400 hover:text-stone-600 underline">
              Manage →
            </a>
          )}
        </div>
        {modePolicies.length === 0 ? (
          <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-2.5 text-[10px] text-stone-400">
            No {mode} policies configured.{" "}
            <a href="/guard/policies" className="underline hover:text-stone-600">Add one →</a>
          </div>
        ) : (
          <ul className="space-y-1">
            {modePolicies.map(p => (
              <li key={p.id} className="flex items-start gap-2 rounded-lg border border-stone-100 bg-stone-50 px-2.5 py-2">
                <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${modeInfo.dot}`} />
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold text-stone-700 truncate">{p.rule_id}</p>
                  {p.description && (
                    <p className="text-[9px] text-stone-400 leading-snug mt-0.5 line-clamp-2">{p.description}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── MCP block panel ──────────────────────────────────────────────────────────

interface MCPTool {
  name: string
  description?: string
  inputSchema?: {
    properties?: Record<string, { type?: string; description?: string }>
    required?: string[]
  }
}

const MCP_PROVIDERS: { value: string; label: string; serverUrl: string; credentialKey: string; transport: string }[] = [
  { value: "vercel",   label: "Vercel",   serverUrl: "https://mcp.vercel.com",          credentialKey: "VERCEL_TOKEN",    transport: "http" },
  { value: "linear",   label: "Linear",   serverUrl: "https://mcp.linear.app/mcp",      credentialKey: "LINEAR_API_KEY",  transport: "http" },
  { value: "railway",  label: "Railway",  serverUrl: "https://mcp.railway.com",         credentialKey: "RAILWAY_TOKEN",   transport: "http" },
  { value: "jira",     label: "Jira",     serverUrl: "https://mcp.atlassian.com/mcp",   credentialKey: "JIRA_TOKEN",      transport: "http" },
  { value: "github",   label: "GitHub",   serverUrl: "https://api.githubcopilot.com/mcp", credentialKey: "GITHUB_TOKEN",  transport: "http" },
  { value: "slack",    label: "Slack",    serverUrl: "https://mcp.slack.com",           credentialKey: "SLACK_TOKEN",     transport: "sse"  },
  { value: "custom",   label: "Custom",   serverUrl: "",                                credentialKey: "",                transport: "auto" },
]

function MCPBlockPanel({
  getToken,
  blockData,
  onChange,
  isViewer = false,
}: {
  getToken?: (() => Promise<string | null>) | null
  blockData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  isViewer?: boolean
}) {
  const [tools, setTools] = useState<MCPTool[]>([])
  const [discovering, setDiscovering] = useState(false)
  const [discoverErr, setDiscoverErr] = useState<string | null>(null)

  const provider      = (getNestedValue(blockData, "config.provider")      as string) || "custom"
  const credentialKey = (getNestedValue(blockData, "config.credential_key") as string) || ""
  const serverUrl     = (getNestedValue(blockData, "config.server_url")     as string) || ""
  const transport     = (getNestedValue(blockData, "config.transport")      as string) || "auto"
  const toolName      = (getNestedValue(blockData, "config.tool_name")      as string) || ""

  const isCustom = provider === "custom"
  const selectedTool = tools.find(t => t.name === toolName) ?? null
  const paramProps   = selectedTool?.inputSchema?.properties ?? {}
  const requiredParams = new Set(selectedTool?.inputSchema?.required ?? [])

  function handleProviderChange(val: string) {
    const p = MCP_PROVIDERS.find(x => x.value === val)
    if (!p) return
    onChange("config.provider",       p.value)
    onChange("config.server_url",     p.serverUrl)
    onChange("config.credential_key", p.credentialKey)
    onChange("config.transport",      p.transport)
    onChange("config.tool_name",      "")
    setTools([])
    setDiscoverErr(null)
  }

  async function authHeaders() {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const ws = typeof document !== "undefined"
      ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
    if (ws) h["X-Workspace-Id"] = ws
    return h
  }

  async function discoverTools() {
    const key = credentialKey.trim()
    if (!key) { setDiscoverErr("Enter a credential key first."); return }
    setDiscovering(true); setDiscoverErr(null)
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/mcp/tools`, {
        method: "POST",
        headers: await authHeaders(),
        body: JSON.stringify({ credential_key: key, transport }),
      })
      const data = await r.json()
      if (!r.ok) { setDiscoverErr(data.detail || `HTTP ${r.status}`); return }
      const list: MCPTool[] = Array.isArray(data) ? data : (data.tools ?? [])
      setTools(list)
      if (list.length > 0 && !toolName) onChange("config.tool_name", list[0].name)
    } catch (e) {
      setDiscoverErr(e instanceof Error ? e.message : "Network error")
    } finally {
      setDiscovering(false)
    }
  }

  const inputBase = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white disabled:opacity-60 disabled:cursor-not-allowed"
  const sectionLabel = "text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1.5 block"

  return (
    <div className="px-4 py-3 space-y-4">

      {/* Provider */}
      <div>
        <span className={sectionLabel}>Provider <span className="text-red-500">*</span></span>
        <select
          value={provider}
          onChange={e => !isViewer && handleProviderChange(e.target.value)}
          disabled={isViewer}
          className={inputBase}
        >
          {MCP_PROVIDERS.map(p => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
      </div>

      {/* Custom server URL */}
      {isCustom && (
        <div>
          <span className={sectionLabel}>MCP Server URL <span className="text-red-500">*</span></span>
          <input
            type="text"
            value={serverUrl}
            onChange={e => !isViewer && onChange("config.server_url", e.target.value)}
            disabled={isViewer}
            placeholder="https://my-mcp-server.com/mcp"
            className={inputBase}
          />
        </div>
      )}

      {/* Credential key — always shown, pre-filled for known providers */}
      <div>
        <span className={sectionLabel}>Credential Key <span className="text-red-500">*</span></span>
        <input
          type="text"
          value={credentialKey}
          onChange={e => !isViewer && onChange("config.credential_key", e.target.value)}
          disabled={isViewer}
          placeholder={isCustom ? "MY_SERVICE_TOKEN" : credentialKey}
          className={inputBase}
        />
        <p className="text-[10px] text-stone-400 mt-1">
          Env var name from <a href="/settings/environments" className="underline hover:text-stone-600">Settings → Environments</a>
        </p>
      </div>

      {/* Discover */}
      <div>
        <button
          type="button"
          onClick={discoverTools}
          disabled={isViewer || discovering || !credentialKey}
          className="w-full rounded-lg border border-cyan-200 bg-cyan-50 text-cyan-700 text-xs font-semibold px-3 py-2 hover:bg-cyan-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {discovering ? "Discovering…" : "Discover tools"}
        </button>
        {discoverErr && <p className="text-[10px] text-red-600 mt-1">{discoverErr}</p>}
        {tools.length > 0 && <p className="text-[10px] text-emerald-600 mt-1">{tools.length} tool{tools.length !== 1 ? "s" : ""} found</p>}
      </div>

      {/* Tool picker */}
      <div>
        <span className={sectionLabel}>Tool <span className="text-red-500">*</span></span>
        {tools.length > 0 ? (
          <select
            value={toolName}
            onChange={e => !isViewer && onChange("config.tool_name", e.target.value)}
            disabled={isViewer}
            className={inputBase}
          >
            <option value="">— pick a tool —</option>
            {tools.map(t => (
              <option key={t.name} value={t.name}>{t.name}{t.description ? ` — ${t.description}` : ""}</option>
            ))}
          </select>
        ) : toolName ? (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5">
            <span className="text-sm font-mono text-emerald-800 flex-1 truncate">{toolName}</span>
            <span className="text-[10px] text-emerald-600 shrink-0">Discover to change</span>
          </div>
        ) : (
          <input
            type="text"
            value={toolName}
            onChange={e => !isViewer && onChange("config.tool_name", e.target.value)}
            disabled={isViewer}
            placeholder="Click Discover to populate"
            className={inputBase}
          />
        )}
        {selectedTool?.description && <p className="text-[10px] text-stone-400 mt-1">{selectedTool.description}</p>}
      </div>

      {/* Dynamic params */}
      {Object.keys(paramProps).length > 0 && (
        <div className="space-y-3">
          <span className={sectionLabel}>Parameters</span>
          {Object.entries(paramProps).map(([paramKey, paramDef]) => {
            const req = requiredParams.has(paramKey)
            const val = (getNestedValue(blockData, `config.params.${paramKey}`) as string) || ""
            return (
              <div key={paramKey}>
                <div className="flex items-center gap-1.5 mb-1">
                  <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">{paramKey}</label>
                  {req && <span className="text-red-500 text-[10px]">*</span>}
                  {paramDef.description && <span className="text-[10px] text-stone-400">{paramDef.description}</span>}
                </div>
                <input
                  type="text"
                  value={val}
                  onChange={e => !isViewer && onChange(`config.params.${paramKey}`, e.target.value)}
                  disabled={isViewer}
                  placeholder={`{{previous_block.${paramKey}}}`}
                  className={inputBase}
                />
              </div>
            )
          })}
          <p className="text-[10px] text-stone-400 pt-1">
            Use <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code> to reference earlier outputs.
          </p>
        </div>
      )}

    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function BlockEditor({
  workflowId,
  blockId,
  blockType,
  label,
  description,
  blockData,
  onChange,
  getToken,
  isAdmin = false,
  isViewer = false,
  selectedEnvId,
  githubHookRepo,
  githubHookId,
  githubWebhook,
  playbookSlug,
  projectSlug,
  onWebhookChange,
  onClose,
}: BlockEditorProps) {
  const [promptOpen, setPromptOpen] = useState(false)
  const [streamedPrompt, setStreamedPrompt] = useState<string>("")
  const [isStreaming, setIsStreaming] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const style = BLOCK_STYLES[blockType]

  const isToolLike = ["tool", "cleanup"].includes(blockType)
  const integration = (blockData.integration as string) || ""
  const action = (getNestedValue(blockData, "config.action") as string) || ""
  const triggerEventType = (getNestedValue(blockData, "config.event_type") as string) || ""

  // Derive config fields to show — filter trigger fields to only what's relevant
  const VERCEL_EVENT_TYPES = new Set(["deployment.succeeded", "deployment.ready", "deployment.failed", "deployment.error"])
  const isVercelTrigger = VERCEL_EVENT_TYPES.has(triggerEventType)

  const allStaticFields = BLOCK_CONFIG_SCHEMAS[blockType] || []
  const staticFields = blockType === "trigger"
    ? allStaticFields.filter(f => {
        if (f.key === "config.labels" || f.key === "config.repo_allowlist")
          return triggerEventType === "github_issue_labeled"
        if (f.key === "config.webhook_secret" || f.key === "config.test_pr_number")
          return triggerEventType === "webhook"
        if (f.key === "config.test_repo")
          return false  // redundant — repo is known from github_hook_repo
        return true
      })
    : blockType === "output"
    ? allStaticFields.filter(f => {
        if (f.key === "config.channel")
          return integration === "slack" || integration === "both"
        if (f.key === "config.to")
          return integration === "email" || integration === "both"
        if (f.key === "config.webhook_url" || f.key === "config.webhook_secret")
          return integration === "webhook"
        return true
      })
    : allStaticFields
  const actionFields = isToolLike && integration && action
    ? (ACTION_FIELDS[integration]?.[action] || [])
    : []

  // Seed default values for read-only fields the first time the block is opened
  useEffect(() => {
    const readOnlyFields = actionFields.filter(f => f.readOnly && f.defaultValue !== undefined)
    if (readOnlyFields.length === 0) return
    let updated = { ...blockData }
    let changed = false
    for (const f of readOnlyFields) {
      const existing = getNestedValue(updated, f.key)
      if (!existing) {
        updated = setNestedValue(updated, f.key, String(f.defaultValue))
        changed = true
      }
    }
    if (changed) onChange(blockId, updated)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockId, action])

  function handleFieldChange(path: string, value: unknown) {
    if (isViewer) return
    const updated = setNestedValue({ ...blockData }, path, value)
    onChange(blockId, updated)
  }

  // GitHub-aware field: repo picker sets owner + repo simultaneously
  const githubOwner = (getNestedValue(blockData, "config.params.owner") as string) || ""
  const githubRepo  = (getNestedValue(blockData, "config.params.repo")  as string) || ""

  function renderField(field: ConfigField) {
    const val = getNestedValue(blockData, field.key)

    // Read-only fields skip all integration-specific overrides
    if (field.readOnly) {
      return <FieldInput field={field} value={val} onChange={() => {}} />
    }

    // Trigger repo allowlist — multi-select typeahead from connected GitHub account
    if (field.key === "config.repo_allowlist") {
      const allowlistVal = (val as string) || (githubHookRepo ?? "")
      return (
        <GitHubRepoAllowlistField
          value={allowlistVal}
          getToken={getToken}
          environmentId={selectedEnvId}
          onChange={v => handleFieldChange(field.key, v)}
        />
      )
    }

    if (integration === "github") {
      // Repo picker — replaces both owner and repo fields
      if (field.key === "config.params.owner") {
        return (
          <GitHubRepoField
            value={githubOwner ? `${githubOwner}/${githubRepo}` : ""}
            getToken={getToken}
            onChange={(owner, repo) => {
              let updated = setNestedValue({ ...blockData }, "config.params.owner", owner)
              updated = setNestedValue(updated, "config.params.repo", repo)
              onChange(blockId, updated)
            }}
          />
        )
      }
      // Hide the standalone repo field — it's set by the owner picker above
      if (field.key === "config.params.repo") return null

      // Branch picker
      if (field.key === "config.params.branch" || field.key === "config.params.head" || field.key === "config.params.ref") {
        return (
          <GitHubBranchField
            owner={githubOwner}
            repo={githubRepo}
            value={(val as string) || ""}
            getToken={getToken}
            onChange={v => handleFieldChange(field.key, v)}
          />
        )
      }
    }

    return (
      <FieldInput
        field={field}
        value={val}
        onChange={v => handleFieldChange(field.key, v)}
      />
    )
  }

  // Stream compiled prompt when preview section is open
  useEffect(() => {
    if (!promptOpen) return
    if (abortRef.current) abortRef.current.abort()
    const abort = new AbortController()
    abortRef.current = abort
    setStreamedPrompt("")
    setIsStreaming(true)

    ;(async () => {
      try {
        const headers: Record<string, string> = { "Content-Type": "application/json" }
        if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
        const ws = typeof document !== "undefined"
          ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
        if (ws) headers["X-Workspace-Id"] = ws
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/blocks/${blockId}/compile/stream`,
          {
            method: "POST",
            signal: abort.signal,
            headers,
            body: JSON.stringify({ description, label, type: blockType }),
          }
        )
        if (!res.body) return
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() ?? ""
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue
            const payload = line.slice(6).trim()
            if (payload === "[DONE]") { setIsStreaming(false); return }
            try {
              const { text, error } = JSON.parse(payload)
              if (error) { setStreamedPrompt(`Error: ${error}`); setIsStreaming(false); return }
              if (text) setStreamedPrompt(prev => prev + text)
            } catch { /* ignore */ }
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name !== "AbortError") {
          setStreamedPrompt("Connection error — is the API running?")
        }
      } finally {
        setIsStreaming(false)
      }
    })()

    return () => abort.abort()
  }, [promptOpen, blockId, workflowId, description, getToken])

  useEffect(() => {
    setPromptOpen(false)
    setStreamedPrompt("")
    setIsStreaming(false)
    setShowAdvanced(false)
  }, [blockId])

  const section = "px-4 py-3 space-y-3 border-b border-stone-100"
  const sectionLabel = "text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2 block"
  const inputBase = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"

  return (
    <div className="bg-white flex flex-col h-full overflow-y-auto">

      {/* Header */}
      <div style={{ padding: "15px 18px", borderBottom: "1px solid var(--border)" }} className="shrink-0">
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span className={`chip bk-${blockType}`} style={{ height: 22, fontSize: 9.5, fontWeight: 800, letterSpacing: ".07em" }}>
            {style.labelText}
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: "auto" }}>#{blockId.slice(0, 8)}</span>
          {onClose && (
            <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose}>×</button>
          )}
        </div>
        <input
          value={label}
          onChange={e => onChange(blockId, { ...blockData, label: e.target.value })}
          disabled={isViewer}
          placeholder="Block name"
          style={{ marginTop: 11, width: "100%", border: "none", background: "transparent", color: "var(--text)", fontSize: 16.5, fontWeight: 650, letterSpacing: "-.01em", outline: "none", padding: 0 }}
        />
      </div>

      {/* Basic section header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "16px 18px 0" }}>
        <span className="eyebrow" style={{ fontSize: 10 }}>Basic</span>
        <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </div>

      {/* ── Brain blocks ── */}
      {blockType === "brain" && (
        <>
          <div className={section}>
            <span className={sectionLabel}>What should this step do?</span>
            <textarea
              value={(blockData.custom_instructions as string) || ""}
              onChange={e => onChange(blockId, { ...blockData, custom_instructions: e.target.value })}
              rows={5}
              placeholder="Describe what this AI step should do in plain English. e.g. &quot;Review the PR diff for security issues and post a summary comment.&quot;"
              className={cn(inputBase, "resize-none")}
              disabled={isViewer}
            />
            <p className="text-[10px] text-stone-400 mt-1">
              Use <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code> to reference outputs from earlier steps.
            </p>
          </div>

          <div className={section}>
            <span className={sectionLabel}>Mode</span>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-stone-700">
                {blockData.isAgentic ? "Can use tools" : "Single call"}
              </span>
              <FieldInput
                field={BLOCK_CONFIG_SCHEMAS.brain![0]}
                value={blockData.isAgentic}
                onChange={v => onChange(blockId, { ...blockData, isAgentic: v })}
              />
            </div>
            <p className="text-[10px] leading-relaxed mt-1.5 px-2 py-1.5 rounded-lg border">
              {blockData.isAgentic ? (
                <span className="text-violet-700 border-violet-200 bg-violet-50 rounded-lg">
                  <strong>Can use tools</strong> — reads files, edits code, runs commands, and pushes branches. Use for implementing fixes, running tests, and making changes.
                </span>
              ) : (
                <span className="text-stone-500 border-stone-100 bg-stone-50 rounded-lg">
                  <strong>Single call</strong> — responds once with text only. No file access, no commands. Use for summarising, classifying, or generating messages.
                </span>
              )}
            </p>
          </div>

          <div className={section}>
            <span className={sectionLabel}>Model routing</span>
            <select
              value={(blockData.routingPreference as string) || "balanced"}
              onChange={e => onChange(blockId, { ...blockData, routingPreference: e.target.value })}
              className={cn(inputBase)}
              disabled={isViewer}
            >
              <option value="balanced">Balanced — best default</option>
              <option value="quality">Quality — strongest model</option>
              <option value="speed">Speed — faster response</option>
              <option value="cost">Cost — efficient model</option>
            </select>
            {(() => {
              const [provider, model, reason] = previewModel(
                playbookSlug,
                (blockData.routingPreference as string) || "balanced",
                (blockData.provider as string) || "",
              )
              return (
                <p className="text-[10px] text-stone-500 mt-1">
                  <span className="font-medium text-violet-700">{provider} · {model}</span>
                  {" "}— {reason}
                </p>
              )
            })()}
            {!showAdvanced && (() => {
              const providerValue = ((blockData.provider as string) || "auto").toLowerCase()
              const providerLabel = providerValue === "auto"
                ? "Auto — let Conduct choose"
                : (PROVIDER_LABELS[providerValue] ?? providerValue)
              return (
                <p className="text-[10px] text-stone-500 mt-1">
                  Provider override: <span className="font-medium text-stone-700">{providerLabel}</span>
                  {" "}·{" "}
                  <button
                    type="button"
                    onClick={() => setShowAdvanced(true)}
                    className="text-violet-600 hover:text-violet-700 underline"
                  >
                    change in Advanced
                  </button>
                </p>
              )
            })()}
          </div>

          <button
            type="button"
            style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, background: "none", border: "none", padding: "8px 18px", cursor: "pointer" }}
            onClick={() => setShowAdvanced(v => !v)}
            disabled={isViewer}
          >
            <span style={{ transform: showAdvanced ? "rotate(90deg)" : "none", transition: "transform 0.14s", display: "inline-block", fontSize: 12, color: "var(--text-3)" }}>›</span>
            <span className="eyebrow" style={{ fontSize: 10 }}>Advanced</span>
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>5 settings</span>
            <div style={{ flex: 1, height: 1, background: "var(--border)", marginLeft: 2 }} />
          </button>

          {showAdvanced && (
            <>
              <div className={section}>
                <div className="flex items-center justify-between">
                  <span className={sectionLabel}>System prompt</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-stone-400 bg-stone-100 px-1.5 py-0.5 rounded mb-2">read-only</span>
                </div>
                <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-xs text-stone-600 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                  <SystemPromptWithChips text={description} />
                </div>
              </div>

              <div className={section}>
                <span className={sectionLabel}>Prompt file</span>
                <input
                  type="text"
                  value={((blockData.config as Record<string, unknown>)?.prompt_file as string) || ""}
                  onChange={e => onChange(blockId, { ...blockData, config: { ...(blockData.config as object || {}), prompt_file: e.target.value } })}
                  placeholder="prompts/fetch_issue.txt"
                  className={inputBase}
                  disabled={isViewer}
                />
                <p className="text-[10px] text-stone-400 mt-1">
                  Path relative to repo root. Overrides system prompt when set.
                </p>
              </div>

              <div className={section}>
                <span className={sectionLabel}>Provider override</span>
                <select
                  value={(blockData.provider as string) || "auto"}
                  onChange={e => onChange(blockId, { ...blockData, provider: e.target.value === "auto" ? "" : e.target.value })}
                  className={cn(inputBase)}
                  disabled={isViewer}
                >
                  <option value="auto">Auto — let Conduct choose</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="openai">OpenAI</option>
                </select>
                <p className="text-[10px] text-stone-500 mt-1">
                  Use auto for policy-based routing, or pin a provider while still letting Conduct choose the safest model within it.
                </p>
              </div>
            </>
          )}
        </>
      )}

      {/* ── Tool blocks: integration + action + params ── */}
      {isToolLike && (
        <div className={section}>
          <span className={sectionLabel}>Integration</span>
          <div className="space-y-2">
            <select
              value={integration}
              onChange={e => {
                const updated = setNestedValue({ ...blockData }, "integration", e.target.value)
                onChange(blockId, setNestedValue(updated, "config.action", ""))
              }}
              className={inputBase}
              disabled={isViewer}
            >
              <option value="">— pick integration —</option>
              {INTEGRATIONS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
            </select>

            {integration && (
              <select
                value={action}
                onChange={e => handleFieldChange("config.action", e.target.value)}
                className={inputBase}
                disabled={isViewer}
              >
                <option value="">— pick action —</option>
                {(INTEGRATION_ACTIONS[integration] || []).map(a => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
            )}
          </div>

          {/* Params */}
          {actionFields.length > 0 && (
            <div className="space-y-2 pt-2">
              {(() => {
                const requiredActionFields = actionFields.filter(f => f.required)
                const basicActionFields = requiredActionFields.length > 0 ? requiredActionFields : actionFields
                const optionalActionFields = requiredActionFields.length > 0
                  ? actionFields.filter(f => !f.required)
                  : []
                return (
                  <>
                    <span className={sectionLabel}>Parameters</span>
                    {basicActionFields.map(field => {
                      const rendered = renderField(field)
                      if (rendered === null) return null
                      return (
                        <div key={field.key}>
                          <div className="flex items-center gap-1.5 mb-1">
                            <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">{field.label}</label>
                            {field.required && <span className="text-red-500 text-[10px] font-bold">*</span>}
                            {field.hint && <span className="text-[10px] text-stone-400">{field.hint}</span>}
                          </div>
                          {rendered}
                        </div>
                      )
                    })}

                    {optionalActionFields.length > 0 && (
                      <>
                        <button
                          type="button"
                          className="w-full flex items-center gap-2 px-4 py-2 bg-transparent border-none cursor-pointer text-stone-500 hover:text-stone-700 transition-colors mt-2"
                          onClick={() => setShowAdvanced(v => !v)}
                          disabled={isViewer}
                        >
                          <span style={{ transform: showAdvanced ? "rotate(90deg)" : "none", transition: "transform 0.14s", display: "inline-block", fontSize: 12 }} className="text-stone-400">›</span>
                          <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Advanced</span>
                          <span className="text-[11px] text-stone-400 font-normal">{optionalActionFields.length} settings</span>
                          <div className="flex-1 h-px bg-stone-100 ml-1" />
                        </button>
                        {!showAdvanced && (
                          <p className="text-[11px] text-stone-400 px-4 pb-2">Power-user options — sensible defaults applied.</p>
                        )}
                      </>
                    )}

                    {showAdvanced && optionalActionFields.map(field => {
                      const rendered = renderField(field)
                      if (rendered === null) return null
                      return (
                        <div key={field.key}>
                          <div className="flex items-center gap-1.5 mb-1">
                            <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">{field.label}</label>
                            {field.hint && <span className="text-[10px] text-stone-400">{field.hint}</span>}
                          </div>
                          {rendered}
                        </div>
                      )
                    })}
                  </>
                )
              })()}
              <p className="text-[10px] text-stone-400 pt-1">
                Use <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code> to reference earlier outputs.
              </p>
            </div>
          )}

          {/* Secret warning */}
          {showAdvanced && (() => {
            const leaked = findHardcodedSecrets(getNestedValue(blockData, "config.params"))
            return leaked.length > 0 ? (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-800 mt-2">
                <p className="font-semibold mb-1">⚠ Secret in params: {leaked.join(", ")}</p>
                <p>Save credentials in <a href="/settings" className="underline">Settings</a> instead.</p>
              </div>
            ) : null
          })()}
        </div>
      )}

      {/* ── Static config fields (trigger, logic, output, approval) ── */}
      {staticFields.length > 0 && !isToolLike && blockType !== "brain" && blockType !== "mcp" && (
        <div className={section}>
          <span className={sectionLabel}>Configuration</span>
          <div className="space-y-3">
            {(() => {
              const requiredStaticFields = staticFields.filter(f => f.required)
              const basicStaticFields = requiredStaticFields.length > 0 ? requiredStaticFields : staticFields
              const visibleStaticFields = showAdvanced ? staticFields : basicStaticFields
              const hasAdvanced = requiredStaticFields.length > 0 && staticFields.length > basicStaticFields.length

              return (
                <>
                  {visibleStaticFields.map(field => {
                    const rendered = renderField(field)
                    if (rendered === null) return null
                    return (
                      <div key={field.key}>
                        <div className="flex items-center gap-1.5 mb-1">
                          <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">{field.label}</label>
                          {field.required && <span className="text-red-500 text-[10px] font-bold">*</span>}
                          {field.hint && <span className="text-[10px] text-stone-400">{field.hint}</span>}
                        </div>
                        {rendered}
                        {/* GitHub issue-labeled — webhook URL card + compact register panel */}
                        {blockType === "trigger" && field.key === "config.event_type" && triggerEventType === "github_issue_labeled" && (() => {
                          const base = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")
                          const webhookUrl = projectSlug && playbookSlug
                            ? `${base}/webhooks/github/${projectSlug}/${playbookSlug}`
                            : (() => {
                                const ws = typeof document !== "undefined"
                                  ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
                                return ws ? `${base}/webhooks/github?workspace_id=${ws}` : null
                              })()
                          return (
                            <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2.5 text-xs text-violet-800 mt-2 space-y-1.5">
                              <div className="flex items-center justify-between">
                                <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-500">GitHub Webhook</p>
                                {webhookUrl && (
                                  <button
                                    type="button"
                                    onClick={() => navigator.clipboard.writeText(webhookUrl)}
                                    className="text-[10px] font-medium text-violet-500 hover:text-violet-700 border border-violet-200 rounded px-1.5 py-0.5 transition-colors"
                                  >
                                    Copy
                                  </button>
                                )}
                              </div>
                              {webhookUrl
                                ? <p className="font-mono break-all text-violet-700 text-[11px]">{webhookUrl}</p>
                                : <p className="text-violet-400 text-[11px]">Select a workspace to see your URL</p>
                              }
                              <GitHubWebhookStatusPanel
                                workflowId={workflowId}
                                hookId={githubHookId ?? null}
                                hookRepo={githubHookRepo ?? null}
                                getToken={getToken}
                                onWebhookChange={onWebhookChange}
                                compact
                              />
                            </div>
                          )
                        })()}

                        {/* Inbound webhook URL panel */}
                        {blockType === "trigger" && field.key === "config.event_type" && triggerEventType === "webhook" && (() => {
                          const base = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")
                          const githubUrl = projectSlug && playbookSlug
                            ? `${base}/webhooks/github/${projectSlug}/${playbookSlug}`
                            : (() => {
                                const ws = typeof document !== "undefined"
                                  ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
                                return ws ? `${base}/webhooks/github?workspace_id=${ws}` : null
                              })()
                          const inboundUrl = `${(process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")}/webhooks/inbound/${workflowId}`
                          const webhookUrl = githubHookRepo ? githubUrl : inboundUrl
                          const displayUrl = webhookUrl ?? inboundUrl
                          return (
                            <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2.5 text-xs text-violet-800 mt-2 space-y-1.5">
                              <div className="flex items-center justify-between">
                                <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-500">
                                  {githubHookRepo ? "GitHub webhook" : "Webhook URL"}
                                </p>
                                {displayUrl && (
                                  <button
                                    type="button"
                                    onClick={() => displayUrl && navigator.clipboard.writeText(displayUrl)}
                                    className="text-[10px] font-medium text-violet-500 hover:text-violet-700 border border-violet-200 rounded px-1.5 py-0.5 transition-colors"
                                  >
                                    Copy
                                  </button>
                                )}
                              </div>
                              <p className="font-mono break-all text-violet-700 text-[11px]">
                                {displayUrl}
                              </p>
                              {githubHookRepo && githubWebhook
                                ? <GitHubWebhookStatusPanel
                                    workflowId={workflowId}
                                    hookId={githubHookId ?? null}
                                    hookRepo={githubHookRepo}
                                    getToken={getToken}
                                    onWebhookChange={onWebhookChange}
                                    compact
                                  />
                                : <>
                                    <p className="text-violet-500 text-[10px]">POST any JSON to this URL — payload available as <span className="font-mono">{"{{_trigger.*}}"}</span></p>
                                    <div className="border-t border-violet-100 pt-1.5 space-y-0.5">
                                      <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-400">GitHub setup</p>
                                      <p className="text-[10px] text-violet-500">Repo → Settings → Webhooks → Add webhook</p>
                                      <p className="text-[10px] text-violet-500">Content type: <span className="font-mono">application/json</span></p>
                                      <p className="text-[10px] text-violet-500">Events: choose individual → <span className="font-mono">Pull requests</span></p>
                                    </div>
                                  </>
                              }
                            </div>
                          )
                        })()}
                        {/* Vercel deployment trigger URL + auto-register panel */}
                        {blockType === "trigger" && field.key === "config.event_type" && isVercelTrigger && (() => {
                          const ws = typeof document !== "undefined"
                            ? document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1] : null
                          const webhookUrl = ws
                            ? `${(process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "")}/webhooks/vercel?workspace_id=${ws}`
                            : null
                          return (
                            <div className="mt-2 space-y-2">
                              <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2.5 text-xs text-violet-800 space-y-1.5">
                                <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-500">Vercel webhook URL</p>
                                {webhookUrl
                                  ? <p className="font-mono break-all select-all text-violet-700 text-[11px]">{webhookUrl}</p>
                                  : <p className="text-violet-400 text-[11px]">Select a workspace to see your URL</p>
                                }
                                <p className="text-violet-500 text-[10px]">Paste in Vercel → Project → Settings → Webhooks</p>
                                <div className="border-t border-violet-100 pt-1.5 space-y-0.5">
                                  <p className="text-[10px] text-violet-500">Payload available as <span className="font-mono">{"{{_trigger.vercel_webhook.*}}"}</span></p>
                                </div>
                              </div>
                              <VercelWebhookRegisterButton eventType={triggerEventType} getToken={getToken} />
                            </div>
                          )
                        })()}
                      </div>
                    )
                  })}

                  {hasAdvanced && (
                    <>
                      <button
                        type="button"
                        style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, background: "none", border: "none", padding: "8px 18px", cursor: "pointer" }}
                        onClick={() => setShowAdvanced(v => !v)}
                        disabled={isViewer}
                      >
                        <span style={{ transform: showAdvanced ? "rotate(90deg)" : "none", transition: "transform 0.14s", display: "inline-block", fontSize: 12, color: "var(--text-3)" }}>›</span>
                        <span className="eyebrow" style={{ fontSize: 10 }}>Advanced</span>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>{staticFields.length - basicStaticFields.length} settings</span>
                        <div style={{ flex: 1, height: 1, background: "var(--border)", marginLeft: 2 }} />
                      </button>
                    </>
                  )}
                </>
              )
            })()}
          </div>
        </div>
      )}

      {/* ── Memory blocks ── */}
      {blockType === "memory" && (() => {
        const action = (getNestedValue(blockData, "config.action") as string) || "read"
        const scope  = (getNestedValue(blockData, "config.scope")  as string) || "repo"
        const limit  = (getNestedValue(blockData, "config.limit")  as string) || "5"
        const summary = (getNestedValue(blockData, "config.summary") as string) || ""

        // Auto-derive key from scope — populate on first render if not set
        const autoKey = scope === "repo" ? "{{_trigger.repo_full_name}}" : "workspace"
        const currentKey = (getNestedValue(blockData, "config.key") as string) || ""
        if (!currentKey) {
          // Seed default key without blocking render
          setTimeout(() => handleFieldChange("config.key", autoKey), 0)
        }

        return (
          <>
            <div className={section}>
              <span className={sectionLabel}>Action</span>
              <select
                value={action}
                onChange={e => handleFieldChange("config.action", e.target.value)}
                className={inputBase}
                disabled={isViewer}
              >
                <option value="read">Read — recall past context</option>
                <option value="write">Write — record outcome</option>
              </select>
              <p className="text-[10px] text-stone-400 mt-1">
                {action === "read"
                  ? "Retrieves the most similar past summaries before the brain runs."
                  : "Stores a summary after the run so future runs can learn from it."}
              </p>
            </div>

            <div className={section}>
              <span className={sectionLabel}>Scope</span>
              <select
                value={scope}
                onChange={e => {
                  const newScope = e.target.value
                  const newKey = newScope === "repo" ? "{{_trigger.repo_full_name}}" : "workspace"
                  let updated = setNestedValue({ ...blockData }, "config.scope", newScope)
                  updated = setNestedValue(updated, "config.key", newKey)
                  onChange(blockId, updated)
                }}
                className={inputBase}
                disabled={isViewer}
              >
                <option value="repo">Repo — per repository</option>
                <option value="workspace">Workspace — shared across repos</option>
              </select>
            </div>

            <button
              type="button"
              className="w-full flex items-center gap-2 px-4 py-2 bg-transparent border-none cursor-pointer text-stone-500 hover:text-stone-700 transition-colors mt-2"
              onClick={() => setShowAdvanced(v => !v)}
              disabled={isViewer}
            >
              <span style={{ transform: showAdvanced ? "rotate(90deg)" : "none", transition: "transform 0.14s", display: "inline-block", fontSize: 12 }} className="text-stone-400">›</span>
              <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Advanced</span>
              <span className="text-[11px] text-stone-400 font-normal">3 settings</span>
              <div className="flex-1 h-px bg-stone-100 ml-1" />
            </button>
            {!showAdvanced && (
              <p className="text-[11px] text-stone-400 px-4 pb-2">Power-user options — sensible defaults applied.</p>
            )}

            {showAdvanced && (
              <>
                <div className={section}>
                  <span className={sectionLabel}>Key</span>
                  <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-50 border border-stone-200 rounded-lg">
                    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-mono font-medium bg-violet-100 text-violet-700 border border-violet-200">
                      {currentKey || autoKey}
                    </span>
                  </div>
                  <p className="text-[10px] text-stone-400 mt-1">
                    Auto-set from scope — groups memories by {scope === "repo" ? "repository" : "workspace"}.
                  </p>
                </div>

                {action === "read" && (
                  <div className={section}>
                    <span className={sectionLabel}>Max entries</span>
                    <input
                      type="number"
                      value={limit}
                      onChange={e => handleFieldChange("config.limit", e.target.value)}
                      min={1}
                      max={20}
                      className={cn(inputBase, "w-24")}
                      disabled={isViewer}
                    />
                    <p className="text-[10px] text-stone-400 mt-1">
                      Retrieved entries available as <code className="bg-stone-100 px-1 rounded">{"{{block_id.entries}}"}</code> in the brain prompt.
                    </p>
                  </div>
                )}

                {action === "write" && (
                  <div className={section}>
                    <span className={sectionLabel}>Summary template</span>
                    {summary ? (
                      <pre className="text-[11px] font-mono text-stone-700 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 whitespace-pre-wrap break-all leading-relaxed">
                        {summary}
                      </pre>
                    ) : (
                      <div className="rounded-lg border border-dashed border-stone-200 bg-stone-50 px-3 py-2.5 text-[11px] text-stone-400 leading-relaxed">
                        No summary template set. Edit the workflow YAML to add one.
                      </div>
                    )}
                    <p className="text-[10px] text-stone-400 mt-1">
                      Resolved at runtime — <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code> refs pull from block outputs.
                    </p>
                  </div>
                )}
              </>
            )}
          </>
        )
      })()}

      {/* ── Guard block ── */}
      {blockType === "guard" && (
        <GuardBlockPanel
          getToken={getToken}
          config={blockData}
          onChange={handleFieldChange}
          isAdmin={isAdmin}
          isViewer={isViewer}
        />
      )}

      {/* ── MCP block ── */}
      {blockType === "mcp" && (
        <MCPBlockPanel
          getToken={getToken}
          blockData={blockData}
          onChange={handleFieldChange}
          isViewer={isViewer}
        />
      )}

      {/* ── Brain: compiled prompt preview (collapsed by default) ── */}
      {blockType === "brain" && showAdvanced && (
        <div className="px-4 py-3">
          <button
            onClick={() => setPromptOpen(v => !v)}
            className="flex items-center gap-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider hover:text-stone-600 transition-colors"
          >
            <span>{promptOpen ? "▾" : "▸"}</span>
            Preview compiled prompt
            {isStreaming && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse ml-1" />}
          </button>
          {promptOpen && (
            <div className={cn(
              "mt-2 rounded-lg border bg-stone-950 px-3 py-2.5 text-xs font-mono text-green-300 leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto",
              isStreaming ? "border-amber-300/30" : "border-stone-700"
            )}>
              {streamedPrompt || (isStreaming
                ? <span className="text-stone-500">Generating…</span>
                : <span className="text-stone-500">Add a description to preview the prompt.</span>
              )}
              {isStreaming && streamedPrompt && (
                <span className="inline-block w-1.5 h-3.5 bg-green-400 ml-0.5 animate-pulse align-middle" />
              )}
            </div>
          )}
        </div>
      )}

      {/* Footer — close only; changes auto-save on every edit */}
      <div style={{ padding: "10px 18px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end" }} className="shrink-0 bg-white sticky bottom-0">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
      </div>

    </div>
  )
}
