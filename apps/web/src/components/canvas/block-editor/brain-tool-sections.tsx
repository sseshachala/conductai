"use client"

import React from "react"
import { BLOCK_CONFIG_SCHEMAS, INTEGRATION_ACTIONS, INTEGRATIONS, type ConfigField } from "@/lib/config-schemas"
import { cn } from "@/lib/utils"
import type { RoutingTable } from "@/hooks/useRoutingTable"
import { previewModel } from "./routing"
import { findHardcodedSecrets, getNestedValue, setNestedValue } from "./field-utils"
import { FieldInput } from "./FieldInput"
import { BrainMCPSection } from "./mcp-panels"

export function BrainBlockSections({
  blockData, blockId, onChange, isViewer, section, sectionLabel, inputBase, playbookSlug, routingTable, getToken, selectedEnvId,
}: {
  blockData: Record<string, unknown>
  blockId: string
  onChange: (blockId: string, changes: Record<string, unknown>) => void
  isViewer: boolean
  section: string
  sectionLabel: string
  inputBase: string
  playbookSlug?: string | null
  routingTable: RoutingTable | null
  getToken?: (() => Promise<string | null>) | null
  selectedEnvId?: string
}) {
  return (
    <>
      <div className={section}>
        <span className={sectionLabel}>What should this step do?</span>
        <textarea
          value={(blockData.custom_instructions as string) || ""}
          onChange={e => onChange(blockId, { ...blockData, custom_instructions: e.target.value })}
          rows={6}
          placeholder="Describe what this AI step should do in plain English. e.g. &quot;Review the PR diff for security issues and post a summary comment.&quot;"
          className={cn(inputBase, "resize-none")}
          disabled={isViewer}
        />
        <p className="text-[10px] text-stone-400 mt-1">
          Use <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code> to reference outputs from earlier steps.
        </p>
      </div>

      {/* ── Guardrails ── */}
      <div className={section}>
        <span className={sectionLabel}>Guardrails</span>
        <div className="space-y-2">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={!!(blockData.rollback_on_failure as boolean)}
              onChange={e => onChange(blockId, { ...blockData, rollback_on_failure: e.target.checked })}
              disabled={isViewer}
              className="h-3.5 w-3.5 rounded border-stone-300 text-indigo-500 accent-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed"
            />
            <span className="text-xs text-stone-600">Rollback on failure</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={!!(blockData.require_tests_pass as boolean)}
              onChange={e => onChange(blockId, { ...blockData, require_tests_pass: e.target.checked })}
              disabled={isViewer}
              className="h-3.5 w-3.5 rounded border-stone-300 text-indigo-500 accent-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed"
            />
            <span className="text-xs text-stone-600">Require tests to pass before commit</span>
          </label>
        </div>
        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between gap-4">
            <label className="text-xs text-stone-600 shrink-0">Max retries per item</label>
            <input
              type="number"
              min={0}
              max={20}
              value={blockData.max_retries !== undefined ? (blockData.max_retries as number) : 3}
              onChange={e => onChange(blockId, { ...blockData, max_retries: Number(e.target.value) })}
              disabled={isViewer}
              className="w-16 border border-stone-200 rounded-lg px-2 py-1 text-xs text-stone-900 text-right focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white disabled:opacity-60 disabled:cursor-not-allowed"
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <label className="text-xs text-stone-600 shrink-0">Max cost ($)</label>
            <input
              type="number"
              min={0}
              step={0.50}
              value={blockData.max_cost_usd !== undefined ? (blockData.max_cost_usd as number) : 2.00}
              onChange={e => onChange(blockId, { ...blockData, max_cost_usd: Number(e.target.value) })}
              disabled={isViewer}
              className="w-16 border border-stone-200 rounded-lg px-2 py-1 text-xs text-stone-900 text-right focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white disabled:opacity-60 disabled:cursor-not-allowed"
            />
          </div>
        </div>
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
              <strong>Can use tools</strong> — reads files, edits code, runs commands, and pushes branches.
            </span>
          ) : (
            <span className="text-stone-500 border-stone-100 bg-stone-50 rounded-lg">
              <strong>Single call</strong> — responds once with text only. No file access, no commands.
            </span>
          )}
        </p>
      </div>

      <div className={section}>
        <span className={sectionLabel}>Model</span>
        <select
          value={(blockData.routingPreference as string) || "balanced"}
          onChange={e => onChange(blockId, { ...blockData, routingPreference: e.target.value })}
          className={cn(inputBase)}
          disabled={isViewer}
        >
          {(["balanced", "quality", "speed", "cost"] as const).map(pref => {
            const [provider, model] = previewModel(playbookSlug, pref, undefined, routingTable)
            const prefLabel = pref.charAt(0).toUpperCase() + pref.slice(1)
            return <option key={pref} value={pref}>{prefLabel} — {provider} · {model}</option>
          })}
        </select>
      </div>

      <BrainMCPSection
        getToken={getToken}
        blockData={blockData}
        blockId={blockId}
        onChange={onChange}
        isViewer={isViewer}
        environmentId={selectedEnvId}
        section={section}
        sectionLabel={sectionLabel}
      />
    </>
  )
}

export function ToolBlockSection({
  blockData, blockId, onChange, isViewer, section, sectionLabel, inputBase, renderField, handleFieldChange, showAdvanced, setShowAdvanced, integration, action, actionFields,
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
  showAdvanced: boolean
  setShowAdvanced: React.Dispatch<React.SetStateAction<boolean>>
  integration: string
  action: string
  actionFields: ConfigField[]
}) {
  return (
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
  )
}
