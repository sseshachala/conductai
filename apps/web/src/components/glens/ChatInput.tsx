"use client"
import { useEffect, useRef, useState } from "react"
import { SlashDropdown, SlashForm, filterTools, type SlashTool } from "@/components/glens/SlashPicker"

// ─── Input ────────────────────────────────────────────────────────────────────

export function ChatInput({ onSubmit, disabled }: { onSubmit: (t: string) => void; disabled: boolean }) {
  const [value, setValue] = useState("")
  const [pickedTool, setPickedTool] = useState<SlashTool | null>(null)
  // Escape sets this true to hide the picker without wiping the user's text;
  // clears when the value stops starting with "/" (fresh slate for next try).
  const [pickerDismissed, setPickerDismissed] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { if (!disabled && !pickedTool) ref.current?.focus() }, [disabled, pickedTool])
  useEffect(() => { if (!value.startsWith("/")) setPickerDismissed(false) }, [value])

  function submit() {
    const t = value.trim()
    if (t && !disabled) { onSubmit(t); setValue("") }
  }

  // Slash-command picker (#1630): only mount the dropdown when there are
  // real matches. Prevents an invisible dropdown from swallowing Enter for
  // messages that legitimately start with "/" (e.g. "/tmp/foo is broken").
  const slashMatches: SlashTool[] =
    value.startsWith("/") && !pickedTool && !pickerDismissed
      ? filterTools(value.slice(1))
      : []
  const showPicker = slashMatches.length > 0

  if (pickedTool) {
    return (
      <SlashForm
        tool={pickedTool}
        disabled={disabled}
        onSubmit={prompt => { onSubmit(prompt); setValue(""); setPickedTool(null) }}
        onCancel={() => { setPickedTool(null); setValue("") }}
      />
    )
  }

  const canSend = !disabled && value.trim().length > 0
  return (
    <div style={{
      position: "relative",
      border: "1px solid var(--border)",
      borderRadius: 16,
      background: "var(--surface-2)",
      padding: "10px 14px",
      transition: "border-color 120ms, box-shadow 120ms",
    }}>
      {showPicker && (
        <SlashDropdown
          matches={slashMatches}
          onSelect={t => { setPickedTool(t); setValue("") }}
          onClose={() => setPickerDismissed(true)}
        />
      )}
      <textarea
        ref={ref}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => {
          if (showPicker) return  // dropdown owns keys only while visible
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() }
        }}
        disabled={disabled}
        placeholder="Ask about your governance data… (type / for commands)"
        rows={2}
        style={{
          width: "100%",
          resize: "none",
          border: "none",
          padding: 0,
          paddingRight: 44,
          fontSize: 14,
          background: "transparent",
          color: "var(--text)",
          outline: "none",
          fontFamily: "inherit",
          lineHeight: 1.5,
          display: "block",
        }}
      />
      <button
        onClick={submit}
        disabled={!canSend}
        aria-label="Send"
        style={{
          position: "absolute",
          right: 8,
          bottom: 8,
          width: 32,
          height: 32,
          borderRadius: "50%",
          border: "none",
          background: canSend ? "var(--text)" : "var(--surface-3, rgba(0,0,0,0.08))",
          color: canSend ? "var(--surface)" : "var(--text-muted)",
          cursor: canSend ? "pointer" : "not-allowed",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "background 120ms, color 120ms",
          padding: 0,
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 19V5" />
          <path d="M5 12l7-7 7 7" />
        </svg>
      </button>
    </div>
  )
}
