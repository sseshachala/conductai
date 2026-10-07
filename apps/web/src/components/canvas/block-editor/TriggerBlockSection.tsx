"use client"

import React from "react"
import { publicApiUrl } from "@/lib/auth/runtime"
import { TRIGGER_CONFIG, type ConfigField } from "@/lib/config-schemas"
import { CRON_PRESETS, matchPreset } from "./routing"
import { getNestedValue, setNestedValue } from "./field-utils"
import { GitHubWebhookStatusPanel, VercelWebhookRegisterButton } from "./webhook-panels"

export function TriggerBlockSection({
  blockData, blockId, onChange, isViewer, section, sectionLabel, inputBase, renderField, handleFieldChange, workflowId, wsId, projectSlug, playbookSlug, githubHookRepo, githubHookId, githubWebhook, getToken, onWebhookChange, triggerEventType, isVercelTrigger,
}: {
  blockData: Record<string, unknown>
  blockId: string
  onChange: (blockId: string, changes: Record<string, unknown>) => void
  isViewer: boolean
  section: string
  sectionLabel: string
  inputBase: string
  renderField: (field: ConfigField) => React.ReactNode
  handleFieldChange: (path: string, value: unknown) => void
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
  const triggerOptions = [
    { value: "manual",                    label: "Manual run" },
    { value: "github_issue_labeled",       label: "GitHub — issue labeled" },
    { value: "github_issue_opened",        label: "GitHub — issue opened" },
    { value: "github_pr_opened",           label: "GitHub — PR opened" },
    { value: "github_pr_updated",          label: "GitHub — PR updated" },
    { value: "github_pr_merged",           label: "GitHub — PR merged" },
    { value: "github_pr_review_requested", label: "GitHub — PR review requested" },
    { value: "github_push",                label: "GitHub — push to branch" },
    { value: "github_issue_comment",       label: "GitHub — issue commented" },
    { value: "github_workflow_run",        label: "GitHub — CI run completed" },
    { value: "deployment.succeeded",       label: "Vercel — deployment succeeded" },
    { value: "deployment.ready",           label: "Vercel — deployment ready" },
    { value: "deployment.failed",          label: "Vercel — deployment failed" },
    { value: "webhook",                    label: "Inbound webhook" },
    { value: "schedule",                   label: "Schedule" },
  ]

  // Fields for the currently selected trigger type
  const typeFields = triggerEventType ? (TRIGGER_CONFIG[triggerEventType]?.fields ?? []) : []

  // Manual trigger inputs from the workflow YAML inputs: section
  const manualInputKeys = triggerEventType === "manual"
    ? Object.keys((blockData.inputs as Record<string, unknown>) ?? {})
    : []

  // Webhook URL helpers (reused from existing logic)
  const webhookBase = (publicApiUrl() || "").replace(/\/$/, "")
  const workspaceId = wsId
  const idPrefix = workflowId ? workflowId.replace(/-/g, "").slice(0, 8) : ""
  const githubWebhookUrl = projectSlug && playbookSlug && idPrefix
    ? `${webhookBase}/webhooks/github/${projectSlug}/agent-${playbookSlug}-${idPrefix}`
    : workspaceId ? `${webhookBase}/webhooks/github?workspace_id=${workspaceId}` : null
  const inboundWebhookUrl = `${webhookBase}/webhooks/inbound/${workflowId}`
  const vercelWebhookUrl = workspaceId
    ? `${webhookBase}/webhooks/vercel?workspace_id=${workspaceId}`
    : null

  return (
    <div className={section}>
      <span className={sectionLabel}>Configuration</span>
      <div className="space-y-3">

        {/* Trigger type selector */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">Trigger type</label>
            <span className="text-red-500 text-[10px] font-bold">*</span>
          </div>
          <select
            value={triggerEventType}
            onChange={e => {
              const et = e.target.value
              const newLabel = TRIGGER_CONFIG[et]?.label ?? "Trigger"
              const updated = setNestedValue({ ...blockData }, "config.event_type", et)
              onChange(blockId, { ...updated, label: newLabel })
            }}
            className={inputBase}
            disabled={isViewer}
          >
            <option value="">— select trigger type —</option>
            {triggerOptions.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* ── Per-type fields ── */}
        {triggerEventType === "schedule" ? (() => {
          const cronValue = (getNestedValue(blockData, "config.cron") as string) || ""
          const presetValue = matchPreset(cronValue)
          const isCustom = presetValue === "__custom__"
          return (
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">Schedule</label>
                <span className="text-red-500 text-[10px] font-bold">*</span>
              </div>
              <select
                value={presetValue}
                onChange={e => {
                  const v = e.target.value
                  if (v !== "__custom__") handleFieldChange("config.cron", v)
                  else handleFieldChange("config.cron", "")
                }}
                className={inputBase}
                disabled={isViewer}
              >
                {CRON_PRESETS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
              {isCustom && (
                <input
                  type="text"
                  value={cronValue}
                  onChange={e => handleFieldChange("config.cron", e.target.value)}
                  placeholder="0 9 * * 1-5"
                  className={`${inputBase} mt-2 font-mono`}
                  disabled={isViewer}
                />
              )}
              {!isCustom && cronValue && (
                <p className="text-[10px] text-stone-400 mt-1 font-mono">{cronValue}</p>
              )}
            </div>
          )
        })() : typeFields.map(field => {
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

        {/* ── Manual trigger: show inputs as "collected at run time" badges ── */}
        {triggerEventType === "manual" && (
          <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 space-y-2">
            <p className="text-[10px] font-semibold text-stone-500 uppercase tracking-wide">Inputs collected at run time</p>
            {manualInputKeys.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {manualInputKeys.map(k => (
                  <span key={k} className="inline-flex items-center px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[11px] font-medium border border-indigo-100">
                    {k}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-stone-400">No inputs declared in this workflow&#39;s <code className="bg-stone-100 px-1 rounded">inputs:</code> section.</p>
            )}
            <p className="text-[10px] text-stone-400">Values are prompted when the run is triggered manually or via the API.</p>
          </div>
        )}

        {/* ── GitHub issue-labeled: webhook URL + register panel ── */}
        {triggerEventType === "github_issue_labeled" && githubWebhookUrl && (
          <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2.5 text-xs text-violet-800 space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-500">GitHub Webhook</p>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(githubWebhookUrl)}
                className="text-[10px] font-medium text-violet-500 hover:text-violet-700 border border-violet-200 rounded px-1.5 py-0.5 transition-colors"
              >
                Copy
              </button>
            </div>
            <p className="font-mono break-all text-violet-700 text-[11px]">{githubWebhookUrl}</p>
            <GitHubWebhookStatusPanel
              workflowId={workflowId}
              hookId={githubHookId ?? null}
              hookRepo={githubHookRepo ?? null}
              getToken={getToken}
              onWebhookChange={onWebhookChange}
              compact
            />
          </div>
        )}

        {/* ── Webhook trigger: inbound webhook URL ── */}
        {triggerEventType === "webhook" && (
          <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2.5 text-xs text-violet-800 space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-500">
                {githubHookRepo ? "GitHub webhook" : "Webhook URL"}
              </p>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(githubHookRepo ? (githubWebhookUrl ?? inboundWebhookUrl) : inboundWebhookUrl)}
                className="text-[10px] font-medium text-violet-500 hover:text-violet-700 border border-violet-200 rounded px-1.5 py-0.5 transition-colors"
              >
                Copy
              </button>
            </div>
            <p className="font-mono break-all text-violet-700 text-[11px]">
              {githubHookRepo ? (githubWebhookUrl ?? inboundWebhookUrl) : inboundWebhookUrl}
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
        )}

        {/* ── Vercel trigger: webhook URL + auto-register ── */}
        {isVercelTrigger && (
          <div className="mt-2 space-y-2">
            <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2.5 text-xs text-violet-800 space-y-1.5">
              <p className="font-semibold text-[10px] uppercase tracking-wide text-violet-500">Vercel webhook URL</p>
              {vercelWebhookUrl
                ? <p className="font-mono break-all select-all text-violet-700 text-[11px]">{vercelWebhookUrl}</p>
                : <p className="text-violet-400 text-[11px]">Select a workspace to see your URL</p>
              }
              <p className="text-violet-500 text-[10px]">Paste in Vercel → Project → Settings → Webhooks</p>
              <div className="border-t border-violet-100 pt-1.5 space-y-0.5">
                <p className="text-[10px] text-violet-500">Payload available as <span className="font-mono">{"{{_trigger.vercel_webhook.*}}"}</span></p>
              </div>
            </div>
            <VercelWebhookRegisterButton eventType={triggerEventType} getToken={getToken} />
          </div>
        )}

        {/* ── Signing secret — inbound webhook only ── */}
        {triggerEventType === "webhook" && (() => {
          const secret = (getNestedValue(blockData, "config.webhook_secret") as string) || ""
          return (
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">Signing secret</label>
                <span className="text-[10px] text-stone-400">optional</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="flex-1 font-mono text-[11px] text-stone-500 bg-stone-50 border border-stone-200 rounded px-2.5 py-1.5 truncate">
                  {secret || "auto-generated on install"}
                </span>
                {secret && (
                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(secret)}
                    className="text-[10px] font-medium text-stone-500 hover:text-stone-700 border border-stone-200 rounded px-1.5 py-1 transition-colors shrink-0"
                  >
                    Copy
                  </button>
                )}
              </div>
              <p className="text-[10px] text-stone-400 mt-1">Requires X-Webhook-Signature header when set.</p>
            </div>
          )
        })()}

      </div>
    </div>
  )
}
