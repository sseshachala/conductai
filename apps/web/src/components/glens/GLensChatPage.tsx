"use client"
import { API } from "@/lib/api"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useLensEvent } from "@/hooks/useLensEvent"
import { useLensSessionStream, type LensSessionStream } from "@/hooks/useLensSessionStream"
import { GlensDashboard } from "@/components/glens/GlensDashboard"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"
import { GlensPageBubble } from "@/components/glens/GlensPageBubble"
import { GenericTableBubble } from "@/components/glens/GenericTableBubble"
import { BlocksBubble } from "@/components/glens/BlocksBubble"
import { FeedbackButtons } from "@/components/glens/FeedbackButtons"
import RunDetailPanel, { type RunMeta } from "@/components/runs/RunDetailPanel"
import { SlashDropdown, SlashForm, filterTools, type SlashTool } from "@/components/glens/SlashPicker"

// ─── Types ────────────────────────────────────────────────────────────────────

interface GLensSession {
  id: string
  title: string
  has_dashboard: boolean
  created_at: string
}

interface PolicyMapping {
  field: string
  column: string
  description: string
}

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; skill?: string; drilldown?: { path: string; filters?: Record<string, string> }; followups?: string[]; understoodAs?: string }
  | { role: "assistant"; kind: "streaming"; text: string }
  | { role: "assistant"; kind: "dashboard"; spec: GlensDashboardSpec; sessionId: string }
  | { role: "assistant"; kind: "loading"; label?: string }
  | { role: "assistant"; kind: "page"; answer: string; pageKind: string; pageData: Record<string, unknown>; warning?: string; skill: string }
  | { role: "assistant"; kind: "policy_confirm"; answer: string; action: string; draft: Record<string, unknown>; mapping: PolicyMapping[]; targetRuleId?: string; sessionId: string; skill: string; warning?: string }
  | { role: "assistant"; kind: "action_confirm"; toolName: string; approvalRequestId: string; summary: string; warnings?: string[]; expiresAt?: string }
  | { role: "assistant"; kind: "run"; runId: string; workflowName: string; initialStatus: string }
  | { role: "assistant"; kind: "blocks"; answer: string; blocks: unknown[]; warning?: string; skill: string; drilldown?: { path: string; filters?: Record<string, string> }; understoodAs?: string }
  | { role: "assistant"; kind: "table"; answer: string; columns?: unknown[]; rows: unknown[]; warning?: string; skill: string; drilldown?: { path: string; filters?: Record<string, string> }; understoodAs?: string }

const DEFAULT_SUGGESTIONS = [
  "Who was blocked today?",
  "Cost by AI tool this month",
  "How many events today?",
  "Show recent blocks",
]

const SKILL_LABELS: Record<string, string> = {
  report:       "Lens ·Report",
  analytics:    "Lens ·Analytics",
  extract:      "Lens ·Extract",
  memory:       "Lens ·Memory",
  session:      "Lens ·Session",
  rules:        "Lens ·Rules",
  guard_config: "Lens ·Guard Config",
  spend_config: "Lens ·Spend Config",
  discovery:    "Lens ·Discovery",
  compliance:   "Lens ·Compliance",
  governance:   "Lens ·Governance",
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

function bucketByDay(sessions: GLensSession[]): { label: string; items: GLensSession[] }[] {
  const startOfDay = (d: Date) => { const c = new Date(d); c.setHours(0, 0, 0, 0); return c.getTime() }
  const today = startOfDay(new Date())
  const buckets: Record<string, GLensSession[]> = { today: [], yesterday: [], prev7: [], older: [] }
  for (const s of sessions) {
    const diff = Math.floor((today - startOfDay(new Date(s.created_at))) / 86_400_000)
    if (diff <= 0) buckets.today.push(s)
    else if (diff === 1) buckets.yesterday.push(s)
    else if (diff <= 7) buckets.prev7.push(s)
    else buckets.older.push(s)
  }
  return [
    { label: "Today", items: buckets.today },
    { label: "Yesterday", items: buckets.yesterday },
    { label: "Previous 7 days", items: buckets.prev7 },
    { label: "Older", items: buckets.older },
  ].filter(b => b.items.length > 0)
}

function SessionRow({
  session, active, onSelect, onDelete, onRename,
}: {
  session: GLensSession
  active: boolean
  onSelect: () => void
  onDelete: () => void
  onRename: (title: string) => void
}) {
  const [hover, setHover] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  function commit() {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== session.title) onRename(trimmed)
    setEditing(false)
  }

  function cancel() {
    setDraft(session.title)
    setEditing(false)
  }

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ position: "relative", marginBottom: 2 }}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => {
            if (e.key === "Enter") { e.preventDefault(); commit() }
            if (e.key === "Escape") { e.preventDefault(); cancel() }
          }}
          style={{
            width: "100%",
            padding: "7px 10px",
            borderRadius: 6,
            border: "1px solid var(--accent)",
            background: "var(--surface)",
            color: "var(--text)",
            fontSize: 13,
            outline: "none",
            fontFamily: "inherit",
          }}
        />
      ) : (
        <button
          onClick={onSelect}
          onDoubleClick={() => setEditing(true)}
          style={{
            width: "100%",
            textAlign: "left",
            padding: "7px 52px 7px 10px",
            borderRadius: 6,
            border: "none",
            background: active ? "var(--accent-weak)" : hover ? "var(--surface-3, rgba(0,0,0,0.04))" : "transparent",
            cursor: "pointer",
            fontSize: 13,
            color: active ? "var(--accent-text)" : "var(--text)",
            fontWeight: active ? 600 : 400,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {session.title}
        </button>
      )}
      {!editing && (
        <div style={{
          position: "absolute",
          right: 4,
          top: "50%",
          transform: "translateY(-50%)",
          display: "flex",
          gap: 2,
          opacity: hover ? 1 : 0,
          transition: "opacity 120ms",
        }}>
          <button
            onClick={() => { setDraft(session.title); setEditing(true) }}
            aria-label="Rename conversation"
            title="Rename"
            style={{
              padding: "3px 5px",
              borderRadius: 4,
              border: "none",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
              lineHeight: 0,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </button>
          <button
            onClick={onDelete}
            aria-label="Delete conversation"
            title="Delete"
            style={{
              padding: "2px 6px",
              borderRadius: 4,
              border: "none",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: 14,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
      )}
    </div>
  )
}

function Sidebar({
  sessions,
  activeId,
  onSelect,
  onDelete,
  onRename,
  onNew,
  collapsed,
  onToggle,
}: {
  sessions: GLensSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onNew: () => void
  collapsed: boolean
  onToggle: () => void
}) {
  const grouped = bucketByDay(sessions)

  if (collapsed) {
    return (
      <div style={{
        width: 52,
        flexShrink: 0,
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        background: "var(--surface-2)",
        height: "100%",
        padding: "12px 0",
        gap: 8,
      }}>
        <button
          onClick={onToggle}
          aria-label="Expand sidebar"
          title="Expand sidebar"
          style={{
            width: 32, height: 32, borderRadius: 6, border: "none",
            background: "transparent", color: "var(--text-muted)",
            cursor: "pointer", fontSize: 16, lineHeight: 1,
          }}
        >
          ›
        </button>
        <button
          onClick={onNew}
          aria-label="New chat"
          title="New chat"
          style={{
            width: 32, height: 32, borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--surface)", color: "var(--text)",
            cursor: "pointer", fontSize: 16, lineHeight: 1,
          }}
        >
          +
        </button>
      </div>
    )
  }

  return (
    <div style={{
      width: 260,
      flexShrink: 0,
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      background: "var(--surface-2)",
      height: "100%",
    }}>
      <div style={{ padding: "14px 12px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent-text)", textTransform: "uppercase", letterSpacing: ".08em" }}>Lens</div>
          <button
            onClick={onToggle}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            style={{
              padding: "4px 6px", borderRadius: 6, border: "none",
              background: "transparent", cursor: "pointer",
              color: "var(--text-muted)", fontSize: 14, lineHeight: 1,
            }}
          >
            ‹
          </button>
        </div>
        <button
          onClick={onNew}
          style={{
            width: "100%",
            fontSize: 13,
            padding: "9px 12px",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text)",
            cursor: "pointer",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: 8,
            justifyContent: "flex-start",
          }}
        >
          <span style={{ fontSize: 15, lineHeight: 1 }}>+</span>
          <span>New chat</span>
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "10px 8px" }}>
        {sessions.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", padding: "24px 8px" }}>
            No conversations yet
          </div>
        )}
        {grouped.map(bucket => (
          <div key={bucket.label} style={{ marginBottom: 14 }}>
            <div style={{
              fontSize: 10,
              fontWeight: 700,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: ".08em",
              padding: "4px 8px 6px",
            }}>
              {bucket.label}
            </div>
            {bucket.items.map(s => (
              <SessionRow
                key={s.id}
                session={s}
                active={s.id === activeId}
                onSelect={() => onSelect(s.id)}
                onDelete={() => onDelete(s.id)}
                onRename={(title) => onRename(s.id, title)}
              />
            ))}
          </div>
        ))}
      </div>

      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span>AI governance analytics</span>
        <a href="/theguard/team-memory" style={{ fontSize: 11, color: "var(--accent-text)", textDecoration: "none", fontWeight: 500 }}>Team Memory →</a>
      </div>
    </div>
  )
}

