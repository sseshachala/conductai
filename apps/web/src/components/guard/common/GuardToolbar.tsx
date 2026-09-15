// Consolidated Guard toolbar primitives + composed layout.
//
// Introduced with #1982 for the Guard Activity page (`/logs/guard`), but
// every piece is deliberately generic so Inbox, Approvals, Spend, or any
// future Guard surface can compose the same four surfaces without
// duplicating the popover + dropdown logic:
//
//   RealtimeBadge   — pause/resume live stream toggle
//   StatusDropdown  — single-select filter chips folded into a dropdown
//   FiltersPopover  — developer + tool + date + rule + toggles in one popover
//   ExportMenu      — CSV / SOC 2 / any future report action
//   ColumnsMenu     — checkbox list of visible table columns (localStorage)
//
// `GuardToolbar` composes the five into a single row. Pages that need a
// different arrangement should import the primitives individually.

"use client"

import { useCallback, useMemo, useState } from "react"
import { useClickOutside } from "@/hooks/useClickOutside"

// Every column the Flight Recorder table can render, in display order.
// Note: input_summary text renders inside the Action cell rather than as
// a separate column — the row was originally designed that way and
// keeping the merge lets Action stay wide enough to show both the tool
// call and its inputs on the same line.
export const ALL_COLUMNS = [
  { key: "time", label: "Time" },
  { key: "actor", label: "Actor" },
  { key: "tool", label: "Tool" },
  { key: "call", label: "Action" },
  { key: "decision", label: "Decision" },
  { key: "rule", label: "Rule" },
  { key: "blast", label: "Blast Radius" },
  // #1959 Phase 3 — opt-in durable-audit lifecycle column. Legacy rows
  // read NULL and render as em dash so the column adds no noise for
  // workspaces still on the single-phase writer.
  { key: "lifecycle", label: "Lifecycle" },
] as const

export type ColumnKey = (typeof ALL_COLUMNS)[number]["key"]

// #1982 acceptance criteria: 6 columns default, Blast Radius opt-in.
// (Input was originally listed as an opt-in column but the row renders
// it merged into Action — a separate column would produce empty cells.)
export const DEFAULT_VISIBLE_COLUMNS: ColumnKey[] = [
  "time", "actor", "tool", "call", "decision", "rule",
]

const STORAGE_KEY = "guard-activity-visible-columns.v1"

// Load the persisted column set. Safe on the server — falls back to defaults
// during SSR then re-hydrates once useEffect runs. Corrupt or absent entries
// silently reset to the default so a mangled localStorage never breaks the
// page.
export function loadVisibleColumns(): ColumnKey[] {
  if (typeof window === "undefined") return DEFAULT_VISIBLE_COLUMNS
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_VISIBLE_COLUMNS
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return DEFAULT_VISIBLE_COLUMNS
    const validKeys = new Set(ALL_COLUMNS.map(c => c.key))
    const filtered = parsed.filter((k): k is ColumnKey => typeof k === "string" && validKeys.has(k as ColumnKey))
    // Ensure at least one column stays visible so the table isn't a blank row.
    return filtered.length > 0 ? filtered : DEFAULT_VISIBLE_COLUMNS
  } catch {
    return DEFAULT_VISIBLE_COLUMNS
  }
}

export function saveVisibleColumns(cols: ColumnKey[]): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cols))
  } catch {
    // localStorage full / disabled — silently ignore. The state is still
    // held in React for the session; only cross-session persistence fails.
  }
}

// ─── Realtime toggle badge ────────────────────────────────────────────────

export function RealtimeBadge({
  streaming, onToggle,
}: { streaming: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      aria-pressed={streaming}
      aria-label={streaming ? "Pause realtime stream" : "Resume realtime stream"}
      className="btn btn-ghost btn-sm"
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        fontSize: 12, fontWeight: 500,
      }}
    >
      <span
        className={streaming ? "conduct-pulse-dot" : ""}
        style={{
          width: 8, height: 8, borderRadius: 4,
          background: streaming ? "var(--ok)" : "var(--text-muted)",
        }}
      />
      {streaming ? "Realtime" : "Paused"}
    </button>
  )
}

// ─── Status dropdown (single-select) ──────────────────────────────────────

type StatusValue = "" | "blocked" | "warned" | "allowed"
const STATUS_OPTIONS: { value: StatusValue; label: string }[] = [
  { value: "", label: "All" },
  { value: "blocked", label: "Blocked" },
  { value: "warned", label: "Warned" },
  { value: "allowed", label: "Allowed" },
]

