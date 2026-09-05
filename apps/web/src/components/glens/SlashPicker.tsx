"use client"
import { useEffect, useMemo, useRef, useState } from "react"
import { API } from "@/lib/api"
import { useAuthFetch } from "@/hooks/useAuthFetch"

export type SlashArg = {
  name: string
  required: boolean
  placeholder?: string
  enum?: string[]
  /**
   * Named completer for per-arg autocomplete (PR 2). When set, the form
   * renders an ArgAutocomplete backed by COMPLETERS[completer] instead of a
   * free-text input. The stored value is the option's `value` (e.g. UUID);
   * the dropdown shows `label` + optional `sublabel`.
   */
  completer?: keyof typeof COMPLETERS
}

export type CompleterOption = { value: string; label: string; sublabel?: string }
type AuthFetch = (path: string, init?: RequestInit) => Promise<Response>
type CompleterFn = (authFetch: AuthFetch, workspaceId: string | null) => Promise<CompleterOption[]>

// Map arg completers → REST endpoints. Every endpoint already exists — no
// backend changes for this feature. Entries are wired to args in SLASH_TOOLS;
// dormant entries (budgets/agents/marketplace_packs) are ready for the
// #1300-#1304 mutators when they land.
export const COMPLETERS: Record<string, CompleterFn> = {
  workflows: async authFetch => {
    const r = await authFetch(`${API}/workflows`)
    if (!r.ok) throw new Error(`workflows ${r.status}`)
    const rows = (await r.json()) as Array<{ id: string; name: string; playbook_slug?: string | null }>
    return rows.map(w => ({
      value: w.playbook_slug || w.id,
      label: w.name,
      sublabel: w.playbook_slug ? `slug: ${w.playbook_slug}` : undefined,
    }))
  },
  pending_approvals: async authFetch => {
    const r = await authFetch(`${API}/guard/approvals?status=pending&limit=50`)
    if (!r.ok) throw new Error(`approvals ${r.status}`)
    const body = (await r.json()) as { items: Array<{ id: string; rule_message: string | null; tool_name: string | null }> }
    return body.items.map(a => ({
      value: a.id,
      label: a.rule_message || a.tool_name || a.id,
      sublabel: a.tool_name ? `tool: ${a.tool_name}` : undefined,
    }))
  },
  // Dormant until #1302 update_budget mutator lands and attaches completer.
  budgets: async authFetch => {
    const r = await authFetch(`${API}/guard/spend/budgets`)
    if (!r.ok) throw new Error(`budgets ${r.status}`)
    const rows = (await r.json()) as Array<{ id: string; email: string | null; monthly_limit_usd: number }>
    return rows.map(b => ({
      value: b.id,
      label: b.email || b.id,
      sublabel: `$${b.monthly_limit_usd}/mo`,
    }))
  },
  // Dormant until #1304 deactivate_agent_identity mutator lands.
  agents: async (authFetch, workspaceId) => {
    if (!workspaceId) return []
    const r = await authFetch(`${API}/workspaces/${workspaceId}/agent-identities?workspace_id=${workspaceId}`)
    if (!r.ok) throw new Error(`agents ${r.status}`)
    const rows = (await r.json()) as Array<{ id: string; name: string; provider: string }>
    return rows.map(a => ({
      value: a.id,
      label: a.name,
      sublabel: a.provider ? `provider: ${a.provider}` : undefined,
    }))
  },
  // Dormant until #1300 install_pack mutator lands.
  marketplace_packs: async authFetch => {
    const r = await authFetch(`${API}/compliance/packs/available`)
    if (!r.ok) throw new Error(`packs ${r.status}`)
    const rows = (await r.json()) as Array<{ slug: string; name: string; description?: string }>
    return rows.map(p => ({
      value: p.slug,
      label: p.name,
      sublabel: p.description || undefined,
    }))
  },
}

export type SlashTool = {
  name: string
  description: string
  args: SlashArg[]
}

// Static catalogue of user-invocable actor tools. Excludes
// confirm_pending_action / cancel_pending_action — those are LLM-only tools
// the chat flow uses to resolve natural-language "yes"/"no" replies.
// When new mutators from #1282 land (#1300-#1304), extend this list.
export const SLASH_TOOLS: SlashTool[] = [
  {
    name: "run_workflow",
    description: "Trigger a workflow run — requires confirmation.",
    args: [
      { name: "name_or_id", required: true, placeholder: "workflow name, slug, or UUID", completer: "workflows" },
      { name: "inputs", required: false, placeholder: 'optional JSON, e.g. {"key":"value"}' },
    ],
  },
  {
    name: "decide_approval",
    description: "Approve or reject a pending Guard approval — requires confirmation.",
    args: [
      { name: "approval_request_id", required: true, placeholder: "approval UUID", completer: "pending_approvals" },
      { name: "decision", required: true, enum: ["approved", "rejected"] },
      { name: "reason", required: false, placeholder: "required when rejecting" },
    ],
  },
]