// ─── Message bubbles ──────────────────────────────────────────────────────────

function UserBubble({ text, onEdit }: { text: string; onEdit?: (newText: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(text)
  const taRef = useRef<HTMLTextAreaElement>(null)

  function startEdit() { setDraft(text); setEditing(true); setTimeout(() => taRef.current?.focus(), 0) }
  function cancel() { setEditing(false) }
  function submit() { if (draft.trim() && draft.trim() !== text) onEdit?.(draft.trim()); setEditing(false) }

  return (
    <div
      style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16, position: "relative" }}
      onMouseEnter={e => { if (!editing && onEdit) (e.currentTarget.querySelector(".edit-btn") as HTMLElement)?.style.setProperty("opacity", "1") }}
      onMouseLeave={e => { (e.currentTarget.querySelector(".edit-btn") as HTMLElement)?.style.setProperty("opacity", "0") }}
    >
      {onEdit && !editing && (
        <button
          className="edit-btn"
          onClick={startEdit}
          style={{
            opacity: 0, transition: "opacity .15s", alignSelf: "center", marginRight: 8,
            background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)",
            fontSize: 13, padding: "2px 6px", borderRadius: 4,
          }}
          title="Edit question"
        >✎</button>
      )}
      {editing ? (
        <div style={{ maxWidth: "65%", display: "flex", flexDirection: "column", gap: 6 }}>
          <textarea
            ref={taRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } if (e.key === "Escape") cancel() }}
            rows={3}
            style={{
              width: "100%", fontSize: 14, padding: "10px 14px", borderRadius: 10,
              border: "1px solid var(--accent)", outline: "none", resize: "none",
              background: "var(--surface-2)", color: "var(--text)", lineHeight: 1.5,
            }}
          />
          <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
            <button onClick={cancel} style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", cursor: "pointer", color: "var(--text-2)" }}>Cancel</button>
            <button onClick={submit} style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "none", background: "var(--accent)", color: "#fff", cursor: "pointer" }}>Send</button>
          </div>
        </div>
      ) : (
        <div style={{
          maxWidth: "65%",
          background: "var(--accent)",
          color: "#fff",
          borderRadius: "14px 14px 4px 14px",
          padding: "10px 16px",
          fontSize: 14,
          lineHeight: 1.5,
        }}>
          {text}
        </div>
      )}
    </div>
  )
}

function renderInline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/).map((p, j) => {
    if (p.startsWith("**")) return <strong key={j}>{p.slice(2, -2)}</strong>
    const link = p.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link) return <a key={j} href={link[2]} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent, #6366f1)", textDecoration: "underline" }}>{link[1]}</a>
    return p
  })
}

function isTableSeparator(line: string): boolean {
  // e.g. "| --- | --- |" or "|:---|---:|"
  return /^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$/.test(line)
}

function parseRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "")
  return trimmed.split("|").map(c => c.trim())
}

