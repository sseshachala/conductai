"use client"

import React from "react"
import { publicApiUrl } from "@/lib/auth/runtime"
import type { BlockType } from "@/lib/block-types"
import type { ConfigField } from "@/lib/config-schemas"
import { cn } from "@/lib/utils"
import { getNestedValue, setNestedValue } from "./field-utils"
import { GitHubWebhookStatusPanel, VercelWebhookRegisterButton } from "./webhook-panels"

export function StaticConfigSection({
  blockType, staticFields, isViewer, section, sectionLabel, renderField, showAdvanced, setShowAdvanced, workflowId, wsId, projectSlug, playbookSlug, githubHookRepo, githubHookId, githubWebhook, getToken, onWebhookChange, triggerEventType, isVercelTrigger,
}: {
  blockType: BlockType
  staticFields: ConfigField[]
  isViewer: boolean
  section: string
  sectionLabel: string
  renderField: (field: ConfigField) => React.ReactNode
  showAdvanced: boolean
  setShowAdvanced: React.Dispatch<React.SetStateAction<boolean>>
  workflowId: string
  wsId: string | null
  projectSlug?: string | null
  playbookSlug?: string | null
  githubHookRepo?: string | null
  githubHookId?: string | null
  githubWebhook?: boolean
  getToken?: (() => Promise<string | null>) | null
  onWebhookChange?: (hookId: string | null, hookRepo: string | null) => void
  triggerEventType: string
  isVercelTrigger: boolean
}) {
  return (
    <div className={section}>
      <span className={sectionLabel}>Configuration</span>
      <div className="space-y-3">
        {(() => {
          const visibleStaticFields = staticFields
          const hasAdvanced = false

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
                    {/* Logic block — available variables hint */}
                    {/* GitHub issue-labeled — webhook URL card + compact register panel */}
                    {blockType === "trigger" && field.key === "config.event_type" && triggerEventType === "github_issue_labeled" && (() => {
                      const base = (publicApiUrl() || "").replace(/\/$/, "")
                      const idP = workflowId ? workflowId.replace(/-/g, "").slice(0, 8) : ""
                      const webhookUrl = projectSlug && playbookSlug && idP
                        ? `${base}/webhooks/github/${projectSlug}/agent-${playbookSlug}-${idP}`
                        : wsId ? `${base}/webhooks/github?workspace_id=${wsId}` : null
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
                      const base = (publicApiUrl() || "").replace(/\/$/, "")
                      const idP = workflowId ? workflowId.replace(/-/g, "").slice(0, 8) : ""
                      const githubUrl = projectSlug && playbookSlug && idP
                        ? `${base}/webhooks/github/${projectSlug}/agent-${playbookSlug}-${idP}`
                        : wsId ? `${base}/webhooks/github?workspace_id=${wsId}` : null
                      const inboundUrl = `${(publicApiUrl() || "").replace(/\/$/, "")}/webhooks/inbound/${workflowId}`
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
                      const webhookUrl = wsId
                        ? `${(publicApiUrl() || "").replace(/\/$/, "")}/webhooks/vercel?workspace_id=${wsId}`
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
                    <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>{staticFields.length} settings</span>
                    <div style={{ flex: 1, height: 1, background: "var(--border)", marginLeft: 2 }} />
                  </button>
                </>
              )}
            </>
          )
        })()}
      </div>
    </div>
  )
}

export function MemoryBlockSection({
  blockData, blockId, onChange, isViewer, section, sectionLabel, inputBase, handleFieldChange,
}: {
  blockData: Record<string, unknown>
  blockId: string
  onChange: (blockId: string, changes: Record<string, unknown>) => void
  isViewer: boolean
  section: string
  sectionLabel: string
  inputBase: string
  handleFieldChange: (path: string, value: unknown) => void
}) {
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
    </>
  )
}