// Compose a natural-language prompt from tool + filled args. The LLM receives
// this on the wire and emits a matching tool_use — same propose→confirm path
// as prose input. Prompt shape mirrors run_workflow's own description so the
// model has zero ambiguity about which tool to call.
export function composePrompt(tool: SlashTool, args: Record<string, string>): string {
  const parts = tool.args
    .filter(a => (args[a.name] ?? "").trim().length > 0)
    .map(a => `${a.name}=${JSON.stringify(args[a.name].trim())}`)
    .join(", ")
  return parts
    ? `Please run ${tool.name} with ${parts}.`
    : `Please run ${tool.name}.`
}

export function filterTools(query: string): SlashTool[] {
  const q = query.toLowerCase()
  return SLASH_TOOLS.filter(t => t.name.startsWith(q))
}

/**
 * Renders a listbox of matched tools. Caller controls whether to mount at all
 * (mount only when matches>0). Owns keyboard nav via a window listener that
 * lives only while mounted — safe because the parent won't mount an empty
 * dropdown, so the listener never runs when nothing is visible.
 */
export function SlashDropdown({
  matches,
  onSelect,
  onClose,
}: {
  matches: SlashTool[]
  onSelect: (tool: SlashTool) => void
  onClose: () => void
}) {
  const [idx, setIdx] = useState(0)

  useEffect(() => { setIdx(0) }, [matches])

  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (matches.length === 0) return
      if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(i + 1, matches.length - 1)) }
      else if (e.key === "ArrowUp") { e.preventDefault(); setIdx(i => Math.max(i - 1, 0)) }
      else if (e.key === "Enter") { e.preventDefault(); onSelect(matches[idx]) }
      else if (e.key === "Escape") { e.preventDefault(); onClose() }
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  }, [matches, idx, onSelect, onClose])

  if (matches.length === 0) return null

  return (
    <div
      role="listbox"
      aria-label="Slash command picker"
      style={{
        position: "absolute", bottom: "100%", left: 0, right: 0,
        marginBottom: 8, background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: 12,
        boxShadow: "0 8px 24px rgba(0,0,0,0.12)", overflow: "hidden", zIndex: 10,
      }}
    >
      {matches.map((t, i) => (
        <button
          key={t.name}
          role="option"
          aria-selected={i === idx}
          onClick={() => onSelect(t)}
          onMouseEnter={() => setIdx(i)}
          style={{
            display: "block", width: "100%", textAlign: "left",
            padding: "10px 14px", border: "none",
            background: i === idx ? "var(--surface-2)" : "transparent",
            color: "var(--text)", cursor: "pointer",
            borderBottom: i < matches.length - 1 ? "1px solid var(--border)" : "none",
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 13, fontFamily: "ui-monospace,monospace" }}>
            /{t.name}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
            {t.description}
          </div>
        </button>
      ))}
    </div>
  )
}

