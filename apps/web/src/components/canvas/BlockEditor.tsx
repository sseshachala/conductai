"use client"

import { useState, useEffect, useRef } from "react"
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

  const base = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"

  if (field.readOnly) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-50 border border-stone-200 rounded-lg">
        <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 shrink-0">auto</span>
        <span className="text-xs font-mono text-stone-500 truncate">{strVal || field.placeholder}</span>
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
}: BlockEditorProps) {
  const [promptOpen, setPromptOpen] = useState(false)
  const [streamedPrompt, setStreamedPrompt] = useState<string>("")
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const style = BLOCK_STYLES[blockType]

  const isToolLike = ["tool", "cleanup"].includes(blockType)
  const integration = (blockData.integration as string) || ""
  const action = (getNestedValue(blockData, "config.action") as string) || ""
  const triggerEventType = (getNestedValue(blockData, "config.event_type") as string) || ""

  // Derive config fields to show — filter trigger fields to only what's relevant
  const allStaticFields = BLOCK_CONFIG_SCHEMAS[blockType] || []
  const staticFields = blockType === "trigger"
    ? allStaticFields.filter(f => {
        if (f.key === "config.label" || f.key === "config.repo_allowlist")
          return triggerEventType === "github_issue_labeled"
        if (f.key === "config.cron")
          return triggerEventType === "schedule"
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
      return (
        <GitHubRepoAllowlistField
          value={(val as string) || ""}
          getToken={getToken}
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
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/blocks/${blockId}/compile/stream`,
          {
            method: "POST",
            signal: abort.signal,
            headers: { "Content-Type": "application/json" },
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
  }, [promptOpen, blockId, workflowId, description])

  useEffect(() => {
    setPromptOpen(false)
    setStreamedPrompt("")
    setIsStreaming(false)
  }, [blockId])

  const section = "px-4 py-3 space-y-3 border-b border-stone-100"
  const sectionLabel = "text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2 block"
  const inputBase = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"

  return (
    <div className="bg-white flex flex-col h-full overflow-y-auto">

      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-100 shrink-0">
        <span className={cn("text-[9px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded shrink-0", style.label)}>
          {style.labelText}
        </span>
        <input
          value={label}
          onChange={e => onChange(blockId, { ...blockData, label: e.target.value })}
          className="flex-1 text-sm font-medium text-stone-800 bg-transparent border-0 outline-none focus:bg-stone-50 rounded px-1 -mx-1 min-w-0"
          placeholder="Block name"
        />
      </div>

      {/* ── Brain blocks: system prompt + custom instructions ── */}
      {blockType === "brain" && (
        <>
          <div className={section}>
            <div className="flex items-center justify-between">
              <span className={sectionLabel}>System prompt</span>
              <span className="text-[10px] text-stone-400 bg-stone-100 px-1.5 py-0.5 rounded mb-2">read-only</span>
            </div>
            <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-xs text-stone-600 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
              <SystemPromptWithChips text={description} />
            </div>
            <p className="text-[10px] text-stone-400 mt-1 flex items-center gap-2">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-sm bg-violet-200 border border-violet-300" />
                template ref
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block w-2 h-2 rounded-sm bg-red-100 border border-red-200" />
                literal placeholder
              </span>
            </p>
          </div>

          <div className={section}>
            <span className={sectionLabel}>Your instructions</span>
            <textarea
              value={(blockData.custom_instructions as string) || ""}
              onChange={e => onChange(blockId, { ...blockData, custom_instructions: e.target.value })}
              rows={3}
              placeholder="Add constraints or focus areas. Avoid overriding steps from the system prompt above."
              className={cn(inputBase, "resize-none")}
            />
          </div>

          <div className={section}>
            <span className={sectionLabel}>Mode</span>
            {BLOCK_CONFIG_SCHEMAS.brain?.map(field => (
              <div key={field.key}>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-stone-600">{field.label}</span>
                  <FieldInput field={field} value={blockData.isAgentic} onChange={v => onChange(blockId, { ...blockData, isAgentic: v })} />
                </div>
                {field.hint && <p className="text-[10px] text-stone-400 mt-1">{field.hint}</p>}
              </div>
            ))}
          </div>
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
            >
              <option value="">— pick integration —</option>
              {INTEGRATIONS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
            </select>

            {integration && (
              <select
                value={action}
                onChange={e => handleFieldChange("config.action", e.target.value)}
                className={inputBase}
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
              <span className={sectionLabel}>Parameters</span>
              {actionFields.map(field => {
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
              <p className="text-[10px] text-stone-400 pt-1">
                Tip: reference previous blocks with <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code>
              </p>
            </div>
          )}

          {/* GitHub webhook — auto-register info (no button, fires on Run) */}
          {blockType === "trigger" && triggerEventType === "github_issue_labeled" && (() => {
            const repoAllowlist = (getNestedValue(blockData, "config.repo_allowlist") as string) || ""
            const firstRepo = repoAllowlist.split(",")[0].trim()
            const [owner, repo] = firstRepo.includes("/") ? firstRepo.split("/") : ["", ""]
            if (!owner || !repo) return null
            return (
              <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700 mt-2">
                Webhook on <span className="font-mono font-medium">{owner}/{repo}</span> will be registered automatically when you run.
              </div>
            )
          })()}

          {/* Secret warning */}
          {(() => {
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
      {staticFields.length > 0 && !isToolLike && (
        <div className={section}>
          <span className={sectionLabel}>Configuration</span>
          <div className="space-y-3">
            {staticFields.map(field => {
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
          </div>
        </div>
      )}

      {/* ── Brain: compiled prompt preview (collapsed by default) ── */}
      {blockType === "brain" && (
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

    </div>
  )
}
