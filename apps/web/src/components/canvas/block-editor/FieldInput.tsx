"use client"

import React, { useState } from "react"
import type { ConfigField } from "@/lib/config-schemas"
import { cn } from "@/lib/utils"

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

// ── Template ref chip — shown when a field's entire value is {{...}} ──────────

function TemplateRefChip({
  value,
  onEdit,
  onClear,
}: {
  value: string
  onEdit: () => void
  onClear: () => void
}) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 flex items-center gap-1.5 px-2.5 py-1.5 bg-stone-50 border border-stone-200 rounded-lg min-w-0">
        <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-mono font-medium bg-violet-100 text-violet-700 border border-violet-200 min-w-0 max-w-full truncate">
          {value}
        </span>
        <button
          type="button"
          onClick={onClear}
          title="Clear"
          className="shrink-0 text-stone-300 hover:text-stone-500 transition-colors leading-none"
          style={{ fontSize: 14 }}
        >
          ×
        </button>
      </div>
      <button
        type="button"
        onClick={onEdit}
        title="Edit expression"
        className="shrink-0 flex items-center justify-center w-7 h-7 rounded-lg border border-stone-200 bg-white text-stone-400 hover:text-violet-600 hover:border-violet-300 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
          <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
        </svg>
      </button>
    </div>
  )
}

// ── Config field renderer ─────────────────────────────────────────────────────

export function FieldInput({
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
  const [editingRef, setEditingRef] = React.useState(false)
  const editInputRef = React.useRef<HTMLInputElement | HTMLTextAreaElement>(null)

  // A single {{...}} expression that fills the entire field value
  const isTemplateRef = (v: string) => /^\{\{[^{}]+\}\}$/.test(v.trim())

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
    // Chip mode when entire value is a single {{...}} ref
    if (!field.readOnly && isTemplateRef(strVal) && !editingRef) {
      return (
        <TemplateRefChip
          value={strVal}
          onEdit={() => { setEditingRef(true); setTimeout(() => editInputRef.current?.focus(), 0) }}
          onClear={() => onChange("")}
        />
      )
    }
    return (
      <textarea
        ref={editInputRef as React.RefObject<HTMLTextAreaElement>}
        value={strVal}
        onChange={e => onChange(e.target.value)}
        onBlur={() => { if (isTemplateRef(strVal)) setEditingRef(false) }}
        rows={2}
        placeholder={field.placeholder}
        className={cn(base, "resize-none")}
        autoFocus={editingRef}
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

  // Default: text — chip mode when entire value is a single {{...}} ref
  if (!field.readOnly && isTemplateRef(strVal) && !editingRef) {
    return (
      <TemplateRefChip
        value={strVal}
        onEdit={() => { setEditingRef(true); setTimeout(() => editInputRef.current?.focus(), 0) }}
        onClear={() => onChange("")}
      />
    )
  }

  return (
    <input
      ref={editInputRef as React.RefObject<HTMLInputElement>}
      type="text"
      value={strVal}
      onChange={e => onChange(e.target.value)}
      onBlur={() => { if (isTemplateRef(strVal)) setEditingRef(false) }}
      placeholder={field.placeholder}
      className={base}
      autoFocus={editingRef}
    />
  )
}