export function SlashForm({
  tool,
  onSubmit,
  onCancel,
  disabled,
}: {
  tool: SlashTool
  onSubmit: (prompt: string) => void
  onCancel: () => void
  disabled: boolean
}) {
  const [args, setArgs] = useState<Record<string, string>>({})
  const firstRef = useRef<HTMLInputElement | HTMLSelectElement | null>(null)

  useEffect(() => { firstRef.current?.focus() }, [])

  const canSubmit = tool.args
    .filter(a => a.required)
    .every(a => (args[a.name] ?? "").trim().length > 0)

  function submit() {
    if (!canSubmit || disabled) return
    onSubmit(composePrompt(tool, args))
  }

  function onFieldKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() }
    else if (e.key === "Escape") { e.preventDefault(); onCancel() }
  }

  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 16,
      background: "var(--surface-2)", padding: 12,
    }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 10, paddingBottom: 8, borderBottom: "1px solid var(--border)",
      }}>
        <div style={{
          fontWeight: 700, fontSize: 13,
          fontFamily: "ui-monospace,monospace", color: "var(--text)",
        }}>
          /{tool.name}
        </div>
        <button
          onClick={onCancel}
          aria-label="Close"
          style={{
            background: "transparent", border: "none", color: "var(--text-muted)",
            fontSize: 20, lineHeight: 1, cursor: "pointer", padding: 4,
          }}
        >×</button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {tool.args.map((arg, i) => (
          <label key={arg.name} style={{ display: "block" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 3 }}>
              {arg.name}{arg.required && <span style={{ color: "var(--err)" }}> *</span>}
            </div>
            {arg.enum ? (
              <select
                ref={el => { if (i === 0) firstRef.current = el }}
                value={args[arg.name] || ""}
                onChange={e => setArgs(a => ({ ...a, [arg.name]: e.target.value }))}
                onKeyDown={onFieldKey}
                style={fieldStyle}
              >
                <option value="">Select…</option>
                {arg.enum.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            ) : arg.completer ? (
              <ArgAutocomplete
                completer={arg.completer}
                value={args[arg.name] || ""}
                onChange={v => setArgs(a => ({ ...a, [arg.name]: v }))}
                onEnter={submit}
                onEscape={onCancel}
                placeholder={arg.placeholder || ""}
                autoFocus={i === 0}
              />
            ) : (
              <input
                ref={el => { if (i === 0) firstRef.current = el }}
                value={args[arg.name] || ""}
                onChange={e => setArgs(a => ({ ...a, [arg.name]: e.target.value }))}
                onKeyDown={onFieldKey}
                placeholder={arg.placeholder || ""}
                style={fieldStyle}
              />
            )}
          </label>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
        <button onClick={onCancel} className="btn btn-ghost btn-sm">Cancel</button>
        <button onClick={submit} disabled={!canSubmit || disabled} className="btn btn-primary btn-sm">
          Send
        </button>
      </div>
    </div>
  )
}

const fieldStyle: React.CSSProperties = {
  width: "100%", padding: "6px 10px", fontSize: 13,
  border: "1px solid var(--border)", borderRadius: 8,
  background: "var(--surface)", color: "var(--text)", outline: "none",
  fontFamily: "inherit",
}

/**
 * ArgAutocomplete (PR 2 / #1630).
 * Loads options once from COMPLETERS[completer], filters locally as the user
 * types, and stores the selected option's `value`. Free-text is allowed:
 * unmatched input passes through so power users can paste a UUID directly.
 */
export function ArgAutocomplete({
  completer,
  value,
  onChange,
  onEnter,
  onEscape,
  placeholder,
  autoFocus,
}: {
  completer: keyof typeof COMPLETERS
  value: string
  onChange: (val: string) => void
  onEnter: () => void
  onEscape: () => void
  placeholder?: string
  autoFocus?: boolean
}) {
  const { authFetch, workspaceId } = useAuthFetch()
  const [options, setOptions] = useState<CompleterOption[]>([])
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [idx, setIdx] = useState(0)
  const [query, setQuery] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { if (autoFocus) inputRef.current?.focus() }, [autoFocus])
  useEffect(() => () => { if (blurTimer.current) clearTimeout(blurTimer.current) }, [])

  useEffect(() => {
    let cancelled = false
    COMPLETERS[completer](authFetch, workspaceId)
      .then(opts => { if (!cancelled) setOptions(opts) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : "load failed") })
    return () => { cancelled = true }
  }, [completer, authFetch, workspaceId])

  const matches = useMemo(() => {
    if (!query.trim()) return options.slice(0, 20)
    const q = query.toLowerCase()
    return options
      .filter(o => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
      .slice(0, 20)
  }, [options, query])

  useEffect(() => { setIdx(0) }, [query])

  function select(opt: CompleterOption) {
    onChange(opt.value)
    setQuery(opt.label)
    setOpen(false)
  }

  return (
    <div style={{ position: "relative" }}>
      <input
        ref={inputRef}
        value={query}
        onChange={e => {
          setQuery(e.target.value)
          onChange(e.target.value)  // free-text pass-through
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 120) }}
        onKeyDown={e => {
          if (open && matches.length > 0) {
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(i + 1, matches.length - 1)); return }
            if (e.key === "ArrowUp")   { e.preventDefault(); setIdx(i => Math.max(i - 1, 0)); return }
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); select(matches[idx]); return }
          }
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onEnter() }
          else if (e.key === "Escape") { e.preventDefault(); setOpen(false); onEscape() }
        }}
        placeholder={placeholder}
        style={fieldStyle}
      />
      {open && matches.length > 0 && (
        <div
          role="listbox"
          aria-label="Autocomplete options"
          style={{
            position: "absolute", top: "100%", left: 0, right: 0,
            marginTop: 4, background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 8,
            maxHeight: 220, overflowY: "auto", zIndex: 20,
            boxShadow: "0 8px 16px rgba(0,0,0,0.08)",
          }}
        >
          {matches.map((o, i) => (
            <button
              key={o.value}
              role="option"
              aria-selected={i === idx}
              onMouseDown={e => e.preventDefault()}
              onClick={() => select(o)}
              onMouseEnter={() => setIdx(i)}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "6px 10px", border: "none", cursor: "pointer",
                background: i === idx ? "var(--surface-2)" : "transparent",
                color: "var(--text)", fontSize: 13,
                borderBottom: i < matches.length - 1 ? "1px solid var(--border)" : "none",
              }}
            >
              <div style={{ fontWeight: 500 }}>{o.label}</div>
              {o.sublabel && (
                <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 1 }}>
                  {o.sublabel}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
      {error && (
        <div style={{ fontSize: 11, color: "var(--err)", marginTop: 3 }}>
          Couldn't load options: {error}. Type manually.
        </div>
      )}
    </div>
  )
}