export function StatusDropdown({
  active, onChange,
}: { active: StatusValue; onChange: (v: StatusValue) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false))
  const activeLabel = STATUS_OPTIONS.find(o => o.value === active)?.label ?? "All"

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="btn btn-ghost btn-sm"
        style={{ fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4 }}
      >
        Status: <strong style={{ fontWeight: 600 }}>{activeLabel}</strong>
        <span aria-hidden style={{ marginLeft: 2, fontSize: 10 }}>▼</span>
      </button>
      {open && (
        <ul
          role="listbox"
          style={{
            position: "absolute", top: "100%", left: 0, marginTop: 4,
            minWidth: 140, padding: 4, listStyle: "none",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            zIndex: 20,
          }}
        >
          {STATUS_OPTIONS.map(o => (
            <li key={o.value || "all"}>
              <button
                role="option"
                aria-selected={o.value === active}
                onClick={() => { onChange(o.value); setOpen(false) }}
                style={{
                  width: "100%", textAlign: "left", padding: "6px 10px",
                  fontSize: 12, borderRadius: 4, border: "none",
                  background: o.value === active ? "var(--accent-weak)" : "transparent",
                  color: o.value === active ? "var(--accent-text)" : "var(--text-2)",
                  cursor: "pointer",
                }}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── Filters popover ──────────────────────────────────────────────────────

export interface FiltersPopoverProps {
  developer: string
  onDeveloperChange: (v: string) => void
  developers: string[]
  canViewAllActivity: boolean
  tool: string
  onToolChange: (v: string) => void
  tools: string[]
  since: string
  onSinceChange: (v: string) => void
  until: string
  onUntilChange: (v: string) => void
  ruleId: string
  onClearRule: () => void
  groupByGoal: boolean
  onGroupByGoalChange: (v: boolean) => void
  onClearAll: () => void
}

const TOOL_NAMES: Record<string, string> = {
  "claude-code": "Claude Code", "claude_code": "Claude Code",
  "claude_chat": "Claude.ai", "claude-chat": "Claude.ai",
  "claude_desktop": "Claude Desktop", "claude-desktop": "Claude Desktop",
  "claude_work": "Claude Work", "claude-work": "Claude Work",
  "codex": "Codex", "codex_cli": "Codex CLI", "codex_chat": "Codex Chat",
  "cursor": "Cursor", "windsurf": "Windsurf", "copilot": "Copilot", "gemini": "Gemini",
}

export function FiltersPopover(p: FiltersPopoverProps) {
  const [open, setOpen] = useState(false)
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false))
  const activeCount = [p.developer, p.tool, p.since, p.until, p.ruleId, p.groupByGoal ? "grp" : ""].filter(Boolean).length

  const selectStyle = {
    fontSize: 12, padding: "5px 8px", borderRadius: 4,
    border: "1px solid var(--border)", background: "var(--surface)",
    color: "var(--text-1)", minWidth: 160,
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="btn btn-ghost btn-sm"
        style={{ fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4 }}
      >
        Filters
        {activeCount > 0 && (
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            minWidth: 18, height: 18, padding: "0 5px",
            borderRadius: 9, fontSize: 10, fontWeight: 700,
            background: "var(--accent-weak)", color: "var(--accent-text)",
          }}>{activeCount}</span>
        )}
        <span aria-hidden style={{ marginLeft: 2, fontSize: 10 }}>▼</span>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Filters"
          style={{
            position: "absolute", top: "100%", left: 0, marginTop: 4,
            width: 280, padding: 12,
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            display: "flex", flexDirection: "column", gap: 10, zIndex: 20,
          }}
        >
          {p.canViewAllActivity && (
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)" }}>
              Developer
              <select value={p.developer} onChange={e => p.onDeveloperChange(e.target.value)}
                      style={{ ...selectStyle, width: "100%", marginTop: 4 }}>
                <option value="">All developers</option>
                {p.developers.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
          )}

          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)" }}>
            Tool
            <select value={p.tool} onChange={e => p.onToolChange(e.target.value)}
                    style={{ ...selectStyle, width: "100%", marginTop: 4 }}>
              <option value="">All tools</option>
              {p.tools.map(t => <option key={t} value={t}>{TOOL_NAMES[t] ?? t}</option>)}
            </select>
          </label>

          <div style={{ display: "flex", gap: 8 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", flex: 1 }}>
              From
              <input type="date" value={p.since} onChange={e => p.onSinceChange(e.target.value)}
                     style={{ ...selectStyle, width: "100%", marginTop: 4 }} />
            </label>
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", flex: 1 }}>
              To
              <input type="date" value={p.until} onChange={e => p.onUntilChange(e.target.value)}
                     style={{ ...selectStyle, width: "100%", marginTop: 4 }} />
            </label>
          </div>

          {p.ruleId && (
            <div style={{
              fontSize: 11, padding: "5px 8px", borderRadius: 4,
              background: "var(--accent-weak)", color: "var(--accent-text)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <span>Rule: <span style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)" }}>{p.ruleId}</span></span>
              <button onClick={p.onClearRule} style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }} aria-label="Clear rule filter">×</button>
            </div>
          )}

          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <input type="checkbox" checked={p.groupByGoal} onChange={e => p.onGroupByGoalChange(e.target.checked)} />
            Group events by workflow goal
          </label>

          {activeCount > 0 && (
            <button onClick={() => { p.onClearAll(); setOpen(false) }}
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, alignSelf: "flex-end" }}>
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Export menu ──────────────────────────────────────────────────────────

export function ExportMenu({
  canExport, onExportCsv, onSocReport,
}: {
  canExport: boolean
  onExportCsv: () => void
  onSocReport: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false))
  if (!canExport) return null
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)}
              aria-haspopup="menu" aria-expanded={open}
              className="btn btn-ghost btn-sm"
              style={{ fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4 }}>
        Export
        <span aria-hidden style={{ marginLeft: 2, fontSize: 10 }}>▼</span>
      </button>
      {open && (
        <ul role="menu" style={{
          position: "absolute", top: "100%", right: 0, marginTop: 4,
          minWidth: 180, padding: 4, listStyle: "none",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
          zIndex: 20,
        }}>
          <li>
            <button role="menuitem" onClick={() => { onExportCsv(); setOpen(false) }}
                    style={menuItemStyle}>
              Export CSV
            </button>
          </li>
          <li>
            <button role="menuitem" onClick={() => { onSocReport(); setOpen(false) }}
                    style={menuItemStyle}>
              SOC 2 Report →
            </button>
          </li>
        </ul>
      )}
    </div>
  )
}

