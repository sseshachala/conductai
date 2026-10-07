"use client"

import { useState } from "react"

export function FieldLabel({
  label, hint, children, required, error, errorId,
}: {
  label: string
  hint?: string
  children: React.ReactNode
  required?: boolean
  error?: string
  errorId?: string
}) {
  return (
    <label style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {label}
        {required && <span aria-hidden="true" style={{ color: "var(--err)" }}>*</span>}
        {hint ? <HintIcon text={hint} /> : null}
      </span>
      {children}
      {error && <span id={errorId} style={{ color: "var(--err)", fontSize: 12 }}>{error}</span>}
    </label>
  )
}


// PR 7 review finding 7 — the previous inline textarea bound its
// ``value`` to the last-valid parsed ``extra_headers`` object. Typing
// the first ``{`` produced invalid JSON, wrote to ``extra_headers_raw``,
// and the next render resets the visible text to whatever was last
// parseable — so users literally couldn't type. This component keeps
// a local raw string state, seeded from either ``extra_headers_raw``
// or a pretty-printed ``extra_headers``, parses on every keystroke,
// and surfaces the error inline without wiping input.
export function CustomExtraHeadersField({
  value, disabled, onChange,
}: {
  value: Record<string, unknown> | undefined
  disabled: boolean
  onChange: (next: Record<string, unknown>) => void
}) {
  const seed = (() => {
    if (value && typeof value.extra_headers_raw === "string") return value.extra_headers_raw
    const eh = value?.extra_headers
    return eh && typeof eh === "object" ? JSON.stringify(eh, null, 2) : ""
  })()
  const [raw, setRaw] = useState(seed)
  const [error, setError] = useState<string | null>(null)

  return (
    <FieldLabel
      label="Extra headers (JSON)"
      hint='Optional static headers to send on every request. Must parse as a flat JSON object of strings, e.g. {"X-Team":"platform"}. Reserved names (authorization / cookie / content-* / any *api-key*) are refused.'
    >
      <textarea
        value={raw}
        disabled={disabled}
        placeholder='{"X-Team": "platform"}'
        onChange={e => {
          const text = e.target.value
          setRaw(text)
          const trimmed = text.trim()
          const next: Record<string, unknown> = { ...(value ?? {}) }
          if (!trimmed) {
            delete next.extra_headers
            delete next.extra_headers_raw
            setError(null)
            onChange(next)
            return
          }
          try {
            const parsed = JSON.parse(trimmed)
            if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
              throw new Error("must be a JSON object")
            }
            for (const [k, v] of Object.entries(parsed)) {
              if (typeof v !== "string") {
                throw new Error(`value for "${k}" must be a string`)
              }
            }
            next.extra_headers = parsed as Record<string, string>
            delete next.extra_headers_raw
            setError(null)
          } catch (err) {
            // Keep the raw text alongside a validation error so the
            // admin can fix without losing keystrokes. Publish still
            // sees ``extra_headers_raw`` — the server refuses that
            // key at the schema level, so a broken draft can't ship.
            delete next.extra_headers
            next.extra_headers_raw = text
            setError((err as Error).message || "invalid JSON")
          }
          onChange(next)
        }}
        style={{
          padding: 6,
          borderRadius: 4,
          border: `1px solid var(${error ? "--err-bd" : "--border"})`,
          background: "var(--surface)",
          color: "var(--text)",
          minHeight: 72,
          fontFamily: "monospace",
          fontSize: 11,
        }} />
      {error ? (
        <span style={{ fontSize: 11, color: "var(--err)" }}>
          {error} — publish will reject until this parses.
        </span>
      ) : null}
    </FieldLabel>
  )
}


export function HintIcon({ text }: { text: string }) {
  // Native `title` attribute has a ~700ms browser delay and doesn't
  // work on touch; custom hover popover renders instantly and is
  // reliable across desktops.
  const [show, setShow] = useState(false)
  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      <span
        role="img"
        aria-label={text}
        tabIndex={0}
        style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 14, height: 14, borderRadius: "50%",
          border: "1px solid var(--border)",
          fontSize: 10, fontWeight: 600, color: "var(--text-3)",
          cursor: "help", userSelect: "none",
        }}
      >i</span>
      {show ? (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: "50%",
            transform: "translateX(-50%)",
            padding: "6px 8px",
            background: "var(--text)",
            color: "var(--surface)",
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 400,
            lineHeight: 1.4,
            maxWidth: 240,
            width: "max-content",
            whiteSpace: "normal",
            textAlign: "left",
            zIndex: 1000,
            pointerEvents: "none",
            boxShadow: "0 4px 12px rgba(0,0,0,.15)",
          }}
        >
          {text}
        </span>
      ) : null}
    </span>
  )
}