function renderTable(header: string[], rows: string[][], key: number): React.ReactNode {
  return (
    <div key={key} style={{ overflowX: "auto", margin: "8px 0" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            {header.map((h, i) => (
              <th key={i} style={{ textAlign: "left", padding: "6px 10px", color: "var(--text-muted)", fontWeight: 600, fontSize: 11.5, textTransform: "uppercase", letterSpacing: ".04em" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ borderBottom: ri < rows.length - 1 ? "1px solid var(--border)" : "none" }}>
              {row.map((cell, ci) => (
                <td key={ci} style={{ padding: "6px 10px", color: "var(--text)", verticalAlign: "top" }}>{renderInline(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function renderMd(text: string): React.ReactNode[] {
  const lines = text.split("\n")
  const out: React.ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    // Detect markdown table: current line starts with | AND next line is separator
    if (line.trim().startsWith("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const header = parseRow(line)
      const rows: string[][] = []
      let j = i + 2
      while (j < lines.length && lines[j].trim().startsWith("|") && !isTableSeparator(lines[j])) {
        rows.push(parseRow(lines[j]))
        j++
      }
      out.push(renderTable(header, rows, i))
      i = j
      continue
    }
    const bullet = line.match(/^[*-]\s+(.+)/)
    const content = bullet ? bullet[1] : line
    const parts = renderInline(content)
    if (bullet) out.push(<div key={i} style={{ paddingLeft: 12, position: "relative" }}><span style={{ position: "absolute", left: 0 }}>•</span>{parts}</div>)
    else out.push(<div key={i} style={{ minHeight: line ? undefined : "0.6em" }}>{parts}</div>)
    i++
  }
  return out
}

function AnswerBubble({ text, skill, drilldown, followups, onFollowup, understoodAs }: { text: string; skill?: string; drilldown?: { path: string }; followups?: string[]; onFollowup?: (q: string) => void; understoodAs?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
      <div style={{ maxWidth: "75%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          {skill && (
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>
              {SKILL_LABELS[skill] ?? skill}
            </div>
          )}
          {understoodAs && (
            <div style={{ fontSize: 10, color: "var(--text-muted)", fontStyle: "italic" }}>
              · {understoodAs}
            </div>
          )}
        </div>
        <div style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: "4px 14px 14px 14px",
          padding: "10px 16px",
          fontSize: 14,
          color: "var(--text)",
          lineHeight: 1.6,
        }}>
          {renderMd(text)}
          {drilldown && (
            <div style={{ marginTop: 8, textAlign: "right" }}>
              <a href={drilldown.path} style={{ fontSize: 12, color: "var(--accent, #6366f1)", textDecoration: "none", fontWeight: 500 }}>
                View full &rarr;
              </a>
            </div>
          )}
        </div>
        {followups && followups.length > 0 && onFollowup && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {followups.map(q => (
              <button
                key={q}
                onClick={() => onFollowup(q)}
                style={{
                  fontSize: 12, padding: "5px 12px", borderRadius: 16,
                  border: "1px solid var(--border)", background: "var(--surface-2)",
                  color: "var(--text-2)", cursor: "pointer",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function LoadingBubble({ label }: { label?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
      <div style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "12px 16px",
        fontSize: 14,
        color: "var(--text-muted)",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }} aria-label="Lens is thinking" role="status">
        <span style={{ display: "inline-flex", alignItems: "flex-end", gap: 4, height: 12 }}>
          <span className="conduct-typing-dot" />
          <span className="conduct-typing-dot" />
          <span className="conduct-typing-dot" />
        </span>
        {label && <span style={{ fontSize: 12, opacity: 0.8 }}>{label}</span>}
      </div>
    </div>
  )
}

// ── Copy button (shared) ──────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // Older browsers / insecure contexts — fall back to a hidden textarea.
      const ta = document.createElement("textarea")
      ta.value = text
      ta.style.position = "fixed"
      ta.style.opacity = "0"
      document.body.appendChild(ta)
      ta.select()
      try { document.execCommand("copy") } catch {}
      document.body.removeChild(ta)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? "Copied" : "Copy response"}
      title={copied ? "Copied" : "Copy"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 26,
        height: 26,
        color: copied ? "var(--ok, #10b981)" : "var(--text-muted)",
        background: "transparent",
        border: "1px solid transparent",
        borderRadius: 6,
        cursor: "pointer",
        transition: "background 0.12s, color 0.12s",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-3, rgba(0,0,0,0.04))")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      {copied ? (
        <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  )
}

// ── Message footer (copy + thumbs) ────────────────────────────────────────────
// Rendered after every assistant bubble (except loading + in-flight streaming).
// Universal: past-session restore, live answers, structured bubbles all get
// the same affordance in the same place. Feedback requires a sessionId; copy
// only requires text.

function MessageFooter({ text, sessionId, messageId }: { text?: string; sessionId: string | null; messageId: string }) {
  if (!text && !sessionId) return null
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "flex-start",
        alignItems: "center",
        gap: 0,
        marginTop: 4,
        marginBottom: 12,
        marginLeft: -4,
      }}
    >
      {text ? <CopyButton text={text} /> : null}
      {sessionId ? <FeedbackButtons sessionId={sessionId} messageId={messageId} /> : null}
    </div>
  )
}

function DashboardBubble({
  spec,
  sessionId,
  authFetch,
}: {
  spec: GlensDashboardSpec
  sessionId: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
}) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{
        width: "100%",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "16px",
      }}>
        <GlensDashboard spec={spec} sessionId={sessionId} authFetch={authFetch} />
      </div>
    </div>
  )
}

const SKILL_APPLY_URL: Record<string, string> = {
  rules:        "/glens/policy/apply",
  guard_config: "/glens/guard_config/apply",
  spend_config: "/glens/spend_config/apply",
}

function _applyBody(skill: string, action: string, draft: Record<string, unknown>, targetRuleId?: string) {
  if (skill === "rules") return { action, draft, target_rule_id: targetRuleId }
  if (skill === "guard_config") return { draft }
  if (skill === "spend_config") return draft   // SpendConfigApplyRequest fields are top-level
  return { action, draft }
}

function PolicyConfirmBubble({
  answer,
  action,
  skill,
  draft,
  mapping,
  targetRuleId,
  sessionId,
  authFetch,
  onResult,
  warning,
}: {
  answer: string
  action: string
  skill: string
  draft: Record<string, unknown>
  mapping: PolicyMapping[]
  targetRuleId?: string
  sessionId: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onResult: (text: string) => void
  warning?: string
}) {
  const [status, setStatus] = useState<"pending" | "loading" | "done">("pending")

  async function confirm() {
    setStatus("loading")
    const url = `${API}${SKILL_APPLY_URL[skill] ?? "/glens/policy/apply"}`
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_applyBody(skill, action, draft, targetRuleId)),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        onResult(`Failed to apply: ${err.detail ?? res.status}`)
      } else {
        const data = await res.json()
        const label = data.rule_id ? `Rule "${data.rule_id}"` : data.scope ? `Budget (${data.scope})` : "Guard config"
        onResult(`${label} ${data.action} successfully.`)
      }
    } catch {
      onResult("Network error. Please try again.")
    }
    setStatus("done")
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Policy</div>
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 16, lineHeight: 1.5 }}>{answer}</div>

        {/* Field → Column mapping table */}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 16 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Field</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Value</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Column</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Description</th>
            </tr>
          </thead>
          <tbody>
            {mapping.map(m => (
              <tr key={m.field} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--accent-text)" }}>{m.field}</td>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text)" }}>{String(draft[m.field] ?? "—")}</td>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text-2)", fontSize: 11 }}>{m.column}</td>
                <td style={{ padding: "6px 8px", color: "var(--text-muted)" }}>{m.description}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {warning && (
          <div style={{ fontSize: 12, color: "var(--warn, #f59e0b)", marginBottom: 12, padding: "8px 12px", background: "var(--warn-bg, #fef3c7)", borderRadius: 6 }}>
            {warning}
          </div>
        )}

        {status === "pending" && (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button
              onClick={confirm}
              style={{
                padding: "8px 20px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer",
                background: action === "delete" ? "var(--err, #ef4444)" : "var(--accent)",
                color: "#fff",
              }}
            >
              {action === "delete" ? "Delete" : "Confirm"}
            </button>
            <button
              onClick={() => onResult(`Policy ${action} cancelled.`)}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer" }}
            >
              Cancel
            </button>
            {action === "delete" && (
              <span style={{ fontSize: 11, color: "var(--err, #ef4444)" }}>This cannot be undone.</span>
            )}
          </div>
        )}
        {status === "loading" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Applying…</div>}
      </div>
    </div>
  )
}

function ActionConfirmBubble({
  toolName,
  approvalRequestId,
  summary,
  warnings,
  expiresAt,
  authFetch,
  stream,
  onResult,
  onRunStarted,
  onRetry,
}: {
  toolName: string
  approvalRequestId: string
  summary: string
  warnings?: string[]
  expiresAt?: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  stream: LensSessionStream | null
  onResult: (text: string) => void
  onRunStarted?: (runId: string, workflowName: string, initialStatus: string) => void
  // Regression 4 fix — invoked when the user retries a failed run from the
  // decided-approved bubble. Parent spawns a new RunBubble for the new run id.
  onRetry?: (newRunId: string, workflowName: string) => void
}) {
  const [status, setStatus] = useState<"pending" | "loading" | "done">("pending")
  const [idCopied, setIdCopied] = useState(false)
  // Server-side status snapshot fetched on mount so a restored bubble for
  // an already-decided action renders in the resolved state instead of
  // showing active Confirm/Cancel buttons for something that already ran.
  const [serverStatus, setServerStatus] = useState<"pending" | "approved" | "rejected" | "timed_out" | null>(null)
  const [serverResult, setServerResult] = useState<Record<string, unknown> | null>(null)
  // #1511 — expand toggle + fetched workflow_id so we can embed <RunDetailPanel>
  // when the action resolved into a run. localStorage keeps expand state across
  // refresh, keyed by approvalRequestId (per-bubble).
  const [panelOpen, setPanelOpen] = useState(() => {
    try { return typeof window !== "undefined" && window.localStorage.getItem(`lens:actionPanelOpen:${approvalRequestId}`) === "1" }
    catch { return false }
  })
  const [runData, setRunData] = useState<RunMeta | null>(null)
  // Dedupe: whichever source (POST response or SSE event) reports resolution
  // first wins. Race is fine because the payload shape is identical.
  const handledRef = useRef(false)
  // #1480 Gap 4 — action controls for the run this bubble kicked off, shown
  // in the decided-approved state so the user doesn't have to hunt for the
  // sibling RunBubble to cancel or retry.
  const [runBusy, setRunBusy] = useState(false)
  const [runActionErr, setRunActionErr] = useState<string | null>(null)

  // #1511 — mirror panelOpen to localStorage so refresh restores expand state.
  useEffect(() => {
    try { window.localStorage.setItem(`lens:actionPanelOpen:${approvalRequestId}`, panelOpen ? "1" : "0") }
    catch { /* best-effort */ }
  }, [panelOpen, approvalRequestId])

  // #1511 — once we know the run_id (via server snapshot or dispatch), fetch
  // /runs/{id} to grab workflow_id + a full run seed. RunDetailPanel needs
  // workflowId, and passing runData as initialRun skips its own initial fetch.
  const resolvedRunId = (serverResult?.run_id as string | undefined) ?? null
  useEffect(() => {
    if (!resolvedRunId) return
    let cancelled = false
    authFetch(`${API}/runs/${resolvedRunId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (!cancelled && data) setRunData(data as RunMeta) })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedRunId])

  // Regression 3 fix — subscribe to run events for this bubble's run so
  // Cancel/Retry/Approve/Reject buttons reflect current run status instead of
  // the stale snapshot from mount. Refetches runData on any run.* event.
  useLensEvent(stream, "run", resolvedRunId ?? "", (_evt) => {
    if (!resolvedRunId) return
    authFetch(`${API}/runs/${resolvedRunId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) setRunData(data as RunMeta) })
      .catch(() => {})
  })

  // #1511 — auto-open the panel when a decided-approved bubble with a run
  // becomes visible, so the demo flow drops straight into the run detail.
  useEffect(() => {
    if (serverStatus === "approved" && resolvedRunId) setPanelOpen(true)
  }, [serverStatus, resolvedRunId])

  // On mount, fetch the current status from the server. Skip when a
  // decision has already been dispatched in this render (handledRef set).
  useEffect(() => {
    let cancelled = false
    authFetch(`${API}/glens/actions/${approvalRequestId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data?.status) return
        setServerStatus(data.status as typeof serverStatus)
        if (data.result) setServerResult(data.result as Record<string, unknown>)
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approvalRequestId])

  const finishText = (text: string) => {
    if (handledRef.current) return
    handledRef.current = true
    setStatus("done")
    onResult(text)
  }

  const finishRun = (runId: string, workflowName: string, initialStatus: string) => {
    if (handledRef.current) return
    handledRef.current = true
    setStatus("done")
    if (onRunStarted) {
      onRunStarted(runId, workflowName, initialStatus)
    } else {
      // Flag OFF or no run-bubble callback wired — fall back to text link.
      onResult(`Run started for **${workflowName}**. [View run →](/runs/${runId})`)
    }
  }

  const dispatchConfirmed = (payload: Record<string, unknown> | undefined, fallbackTool: string) => {
    const result = (payload?.result ?? {}) as Record<string, unknown>
    const label = (payload?.tool_name as string | undefined) ?? fallbackTool
    const runId = result.run_id as string | undefined
    if (runId) {
      const wfName = (result.workflow_name as string | undefined) ?? label
      // Initial status from the run row when we have it; "pending" otherwise
      // (the worker will emit run.status_changed within seconds).
      const initialStatus = (result.status as string | undefined) ?? "pending"
      finishRun(runId, wfName, initialStatus)
    } else {
      finishText(`${label} executed successfully.`)
    }
  }

  // #1480 PR 4 — react to action.confirmed / action.cancelled events on the
  // session stream. Fires for cross-tab confirms, Slack-side approvals, or
  // any decide path that touches this row. `stream` is null when the SSE
  // feature flag is off — subscription is a silent no-op then.
  useLensEvent(stream, "approval", approvalRequestId, (evt) => {
    if (evt.type === "action.confirmed") {
      dispatchConfirmed(evt.payload, toolName)
    } else if (evt.type === "action.cancelled") {
      finishText("Action cancelled.")
    }
  })

  async function post(action: "confirm" | "cancel") {
    setStatus("loading")
    try {
      const res = await authFetch(`${API}/glens/actions/${approvalRequestId}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        finishText(`Failed to ${action}: ${err.detail ?? res.status}`)
        return
      }
      // When the SSE stream is live, it will call `finish*` with the
      // event-derived message; the POST body is redundant then. When SSE
      // is off (flag disabled) or subscribed too late, fall through and
      // use the response body directly. `handledRef` deduplicates either way.
      const data = await res.json()
      if (action === "confirm") {
        dispatchConfirmed(data as Record<string, unknown>, toolName)
      } else {
        finishText("Action cancelled.")
      }
    } catch {
      finishText("Network error. Please try again.")
    }
  }

  const isMutation = toolName !== "decide_approval"  // heuristic — decide is itself an approve/reject

  async function _postRunAction(url: string, body?: unknown, onOk?: (data: Record<string, unknown>) => void) {
    if (runBusy || !runData?.workflow_id || !resolvedRunId) return
    setRunBusy(true); setRunActionErr(null)
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setRunActionErr((err as { detail?: string }).detail ?? `Request failed (${res.status})`)
        return
      }
      const data = await res.json().catch(() => ({}))
      onOk?.(data as Record<string, unknown>)
    } catch {
      setRunActionErr("Network error")
    } finally {
      setRunBusy(false)
    }
  }

  const runStatus = runData?.status ?? null
  const runCancel = () => _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs/${resolvedRunId}/cancel`)
  const runDecide = (decision: "approved" | "rejected") =>
    _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs/${resolvedRunId}/approve`, { decision })
  const runRetry = () => {
    // #1480 Gap 3 parity — reuse original inputs, strip block outputs + system keys.
    const runStateRec = (runData?.state ?? {}) as Record<string, unknown>
    const initial_state: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(runStateRec)) {
      if (k.startsWith("__")) continue
      // Same heuristic as RunBubble's retry: keep single-underscore meta keys
      // (_trigger) and scalars; drop object-typed non-underscore keys (likely
      // block outputs). Server-side validate_run_start_inputs is the backstop.
      if (typeof v === "object" && v !== null && !k.startsWith("_")) continue
      initial_state[k] = v
    }
    _postRunAction(`${API}/workflows/${runData!.workflow_id}/runs`, { initial_state }, (data) => {
      // Regression 4 fix — spawn a new RunBubble instead of leaving the new
      // run orphaned. Without this the Retry button stays visible and the
      // user might spam-click it, spawning a run per click.
      const newId = data.id as string | undefined
      if (newId && onRetry) onRetry(newId, (runData?.workflow_id as string | undefined) ?? "workflow")
    })
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Action · {toolName}</div>
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 10, lineHeight: 1.5 }}>{summary}</div>

        {/* Approval request identifier (#1468) — visible so the user knows which pending
             action a natural-language "yes" is confirming when multiple are outstanding. */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, fontSize: 11, color: "var(--text-muted)" }}>
          <span style={{ textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>ID</span>
          <code style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", color: "var(--text-2)", fontSize: 11 }}>
            {approvalRequestId.slice(0, 8)}…{approvalRequestId.slice(-4)}
          </code>
          <button
            type="button"
            title={idCopied ? "Copied" : "Copy full ID"}
            onClick={() => {
              navigator.clipboard.writeText(approvalRequestId).then(
                () => { setIdCopied(true); setTimeout(() => setIdCopied(false), 1200) },
                () => {},
              )
            }}
            style={{
              padding: "2px 6px", borderRadius: 4, border: "none",
              background: idCopied ? "var(--accent-weak, rgba(59,130,246,0.12))" : "transparent",
              color: idCopied ? "var(--accent-text, #2563eb)" : "var(--text-muted)",
              cursor: "pointer", fontSize: 11, lineHeight: 1,
            }}
          >
            {idCopied ? "✓" : "⧉"}
          </button>
        </div>

        {warnings && warnings.length > 0 && (
          <div style={{ fontSize: 12, color: "var(--warn, #f59e0b)", marginBottom: 12, padding: "8px 12px", background: "var(--warn-bg, #fef3c7)", borderRadius: 6 }}>
            {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
          </div>
        )}

        {(serverStatus === "approved" || serverStatus === "rejected" || serverStatus === "timed_out") && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
            <span style={{
              fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 999,
              background:
                serverStatus === "approved" ? "var(--ok-bg, #dcfce7)" :
                serverStatus === "rejected" ? "var(--err-bg, #fee2e2)" :
                "var(--surface-3, #f3f4f6)",
              color:
                serverStatus === "approved" ? "var(--ok-text, #166534)" :
                serverStatus === "rejected" ? "var(--err-text, #991b1b)" :
                "var(--text-muted)",
              textTransform: "capitalize",
            }}>{serverStatus === "timed_out" ? "Expired" : serverStatus}</span>
            {serverStatus === "approved" && (serverResult?.run_id as string | undefined) && (
              <a href={`/runs/${serverResult!.run_id}`} style={{ color: "var(--accent)", textDecoration: "none" }}>
                View run →
              </a>
            )}
          </div>
        )}
        {serverStatus === "approved" && runData?.workflow_id && resolvedRunId &&
         (runStatus === "pending" || runStatus === "running" || runStatus === "paused" || runStatus === "failed") && (
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            {(runStatus === "pending" || runStatus === "running") && (
              <button onClick={runCancel} disabled={runBusy}
                style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                         background: "transparent", color: "var(--text-2)",
                         fontSize: 12, cursor: runBusy ? "wait" : "pointer" }}>
                Cancel run
              </button>
            )}
            {runStatus === "paused" && (
              <>
                <button onClick={() => runDecide("approved")} disabled={runBusy}
                  style={{ padding: "6px 14px", borderRadius: 6, border: "none",
                           background: "var(--accent)", color: "#fff",
                           fontSize: 12, fontWeight: 600, cursor: runBusy ? "wait" : "pointer" }}>
                  Approve run
                </button>
                <button onClick={() => runDecide("rejected")} disabled={runBusy}
                  style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                           background: "transparent", color: "var(--text-2)",
                           fontSize: 12, cursor: runBusy ? "wait" : "pointer" }}>
                  Reject run
                </button>
              </>
            )}
            {runStatus === "failed" && (
              <button onClick={runRetry} disabled={runBusy}
                style={{ padding: "6px 14px", borderRadius: 6, border: "none",
                         background: "var(--accent)", color: "#fff",
                         fontSize: 12, fontWeight: 600, cursor: runBusy ? "wait" : "pointer" }}>
                Retry run
              </button>
            )}
          </div>
        )}
        {runActionErr && (
          <div style={{ fontSize: 12, color: "var(--err-text, #991b1b)", background: "var(--err-bg, #fee2e2)",
                        padding: "6px 10px", borderRadius: 6, marginTop: 8 }}>
            {runActionErr}
          </div>
        )}
        {panelOpen && serverStatus === "approved" && runData?.workflow_id && resolvedRunId && (
          <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
            <RunDetailPanel
              workflowId={runData.workflow_id as string}
              runId={resolvedRunId}
              embedded
              initialRun={runData}
            />
          </div>
        )}
        {status === "pending" && (serverStatus === null || serverStatus === "pending") && (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button
              onClick={() => post("confirm")}
              style={{
                padding: "8px 20px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer",
                background: "var(--accent)", color: "#fff",
              }}
            >
              Confirm
            </button>
            <button
              onClick={() => post("cancel")}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer" }}
            >
              Cancel
            </button>
            {expiresAt && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Expires {new Date(expiresAt).toLocaleTimeString()}
              </span>
            )}
          </div>
        )}
        {status === "loading" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Working…</div>}
      </div>
    </div>
  )
}

