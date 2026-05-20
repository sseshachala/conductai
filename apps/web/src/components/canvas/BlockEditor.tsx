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
import { cn } from "@/lib/utils"

interface BlockEditorProps {
  workflowId: string
  blockId: string
  blockType: BlockType
  label: string
  description: string
  blockData: Record<string, unknown>
  onChange: (blockId: string, changes: Record<string, unknown>) => void
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
}: BlockEditorProps) {
  const [tab, setTab] = useState<"plain" | "config" | "advanced">("config")
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

  function handleFieldChange(path: string, value: unknown) {
    const updated = setNestedValue({ ...blockData }, path, value)
    onChange(blockId, updated)
  }

  // Stream whenever Advanced tab is open
  useEffect(() => {
    if (tab !== "advanced") return
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
  }, [tab, blockId, workflowId, description])

  useEffect(() => {
    setTab("config")
    setStreamedPrompt("")
    setIsStreaming(false)
  }, [blockId])

  return (
    <div className="bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <span className={cn("text-[9px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded", style.label)}>
            {style.labelText}
          </span>
          <span className="text-sm font-medium text-stone-700">{label}</span>
        </div>
        <div className="flex rounded-lg border border-stone-200 overflow-hidden text-xs">
          {(["config", "plain", "advanced"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn("px-3 py-1.5 font-medium capitalize transition-colors",
                tab === t ? "bg-stone-900 text-white" : "text-stone-500 hover:text-stone-700"
              )}
            >
              {t === "advanced" ? (
                <>Advanced {isStreaming && tab === "advanced" && (
                  <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                )}</>
              ) : t === "config" ? "Config" : "Plain English"}
            </button>
          ))}
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-3">

        {/* ── Plain English tab ── */}
        {tab === "plain" && (
          <div className="flex gap-4">
            <div className="w-40 shrink-0">
              <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">Name</label>
              <input
                value={label}
                onChange={e => onChange(blockId, { ...blockData, label: e.target.value })}
                className="mt-1 w-full rounded-lg border border-stone-200 px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="flex-1">
              <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
                What should this block do?
              </label>
              <textarea
                value={description}
                onChange={e => onChange(blockId, { ...blockData, description: e.target.value })}
                rows={3}
                placeholder="Describe in plain English…"
                className="mt-1 w-full rounded-lg border border-stone-200 px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
              />
            </div>
          </div>
        )}

        {/* ── Config tab ── */}
        {tab === "config" && (
          <div className="space-y-3">

            {/* Integration + Action pickers for tool-like blocks */}
            {isToolLike && (
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1">Integration</label>
                  <select
                    value={integration}
                    onChange={e => {
                      const updated = setNestedValue({ ...blockData }, "integration", e.target.value)
                      const withAction = setNestedValue(updated, "config.action", "")
                      onChange(blockId, withAction)
                    }}
                    className="w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"
                  >
                    <option value="">— pick one —</option>
                    {INTEGRATIONS.map(i => (
                      <option key={i.value} value={i.value}>{i.label}</option>
                    ))}
                  </select>
                </div>

                {integration && (
                  <div className="flex-1">
                    <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide block mb-1">Action</label>
                    <select
                      value={action}
                      onChange={e => handleFieldChange("config.action", e.target.value)}
                      className="w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"
                    >
                      <option value="">— pick one —</option>
                      {(INTEGRATION_ACTIONS[integration] || []).map(a => (
                        <option key={a.value} value={a.value}>{a.label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}

            {/* Static fields for this block type */}
            {staticFields.map(field => (
              <div key={field.key}>
                <div className="flex items-center gap-2 mb-1">
                  <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
                    {field.label}
                  </label>
                  {field.hint && (
                    <span className="text-[10px] text-stone-400">{field.hint}</span>
                  )}
                </div>
                <FieldInput
                  field={field}
                  value={getNestedValue(blockData, field.key)}
                  onChange={val => handleFieldChange(field.key, val)}
                />
              </div>
            ))}


            {/* Hardcoded-secret warning */}
            {(() => {
              const params = getNestedValue(blockData, "config.params")
              const leaked = findHardcodedSecrets(params)
              return leaked.length > 0 ? (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-800">
                  <p className="font-semibold mb-1">⚠ Secret detected in params: {leaked.join(", ")}</p>
                  <p className="leading-relaxed text-red-700">
                    Hardcoded tokens are exported in the YAML file and can leak if committed to a repo.
                    Save this credential in <a href="/settings" className="underline font-medium">Integrations → Settings</a> and
                    reference it via the <span className="font-mono bg-red-100 px-0.5 rounded">integration:</span> field instead.
                  </p>
                </div>
              ) : null
            })()}

            {/* Action-specific param fields */}
            {actionFields.length > 0 && (
              <div className="pt-1 border-t border-stone-100 space-y-3">
                <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">Parameters</p>
                {actionFields.map(field => (
                  <div key={field.key}>
                    <div className="flex items-center gap-2 mb-1">
                      <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
                        {field.label}
                      </label>
                      {field.hint && (
                        <span className="text-[10px] text-stone-400">{field.hint}</span>
                      )}
                    </div>
                    <FieldInput
                      field={field}
                      value={getNestedValue(blockData, field.key)}
                      onChange={val => handleFieldChange(field.key, val)}
                    />
                  </div>
                ))}
                <p className="text-[10px] text-stone-400 pt-1">
                  Tip: reference previous blocks with <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code>
                </p>
              </div>
            )}

            {/* Empty state */}
            {!isToolLike && staticFields.length === 0 && (
              <p className="text-sm text-stone-400 py-2">No configuration for this block type.</p>
            )}
          </div>
        )}

        {/* ── Advanced tab ── */}
        {tab === "advanced" && (
          <div className="relative">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
                Compiled prompt — auto-generated
              </label>
              {isStreaming && (
                <span className="text-[10px] text-amber-500 font-medium animate-pulse">Compiling…</span>
              )}
            </div>
            <div className={cn(
              "min-h-28 rounded-lg border bg-stone-950 px-3 py-2.5 text-xs font-mono text-green-300 leading-relaxed whitespace-pre-wrap",
              isStreaming ? "border-amber-300/30" : "border-stone-700"
            )}>
              {streamedPrompt || (
                isStreaming
                  ? <span className="text-stone-500">Generating<span className="animate-pulse">…</span></span>
                  : <span className="text-stone-500">Switch to Plain English, add a description, then come back here.</span>
              )}
              {isStreaming && streamedPrompt && (
                <span className="inline-block w-1.5 h-3.5 bg-green-400 ml-0.5 animate-pulse align-middle" />
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
