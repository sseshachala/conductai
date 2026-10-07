"use client"

import { useState, useEffect, useRef } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { BLOCK_STYLES, type BlockType } from "@/lib/block-types"
import { BLOCK_CONFIG_SCHEMAS, ACTION_FIELDS, type ConfigField } from "@/lib/config-schemas"
import { GitHubRepoField, GitHubBranchField, GitHubRepoAllowlistField } from "./GitHubRepoField"
import { cn } from "@/lib/utils"
import { useBlockSchemas, getSchemaRequiredKeys } from "@/hooks/useBlockSchemas"
import { useRoutingTable } from "@/hooks/useRoutingTable"
import { workflows } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"
import { getNestedValue, setNestedValue } from "./block-editor/field-utils"
import { FieldInput } from "./block-editor/FieldInput"
import { MCPBlockPanel } from "./block-editor/mcp-panels"
import { SandboxBlockPanel } from "./block-editor/SandboxBlockPanel"
import { BrainBlockSections, ToolBlockSection } from "./block-editor/brain-tool-sections"
import { TriggerBlockSection } from "./block-editor/TriggerBlockSection"
import { StaticConfigSection, MemoryBlockSection } from "./block-editor/config-memory-sections"

interface BlockEditorProps {
  workflowId: string
  blockId: string
  previousBlockId?: string
  isReadOnly?: boolean
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
  onDelete?: (blockId: string) => void
  sandboxBlocks?: { id: string; label: string }[]
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
  previousBlockId,
  isReadOnly = false,
  onClose,
  onDelete,
  sandboxBlocks,
}: BlockEditorProps) {
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id ?? null
  const [promptOpen, setPromptOpen] = useState(false)
  const [streamedPrompt, setStreamedPrompt] = useState<string>("")
  const [isStreaming, setIsStreaming] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showVarsHint, setShowVarsHint] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const style = BLOCK_STYLES[blockType] ?? BLOCK_STYLES["tool"]

  // Block schema registry — drives required-field markers and fallback rendering
  const { schemas: blockSchemas } = useBlockSchemas()
  // Model routing table — fetched from DB, falls back to hardcoded POLICY when loading
  const { table: routingTable } = useRoutingTable()

  const isToolLike = ["tool", "cleanup"].includes(blockType)
  const integration = (blockData.integration as string) || ""
  const action = (getNestedValue(blockData, "config.action") as string) || ""
  const triggerEventType = (getNestedValue(blockData, "config.event_type") as string) || ""

  // Derive config fields to show
  const VERCEL_EVENT_TYPES = new Set(["deployment.succeeded", "deployment.ready", "deployment.failed", "deployment.error"])
  const isVercelTrigger = VERCEL_EVENT_TYPES.has(triggerEventType)

  // Required keys from registry — used to show missing-field badges
  const schemaRequiredKeys = getSchemaRequiredKeys(blockSchemas, blockType, triggerEventType || undefined)

  // Trigger block has its own dedicated rendering section — excluded from staticFields.
  // For unknown block types (not in the static schema map), fall back to registry fields.
  const staticSchemaFields: ConfigField[] = (() => {
    const apiDef = blockSchemas?.[blockType]
    if (!apiDef) return []
    return apiDef.fields.map(f => ({
      key: f.key,
      label: f.label,
      type: (f.type as ConfigField["type"]) || "text",
      required: f.required,
      placeholder: f.placeholder,
      hint: f.hint,
      options: f.options,
      defaultValue: f.default,
    }))
  })()
  const allStaticFields = BLOCK_CONFIG_SCHEMAS[blockType as keyof typeof BLOCK_CONFIG_SCHEMAS] || staticSchemaFields
  const staticFields = blockType === "trigger"
    ? []
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
        if (wsId) headers["X-Workspace-ID"] = wsId
        const authFetch: AuthFetch = (url, opts) => fetch(url, { ...opts, headers: { ...headers, ...(opts?.headers as Record<string, string> | undefined) } })
        const res = await authFetch(
          workflows.blocks.compileStreamUrl(workflowId, blockId),
          {
            method: "POST",
            signal: abort.signal,
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
    // showAdvanced intentionally NOT reset — preserve user's expanded state on block switch
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
            <button className="btn btn-ghost btn-icon btn-sm" aria-label="Close" onClick={onClose}>×</button>
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

      {isReadOnly && (
        <div className="mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 flex items-center gap-2">
          <span>🔒</span>
          <span>Defined in base template — edit the playbook YAML to change this block.</span>
        </div>
      )}

      {/* ── Brain blocks ── */}
      {blockType === "brain" && (
        <BrainBlockSections
          blockData={blockData} blockId={blockId} onChange={onChange} isViewer={isViewer}
          section={section} sectionLabel={sectionLabel} inputBase={inputBase}
          playbookSlug={playbookSlug} routingTable={routingTable} getToken={getToken} selectedEnvId={selectedEnvId}
        />
      )}

      {/* ── Tool blocks: integration + action + params ── */}
      {isToolLike && (
        <ToolBlockSection
          blockData={blockData} blockId={blockId} onChange={onChange} isViewer={isViewer}
          section={section} sectionLabel={sectionLabel} inputBase={inputBase}
          renderField={renderField} handleFieldChange={handleFieldChange}
          showAdvanced={showAdvanced} setShowAdvanced={setShowAdvanced}
          integration={integration} action={action} actionFields={actionFields}
        />
      )}

      {/* ── Trigger block ── */}
      {blockType === "trigger" && (
        <TriggerBlockSection
          blockData={blockData} blockId={blockId} onChange={onChange} isViewer={isViewer}
          section={section} sectionLabel={sectionLabel} inputBase={inputBase}
          renderField={renderField} handleFieldChange={handleFieldChange}
          workflowId={workflowId} wsId={wsId} projectSlug={projectSlug} playbookSlug={playbookSlug}
          githubHookRepo={githubHookRepo} githubHookId={githubHookId} githubWebhook={githubWebhook}
          getToken={getToken} onWebhookChange={onWebhookChange}
          triggerEventType={triggerEventType} isVercelTrigger={isVercelTrigger}
        />
      )}

      {/* ── Static config fields (logic, output, approval) ── */}
      {staticFields.length > 0 && !isToolLike && blockType !== "brain" && blockType !== "mcp" && (
        <StaticConfigSection
          blockType={blockType} staticFields={staticFields} isViewer={isViewer}
          section={section} sectionLabel={sectionLabel} renderField={renderField}
          showAdvanced={showAdvanced} setShowAdvanced={setShowAdvanced}
          workflowId={workflowId} wsId={wsId} projectSlug={projectSlug} playbookSlug={playbookSlug}
          githubHookRepo={githubHookRepo} githubHookId={githubHookId} githubWebhook={githubWebhook}
          getToken={getToken} onWebhookChange={onWebhookChange}
          triggerEventType={triggerEventType} isVercelTrigger={isVercelTrigger}
        />
      )}

      {/* ── Memory blocks ── */}
      {blockType === "memory" && (
        <MemoryBlockSection
          blockData={blockData} blockId={blockId} onChange={onChange} isViewer={isViewer}
          section={section} sectionLabel={sectionLabel} inputBase={inputBase}
          handleFieldChange={handleFieldChange}
        />
      )}


      {/* ── MCP block ── */}
      {blockType === "mcp" && (
        <MCPBlockPanel
          getToken={getToken}
          blockData={blockData}
          onChange={handleFieldChange}
          isViewer={isViewer}
          environmentId={selectedEnvId}
        />
      )}

      {blockType === "sandbox" && (
        <SandboxBlockPanel
          blockData={blockData}
          blockId={blockId}
          onChange={onChange}
          isViewer={isViewer}
          sectionLabel={sectionLabel}
          section={section}
          inputBase={inputBase}
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

      {/* Footer — close + optional delete; changes auto-save on every edit */}
      <div style={{ padding: "10px 18px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }} className="shrink-0 bg-white sticky bottom-0">
        {schemaRequiredKeys.length > 0 && (() => {
          const def = blockSchemas?.[blockType]
          const allFields = def
            ? [...def.fields, ...(triggerEventType && def.subtypes?.[triggerEventType]?.fields ? def.subtypes[triggerEventType].fields : [])]
            : []
          const missing = schemaRequiredKeys
            .filter(key => !getNestedValue(blockData, key))
            .map(key => allFields.find(f => f.key === key)?.label || key)
          return missing.length > 0 ? (
            <p className="text-[10px] text-amber-600 flex items-start gap-1">
              <span>⚠</span>
              <span>
                <strong>{missing.length === 1 ? "Missing required field:" : `${missing.length} required fields missing:`}</strong>{" "}
                {missing.join(", ")}
              </span>
            </p>
          ) : (
            <p className="text-[10px] text-emerald-600 flex items-center gap-1"><span>✓</span> All required fields set</p>
          )
        })()}
        {schemaRequiredKeys.length === 0 && <span />}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {!isViewer && onDelete && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ color: "var(--err)" }}
              onClick={() => onDelete(blockId)}
            >
              Delete block
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
        </div>
      </div>

    </div>
  )
}