// ─── Run bubble ──────────────────────────────────────────────────────────────

function formatElapsed(startMs: number, endMs: number): string {
  const secs = Math.max(0, Math.round((endMs - startMs) / 1000))
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const rem = secs % 60
  if (mins < 60) return rem ? `${mins}m ${rem}s` : `${mins}m`
  const hrs = Math.floor(mins / 60)
  const rmin = mins % 60
  return rmin ? `${hrs}h ${rmin}m` : `${hrs}h`
}

type RunBlockState = {
  id: string
  status: "pending" | "running" | "succeeded" | "failed"
  label?: string
  error?: string
}
// #1480 PR 5 — live run status inline in chat. Subscribes to run.status_changed
// events on the session stream and updates its pill in place. Always renders
// the "View run →" link so the user can jump to the run detail page.

function RunBubble({
  runId,
  workflowName,
  initialStatus,
  stream,
  authFetch,
  onRetry,
}: {
  runId: string
  workflowName: string
  initialStatus: string
  stream: LensSessionStream | null
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onRetry?: (newRunId: string, workflowName: string) => void
}) {
  const [status, setStatus] = useState(initialStatus)
  const [error, setError] = useState<string | null>(null)
  // Per-block timeline (#1480 PR 7). Order is insertion order (Map preserves
  // it), which matches the DAG execution order the worker publishes in.
  const [blocks, setBlocks] = useState<Map<string, RunBlockState>>(new Map())
  // Cached run.state from /runs/{id} — populated on mount, used to render
  // block outputs inline (#1480 PR 9). Refetch on demand if a block the
  // user expands isn't in the cache yet.
  const [runState, setRunState] = useState<Record<string, unknown> | null>(null)
  const [outcome, setOutcome] = useState<{ type?: string; artifact_url?: string } | null>(null)
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionErr, setActionErr] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [completedAt, setCompletedAt] = useState<number | null>(null)
  const [now, setNow] = useState<number>(() => Date.now())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // #1506 — top-level expand toggle for the embedded RunDetailPanel
  const [panelOpen, setPanelOpen] = useState(() => {
    // #1508 follow-up — persist expand state across refresh, per runId.
    // localStorage (not sessionStorage) so re-opening the tab keeps context.
    try { return typeof window !== "undefined" && window.localStorage.getItem(`lens:panelOpen:${runId}`) === "1" }
    catch { return false }
  })
  // #1508 follow-up — cache the /runs/{id} response so the embedded
  // RunDetailPanel can skip its own initial fetch (initialRun prop).
  const [runData, setRunData] = useState<RunMeta | null>(null)
  // If an SSE update lands before the bootstrap fetch resolves, the fetch
  // result is stale — don't overwrite the fresher event.
  const gotUpdate = useRef(false)

  // Mount-race fix: the worker publishes run.status_changed as soon as it
  // picks up the run — often BEFORE this component mounts and subscribes.
  // On short runs both "running" and terminal events can fire before the
  // subscription attaches, leaving the pill stuck at "pending" forever.
  // Fetch current status once on mount so the pill catches up regardless
  // of when SSE events landed.
  useEffect(() => {
    let cancelled = false
    authFetch(`${API}/runs/${runId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled) return
        if (data) setRunData(data as RunMeta)
        if (data?.state) {
          const st = data.state as Record<string, unknown>
          setRunState(st)
          // #1480 PR 12 — seed the block timeline from persisted run.state
          // so a restored RunBubble shows completed blocks immediately
          // instead of waiting for new SSE events (which never come for
          // an already-completed run).
          if (gotUpdate.current === false) {
            const seeded = new Map<string, RunBlockState>()
            for (const [key, val] of Object.entries(st)) {
              // Regression 2 fix: skip system keys (__foo) AND meta keys
              // (_trigger, _workspace, etc.). Single-underscore prefix means
              // "run metadata, not a block output" by convention. Without
              // this, _trigger got treated as a block on restore and the
              // retry filter (#1547) then dropped it, losing webhook context.
              if (key.startsWith("_")) continue
              const failed = val && typeof val === "object" && "error" in (val as Record<string, unknown>)
              seeded.set(key, {
                id: key,
                status: failed ? "failed" : "succeeded",
                error: failed ? String((val as Record<string, unknown>).error) : undefined,
              })
            }
            if (seeded.size > 0) setBlocks(prev => prev.size === 0 ? seeded : prev)
          }
        }
        if (data?.workflow_id) setWorkflowId(data.workflow_id as string)
        if (data?.outcome) setOutcome(data.outcome as { type?: string; artifact_url?: string })
        if (data?.started_at) setStartedAt(new Date(data.started_at as string).getTime())
        if (data?.completed_at) setCompletedAt(new Date(data.completed_at as string).getTime())
        if (data?.status && !gotUpdate.current) setStatus(data.status)
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // Refetch state + outcome + timing when a block completes / status changes.
  // #1480 Gap 1 — deps include terminalCount so we refetch on EVERY block
  // completion, not just the first. That refreshes tokens/cost mid-run so the
  // embedded RunDetailPanel StatRow updates live (kills #1543 stopgap).
  const terminalCount = Array.from(blocks.values()).filter(b => b.status === "succeeded" || b.status === "failed").length
  useEffect(() => {
    if (terminalCount === 0 && status !== "succeeded" && status !== "failed") return
    let cancelled = false
    authFetch(`${API}/runs/${runId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data) return
        setRunData(data as RunMeta)
        if (data.state) setRunState(data.state as Record<string, unknown>)
        if (data.outcome) setOutcome(data.outcome as { type?: string; artifact_url?: string })
        if (data.completed_at) setCompletedAt(new Date(data.completed_at as string).getTime())
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, terminalCount])

  // Client-side elapsed clock — tick every second while the run is active.
  useEffect(() => {
    if (status !== "running" && status !== "pending") return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [status])

  // #1506 — auto-open the full detail panel when the run pauses for approval,
  // so the Approvals tab is one click away without hunting for a chevron.
  useEffect(() => {
    if (status === "paused") setPanelOpen(true)
  }, [status])

  // #1508 follow-up — mirror panelOpen to localStorage so refresh restores it.
  useEffect(() => {
    try { window.localStorage.setItem(`lens:panelOpen:${runId}`, panelOpen ? "1" : "0") }
    catch { /* private-mode / quota — best-effort */ }
  }, [panelOpen, runId])

  useLensEvent(stream, "run", runId, (evt) => {
    gotUpdate.current = true
    if (evt.type === "run.status_changed") {
      const nextStatus = (evt.payload?.status as string | undefined) ?? status
      setStatus(nextStatus)
      const evtErr = evt.payload?.error as string | undefined
      if (evtErr) setError(evtErr)
      return
    }
    // Block-level events (#1480 PR 7 timeline)
    const blockId = evt.payload?.block_id as string | undefined
    if (!blockId) return
    const label = evt.payload?.label as string | undefined
    const errMsg = evt.payload?.error as string | undefined
    setBlocks(prev => {
      const next = new Map(prev)
      const cur = next.get(blockId) ?? { id: blockId, status: "pending" }
      if (evt.type === "run.block_started") {
        next.set(blockId, { ...cur, status: "running", label: label ?? cur.label })
      } else if (evt.type === "run.block_completed") {
        next.set(blockId, { ...cur, status: "succeeded" })
      } else if (evt.type === "run.block_failed") {
        next.set(blockId, { ...cur, status: "failed", error: errMsg ?? cur.error })
      }
      return next
    })
  })

  async function _postAction(url: string, body?: unknown, onOk?: (data: Record<string, unknown>) => void) {
    if (busy || !workflowId) return
    setBusy(true); setActionErr(null)
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setActionErr((err as { detail?: string }).detail ?? `Request failed (${res.status})`)
        setBusy(false)
        return
      }
      const data = await res.json().catch(() => ({}))
      onOk?.(data as Record<string, unknown>)
    } catch {
      setActionErr("Network error")
    } finally {
      setBusy(false)
    }
  }

  const cancelRun = () => _postAction(`${API}/workflows/${workflowId}/runs/${runId}/cancel`)
  const decideRun = (decision: "approved" | "rejected") =>
    _postAction(`${API}/workflows/${workflowId}/runs/${runId}/approve`, { decision })
  const retryRun = () => {
    // #1480 Gap 3 — reuse the original run's inputs. runState + blocks give
    // us enough to reconstruct: strip out per-block outputs (keys equal to
    // block IDs) and system-added keys (__foo). What remains is _trigger +
    // any top-level input fields the workflow was originally started with.
    const initial_state: Record<string, unknown> = {}
    if (runState) {
      for (const [k, v] of Object.entries(runState)) {
        if (k.startsWith("__")) continue        // system-added
        if (blocks.has(k)) continue             // block output
        initial_state[k] = v
      }
    }
    _postAction(`${API}/workflows/${workflowId}/runs`, { initial_state }, (data) => {
      const newId = data.id as string | undefined
      if (newId && onRetry) onRetry(newId, workflowName)
    })
  }

  const pillColor = (() => {
    switch (status) {
      case "succeeded": return { bg: "var(--ok-bg, #dcfce7)", fg: "var(--ok-text, #166534)" }
      case "failed":    return { bg: "var(--err-bg, #fee2e2)", fg: "var(--err-text, #991b1b)" }
      case "running":   return { bg: "var(--accent-weak, rgba(59,130,246,0.12))", fg: "var(--accent-text, #2563eb)" }
      case "paused":    return { bg: "var(--warn-bg, #fef3c7)", fg: "var(--warn, #f59e0b)" }
      case "cancelled": return { bg: "var(--surface-3, #f3f4f6)", fg: "var(--text-muted)" }
      default:          return { bg: "var(--surface-3, #f3f4f6)", fg: "var(--text-muted)" }
    }
  })()

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Run · {workflowName}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <span style={{
            fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 999,
            background: pillColor.bg, color: pillColor.fg, textTransform: "capitalize",
          }}>{status}</span>
          {startedAt && (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {formatElapsed(startedAt, completedAt ?? now)}
            </span>
          )}
          <button
            onClick={() => setPanelOpen(o => !o)}
            aria-label={panelOpen ? "Collapse run detail" : "Expand run detail"}
            aria-expanded={panelOpen}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              borderRadius: 6, padding: "2px 8px", fontSize: 11,
              color: "var(--text-2)", cursor: "pointer", lineHeight: 1.4,
            }}
          >
            {panelOpen ? "▾ Collapse" : "▸ Expand"}
          </button>
          <a href={`/runs/${runId}`} style={{ fontSize: 13, color: "var(--accent)", textDecoration: "none" }}>
            View run →
          </a>
        </div>
        {outcome?.artifact_url && (
          <div style={{ marginBottom: 10, padding: "8px 12px", background: "var(--ok-bg, #dcfce7)", borderRadius: 6, fontSize: 12 }}>
            <span style={{ color: "var(--ok-text, #166534)", fontWeight: 600 }}>
              {outcome.type ? outcome.type.replace(/_/g, " ") : "artifact"}:
            </span>{" "}
            <a href={outcome.artifact_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", textDecoration: "none", wordBreak: "break-all" }}>
              {outcome.artifact_url}
            </a>
          </div>
        )}
        {error && (
          <div style={{ fontSize: 12, color: "var(--err-text, #991b1b)", background: "var(--err-bg, #fee2e2)", padding: "8px 12px", borderRadius: 6 }}>
            {error}
          </div>
        )}
        {actionErr && (
          <div style={{ fontSize: 12, color: "var(--err-text, #991b1b)", background: "var(--err-bg, #fee2e2)", padding: "6px 10px", borderRadius: 6, marginBottom: 8 }}>
            {actionErr}
          </div>
        )}
        {!panelOpen && workflowId && (status === "pending" || status === "running" || status === "paused" || status === "failed") && (
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            {(status === "pending" || status === "running") && (
              <button
                onClick={cancelRun}
                disabled={busy}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                  background: "transparent", color: "var(--text-2)",
                  fontSize: 12, cursor: busy ? "wait" : "pointer",
                }}
              >
                Cancel
              </button>
            )}
            {status === "paused" && (
              <>
                <button
                  onClick={() => decideRun("approved")}
                  disabled={busy}
                  style={{
                    padding: "6px 14px", borderRadius: 6, border: "none",
                    background: "var(--accent)", color: "#fff",
                    fontSize: 12, fontWeight: 600, cursor: busy ? "wait" : "pointer",
                  }}
                >
                  Approve
                </button>
                <button
                  onClick={() => decideRun("rejected")}
                  disabled={busy}
                  style={{
                    padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border)",
                    background: "transparent", color: "var(--text-2)",
                    fontSize: 12, cursor: busy ? "wait" : "pointer",
                  }}
                >
                  Reject
                </button>
              </>
            )}
            {status === "failed" && onRetry && (
              <button
                onClick={retryRun}
                disabled={busy}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "none",
                  background: "var(--accent)", color: "#fff",
                  fontSize: 12, fontWeight: 600, cursor: busy ? "wait" : "pointer",
                }}
              >
                Retry
              </button>
            )}
          </div>
        )}
        {blocks.size > 0 && (
          <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
            {Array.from(blocks.values()).map(b => {
              const isExpanded = expanded.has(b.id)
              const blockOutput = runState?.[b.id]
              const hasOutput = blockOutput !== undefined && b.status !== "pending" && b.status !== "running"
              return (
                <div key={b.id} style={{ padding: "4px 0" }}>
                  <div
                    onClick={hasOutput ? () => setExpanded(prev => {
                      const next = new Set(prev)
                      if (next.has(b.id)) next.delete(b.id); else next.add(b.id)
                      return next
                    }) : undefined}
                    style={{
                      display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12,
                      color: "var(--text-2)", cursor: hasOutput ? "pointer" : "default",
                    }}
                  >
                    <span style={{
                      display: "inline-block", width: 14, textAlign: "center",
                      color: b.status === "succeeded" ? "var(--ok-text, #166534)"
                           : b.status === "failed"    ? "var(--err-text, #991b1b)"
                           : b.status === "running"   ? "var(--accent-text, #2563eb)"
                           : "var(--text-muted)",
                    }}>{b.status === "succeeded" ? "✓" : b.status === "failed" ? "✗" : b.status === "running" ? "●" : "○"}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500, color: "var(--text)" }}>
                        {b.label ?? b.id}
                        {hasOutput && (
                          <span style={{ marginLeft: 8, fontSize: 10, color: "var(--text-muted)" }}>
                            {isExpanded ? "▾" : "▸"}
                          </span>
                        )}
                      </div>
                      {b.error && (
                        <div style={{ fontSize: 11, color: "var(--err-text, #991b1b)", marginTop: 2 }}>
                          {b.error}
                        </div>
                      )}
                    </div>
                  </div>
                  {isExpanded && hasOutput && (
                    <pre style={{
                      margin: "6px 0 6px 22px", padding: "8px 10px",
                      background: "var(--surface-3, rgba(0,0,0,0.03))",
                      border: "1px solid var(--border)", borderRadius: 6,
                      fontSize: 11, overflow: "auto", maxHeight: 240,
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      color: "var(--text-2)",
                    }}>
                      {JSON.stringify(blockOutput, null, 2)}
                    </pre>
                  )}
                </div>
              )
            })}
          </div>
        )}
        {panelOpen && workflowId && (
          <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
            <RunDetailPanel workflowId={workflowId} runId={runId} embedded initialRun={runData ?? undefined} />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Input ────────────────────────────────────────────────────────────────────

function ChatInput({ onSubmit, disabled }: { onSubmit: (t: string) => void; disabled: boolean }) {
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

// ─── Main page ────────────────────────────────────────────────────────────────

export function GLensChatPage({ initialSessionId }: { initialSessionId?: string } = {}) {
  const { authFetch, workspaceId } = useAuthFetch()
  const router = useRouter()

  const [sessions, setSessions] = useState<GLensSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  // #1480 PR 4 — SSE session stream. Returns null when the feature flag
  // (NEXT_PUBLIC_LENS_SSE_SURFACE) is off or no active session yet; bubbles
  // that opt in via useLensEvent silently degrade to the existing REST flow.
  const lensStream = useLensSessionStream(activeId)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS)
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem("glens.sidebar.collapsed") === "1"
  })

  useEffect(() => {
    if (typeof window === "undefined") return
    window.localStorage.setItem("glens.sidebar.collapsed", sidebarCollapsed ? "1" : "0")
  }, [sidebarCollapsed])

  const threadRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load session list
  useEffect(() => {
    if (!workspaceId) return
    authFetch(`${API}/glens/sessions`)
      .then(r => r.ok ? r.json() : [])
      .then(setSessions)
      .catch(() => {})
  }, [workspaceId, authFetch])

  // Deep-link entry: if the page mounted with an initialSessionId (URL
  // /lens/{id}), load it once. selectSession updates the URL via
  // router.replace, which is a no-op when we already match — so no loop.
  const initialLoadedRef = useRef(false)
  useEffect(() => {
    if (initialSessionId && !initialLoadedRef.current && workspaceId) {
      initialLoadedRef.current = true
      selectSession(initialSessionId)
    }
    // selectSession is stable within the component closure; omitting from deps
    // avoids re-firing when Redis-driven state updates cascade.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId, workspaceId])

  // Load data-grounded opener chips
  useEffect(() => {
    if (!workspaceId) return
    authFetch(`${API}/glens/opener`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.chips?.length) setSuggestions(d.chips) })
      .catch(() => {})
  }, [workspaceId, authFetch])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages])

  function startNew() {
    setActiveId(null)
    setMessages([])
    router.replace("/lens")
  }

  async function selectSession(id: string) {
    router.replace(`/lens/${id}`)
    setLoading(true)
    setActiveId(id)
    setMessages([])
    try {
      const res = await authFetch(`${API}/glens/sessions/${id}`)
      if (!res.ok) return
      const data = await res.json()
      const thread: Message[] = []
      for (const m of (data.messages ?? [])) {
        if (m.role === "user") {
          thread.push({ role: "user", text: m.content })
        } else {
          try {
            const p = JSON.parse(m.content)
            const rendered = m.rendered ?? {}
            if (p.ready && p.spec) {
              thread.push({ role: "assistant", kind: "dashboard", spec: p.spec, sessionId: id })
            } else if (rendered.rows?.length) {
              thread.push({ role: "assistant", kind: "table", rows: rendered.rows, answer: p.answer ?? "", skill: p.skill ?? "governance", columns: p.columns })
            } else if (rendered.blocks?.length) {
              thread.push({ role: "assistant", kind: "blocks", blocks: rendered.blocks, answer: p.answer ?? "", skill: p.skill ?? "governance" })
            } else if (p.confirm_envelope?.approval_request_id) {
              // #1480 PR 12 — rehydrate ActionConfirmBubble from persisted envelope
              const ce = p.confirm_envelope
              thread.push({
                role: "assistant", kind: "action_confirm",
                toolName: ce.tool_name,
                approvalRequestId: ce.approval_request_id,
                summary: ce.summary ?? "Confirm this action?",
                warnings: ce.warnings ?? [],
                expiresAt: ce.expires_at,
              })
            } else if (p.run_started?.run_id) {
              // #1480 PR 12 — rehydrate RunBubble from persisted envelope
              const rs = p.run_started
              thread.push({
                role: "assistant", kind: "run",
                runId: rs.run_id,
                workflowName: rs.workflow_name ?? "workflow",
                initialStatus: rs.status ?? "pending",
              })
            } else {
              const text = p.answer || p.question
              if (text) thread.push({ role: "assistant", kind: "answer", text, skill: p.skill })
            }
          } catch {
            thread.push({ role: "assistant", kind: "answer", text: m.content })
          }
        }
      }
      try {
        if (data.spec && !thread.find(m => m.role === "assistant" && (m as {kind:string}).kind === "dashboard")) {
          thread.push({ role: "assistant", kind: "dashboard", spec: data.spec, sessionId: id })
        }
      } catch { /* malformed spec — skip dashboard bubble */ }
      setMessages(thread)
    } finally {
      setLoading(false)
    }
  }

  async function deleteSession(id: string) {
    await authFetch(`${API}/glens/sessions/${id}`, { method: "DELETE" }).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== id))
    if (activeId === id) startNew()
  }

  async function renameSession(id: string, title: string) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, title } : s))
    await authFetch(`${API}/glens/sessions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).catch(() => {})
  }

  function _applyData(data: Record<string, unknown>, text: string) {
    if (!activeId && data.session_id) {
      setActiveId(data.session_id as string)
      setSessions(prev => [{ id: data.session_id as string, title: text.slice(0, 60), has_dashboard: !!data.spec, created_at: new Date().toISOString() }, ...prev])
    }
    if (data.clarification_required) {
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "answer",
        text: (data.answer as string) ?? "I need more detail to proceed.",
        skill: (data.skill as string) ?? "rules",
        followups: data.followups as string[] | undefined,
      }])
    } else if (data.run_started) {
      // Natural-language confirm path (#1480 PR 11): user typed "yes" and
      // the LLM called confirm_pending_action which returned a run_id.
      // Render <RunBubble> — same live surface the button-click path gets.
      const rs = data.run_started as { run_id: string; workflow_name: string; status: string }
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "run",
        runId: rs.run_id,
        workflowName: rs.workflow_name,
        initialStatus: rs.status ?? "pending",
      }])
    } else if (data.confirm_required && data.approval_request_id) {
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "action_confirm",
        toolName: data.tool_name as string,
        approvalRequestId: data.approval_request_id as string,
        summary: (data.summary as string) ?? "Confirm this action?",
        warnings: (data.warnings as string[] | undefined) ?? [],
        expiresAt: data.expires_at as string | undefined,
      }])
    } else if (data.confirm_required) {
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "policy_confirm",
        answer: (data.answer as string) ?? "Review the draft below:",
        action: data.action as string,
        draft: (data.draft as Record<string, unknown>) ?? {},
        mapping: (data.mapping as PolicyMapping[]) ?? [],
        targetRuleId: data.target_rule_id as string | undefined,
        sessionId: data.session_id as string,
        skill: (data.skill as string) ?? "rules",
        warning: data.warning as string | undefined,
      }])
    } else if (data.page_kind && data.page_data) {
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "page",
        answer: (data.answer as string) ?? "",
        pageKind: data.page_kind as string,
        pageData: data.page_data as Record<string, unknown>,
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
      }])
    } else if (data.blocks) {
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "blocks",
        answer: (data.answer as string) ?? "",
        blocks: data.blocks as unknown[],
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        understoodAs: data.query_understood_as as string | undefined,
      }])
    } else if (data.rows) {
      setMessages(prev => [...prev.slice(0, -1), {
        role: "assistant", kind: "table",
        answer: (data.answer as string) ?? "",
        columns: data.columns as unknown[] | undefined,
        rows: data.rows as unknown[],
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
        understoodAs: data.query_understood_as as string | undefined,
      }])
    } else if (data.ready && data.spec) {
      setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "dashboard", spec: data.spec as GlensDashboardSpec, sessionId: data.session_id as string }])
    } else {
      setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: (data.answer as string) ?? "No answer returned.", skill: data.skill as string | undefined, drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined, followups: data.followups as string[] | undefined, understoodAs: data.query_understood_as as string | undefined }])
    }
  }

  async function sendMessage(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, { role: "user", text }, { role: "assistant", kind: "loading" }])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (activeId) body.session_id = activeId

      const res = await authFetch(`${API}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: `Request failed (${res.status}). Try again.` }])
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const evt = JSON.parse(line.slice(6)) as Record<string, unknown>
          if (evt.type === "thinking") {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last?.role === "assistant" && last.kind === "loading") {
                return [...prev.slice(0, -1), { ...last, label: evt.label as string }]
              }
              return prev
            })
          } else if (evt.type === "token") {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last?.role === "assistant" && (last.kind === "loading" || last.kind === "streaming")) {
                const current = last.kind === "streaming" ? (last as { text: string }).text : ""
                return [...prev.slice(0, -1), { role: "assistant", kind: "streaming", text: current + (evt.text as string) }]
              }
              return prev
            })
          } else if (evt.type === "done") {
            _applyData(evt, text)
          } else if (evt.type === "error") {
            setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: (evt.message as string) ?? "Something went wrong." }])
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: "Network error. Please try again." }])
    } finally {
      setLoading(false)
    }
  }

  const hasThread = messages.length > 0

  return (
    <div style={{ display: "flex", height: "calc(100vh - 60px)", overflow: "hidden" }}>

      {/* Sidebar */}
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={selectSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onNew={startNew}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(v => !v)}
      />

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--surface)" }}>

        {/* Thread */}
        <div
          ref={threadRef}
          style={{ flex: 1, overflowY: "auto", padding: hasThread ? "32px 48px" : "0", display: hasThread ? "block" : "flex", flexDirection: "column", justifyContent: "center" }}
        >
          {!hasThread && (
            <div style={{ maxWidth: 680, width: "100%", margin: "0 auto", padding: "32px 24px" }}>
              <div style={{ textAlign: "center", marginBottom: 28 }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: "var(--text)", marginBottom: 8, letterSpacing: "-0.01em" }}>
                  What do you want to see?
                </div>
                <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
                  Ask about blocks, spend, sessions, team memory.
                </div>
              </div>
              <div style={{ marginBottom: 20 }}>
                <ChatInput onSubmit={sendMessage} disabled={loading} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8 }}>
                {suggestions.map(s => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    style={{
                      fontSize: 13,
                      padding: "12px 14px",
                      borderRadius: 10,
                      border: "1px solid var(--border)",
                      background: "var(--surface-2)",
                      color: "var(--text-2)",
                      cursor: "pointer",
                      textAlign: "left",
                      lineHeight: 1.4,
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ maxWidth: 800, margin: "0 auto" }}>
            {messages.map((msg, i) => {
              if (msg.role === "user") return (
                <UserBubble
                  key={i}
                  text={msg.text}
                  onEdit={newText => {
                    setMessages(prev => prev.slice(0, i))
                    sendMessage(newText)
                  }}
                />
              )
              if (msg.kind === "loading") return <LoadingBubble key={i} label={msg.label} />
              if (msg.kind === "streaming") return <AnswerBubble key={i} text={msg.text} skill="governance" />
              // Per-message copy text + stable id so feedback rows upsert on
              // the same (session, message, user) key across re-renders.
              const copyText =
                msg.kind === "answer" ? msg.text :
                msg.kind === "blocks" ? msg.answer :
                msg.kind === "table"  ? msg.answer :
                msg.kind === "page"   ? msg.answer :
                msg.kind === "policy_confirm" ? msg.answer :
                        msg.kind === "action_confirm" ? msg.summary :
                undefined
              const messageId = String(i)
              return (
                <div key={i}>
                  {msg.kind === "answer" && <AnswerBubble text={msg.text} skill={msg.skill} drilldown={msg.drilldown} followups={msg.followups} onFollowup={sendMessage} understoodAs={msg.understoodAs} />}
                  {msg.kind === "dashboard" && <DashboardBubble spec={msg.spec} sessionId={msg.sessionId} authFetch={authFetch} />}
                  {msg.kind === "blocks" && <BlocksBubble answer={msg.answer} blocks={msg.blocks as any} warning={msg.warning} skill={msg.skill} understoodAs={msg.understoodAs} />}
                  {msg.kind === "table" && <GenericTableBubble answer={msg.answer} columns={msg.columns as any} rows={msg.rows as any} warning={msg.warning} skill={msg.skill} drilldown={msg.drilldown} understoodAs={msg.understoodAs} />}
                  {msg.kind === "page" && <GlensPageBubble answer={msg.answer} pageKind={msg.pageKind as any} data={msg.pageData} warning={msg.warning} />}
                  {msg.kind === "action_confirm" && (
                    <ActionConfirmBubble
                      toolName={msg.toolName}
                      approvalRequestId={msg.approvalRequestId}
                      summary={msg.summary}
                      warnings={msg.warnings}
                      expiresAt={msg.expiresAt}
                      authFetch={authFetch}
                      stream={lensStream}
                      onResult={text => setMessages(prev => [
                        ...prev.slice(0, i),
                        { role: "assistant", kind: "answer", text },
                        ...prev.slice(i + 1),
                      ])}
                      onRunStarted={lensStream ? (runId, wfName, initialStatus) => setMessages(prev => [
                        ...prev.slice(0, i),
                        { role: "assistant", kind: "run", runId, workflowName: wfName, initialStatus },
                        ...prev.slice(i + 1),
                      ]) : undefined}
                      onRetry={(newRunId, wfName) => setMessages(prev => [
                        ...prev,
                        { role: "assistant", kind: "run", runId: newRunId, workflowName: wfName, initialStatus: "pending" },
                      ])}
                    />
                  )}
                  {msg.kind === "run" && (
                    <RunBubble
                      runId={msg.runId}
                      workflowName={msg.workflowName}
                      initialStatus={msg.initialStatus}
                      stream={lensStream}
                      authFetch={authFetch}
                      onRetry={(newRunId, wfName) => setMessages(prev => [
                        ...prev,
                        { role: "assistant", kind: "run", runId: newRunId, workflowName: wfName, initialStatus: "pending" },
                      ])}
                    />
                  )}
                  {msg.kind === "policy_confirm" && (
                    <PolicyConfirmBubble
                      answer={msg.answer}
                      action={msg.action}
                      skill={msg.skill}
                      draft={msg.draft}
                      mapping={msg.mapping}
                      targetRuleId={msg.targetRuleId}
                      sessionId={msg.sessionId}
                      authFetch={authFetch}
                      warning={msg.warning}
                      onResult={text => setMessages(prev => [
                        ...prev.slice(0, i),
                        { role: "assistant", kind: "answer", text, skill: msg.skill },
                        ...prev.slice(i + 1),
                      ])}
                    />
                  )}
                  <MessageFooter text={copyText} sessionId={activeId} messageId={messageId} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Input — bottom-anchored once the thread has content */}
        {hasThread && (
          <div style={{ borderTop: "1px solid var(--border)", background: "var(--surface)", padding: "12px 48px 16px" }}>
            <div style={{ maxWidth: 800, margin: "0 auto" }}>
              <ChatInput onSubmit={sendMessage} disabled={loading} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
