"use client"
import { useEffect, useRef, useState } from "react"

export function UserBubble({ text, onEdit }: { text: string; onEdit?: (newText: string) => void }) {
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