// ─── Columns menu (checkbox list) ─────────────────────────────────────────

export interface ColumnsMenuOption<TKey extends string = string> {
  key: TKey
  label: string
}

export function ColumnsMenu<TKey extends string = string>({
  allColumns, visible, onChange,
}: {
  allColumns: readonly ColumnsMenuOption<TKey>[]
  visible: readonly TKey[]
  onChange: (cols: TKey[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false))
  const visibleSet = useMemo(() => new Set<TKey>(visible), [visible])

  const toggle = useCallback((key: TKey) => {
    const next = visibleSet.has(key)
      // Preserve the canonical allColumns order when removing so re-adding
      // later drops the column back into the same slot.
      ? visible.filter(k => k !== key)
      : allColumns.map(c => c.key).filter(k => visibleSet.has(k) || k === key)
    // Never allow zero columns.
    if (next.length > 0) onChange([...next])
  }, [visible, visibleSet, onChange, allColumns])

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen(o => !o)}
              aria-haspopup="menu" aria-expanded={open}
              aria-label="Configure visible columns"
              className="btn btn-ghost btn-sm"
              style={{ fontSize: 12 }}
              title="Columns">
        ⚙
      </button>
      {open && (
        <ul role="menu" style={{
          position: "absolute", top: "100%", right: 0, marginTop: 4,
          minWidth: 180, padding: 6, listStyle: "none",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
          zIndex: 20,
        }}>
          <li style={{ padding: "4px 8px", fontSize: 10, fontWeight: 700,
                       textTransform: "uppercase", color: "var(--text-muted)",
                       letterSpacing: ".06em" }}>Columns</li>
          {allColumns.map(c => (
            <li key={c.key}>
              <label role="menuitemcheckbox" aria-checked={visibleSet.has(c.key)}
                     style={{ display: "flex", alignItems: "center", gap: 8,
                              padding: "6px 8px", fontSize: 12, cursor: "pointer",
                              borderRadius: 4 }}>
                <input
                  type="checkbox"
                  checked={visibleSet.has(c.key)}
                  onChange={() => toggle(c.key)}
                />
                {c.label}
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const menuItemStyle = {
  width: "100%", textAlign: "left" as const, padding: "6px 10px",
  fontSize: 12, borderRadius: 4, border: "none",
  background: "transparent", color: "var(--text-2)",
  cursor: "pointer",
}

// ─── Composed toolbar ─────────────────────────────────────────────────────
//
// One row, exactly the four primary controls plus a right-aligned Columns
// affordance. Every popover is closable via click-outside and Escape (native
// dialog/menu handling).

export interface GuardToolbarProps<TKey extends string = string> {
  streaming: boolean
  onStreamingToggle: () => void
  status: StatusValue
  onStatusChange: (v: StatusValue) => void
  filters: Omit<FiltersPopoverProps, "onClearAll">
  onClearAll: () => void
  canExport: boolean
  onExportCsv: () => void
  onSocReport: () => void
  allColumns: readonly ColumnsMenuOption<TKey>[]
  columns: readonly TKey[]
  onColumnsChange: (v: TKey[]) => void
}

export function GuardToolbar<TKey extends string = string>(p: GuardToolbarProps<TKey>) {
  return (
    <div style={{
      display: "flex", gap: 8, marginBottom: 12,
      alignItems: "center", flexWrap: "wrap",
    }}>
      <RealtimeBadge streaming={p.streaming} onToggle={p.onStreamingToggle} />
      <StatusDropdown active={p.status} onChange={p.onStatusChange} />
      <FiltersPopover {...p.filters} onClearAll={p.onClearAll} />
      <span style={{ marginLeft: "auto", display: "inline-flex", gap: 4, alignItems: "center" }}>
        <ExportMenu canExport={p.canExport} onExportCsv={p.onExportCsv} onSocReport={p.onSocReport} />
        <ColumnsMenu allColumns={p.allColumns} visible={p.columns} onChange={p.onColumnsChange} />
      </span>
    </div>
  )
}
