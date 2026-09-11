"use client"
import { useEffect, useRef, useState } from "react"
import type { GLensSession } from "@/components/glens/glensTypes"

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

export function Sidebar({
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
