"use client"

/**
 * Thumbs up/down feedback on a single Lens assistant message.
 *
 * Backend: POST /glens/chat/feedback (upserts on session_id + message_id +
 * clerk_user_id). No wiring here — parent owns sessionId / messageId; drop
 * this next to <CopyButton> when both PRs land.
 */

import { useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

type Verdict = "up" | "down" | null

export function FeedbackButtons({
  sessionId,
  messageId,
  onSubmit,
}: {
  sessionId: string
  messageId: string
  onSubmit?: (verdict: "up" | "down") => void
}) {
  const [verdict, setVerdict] = useState<Verdict>(null)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { authFetch } = useAuthFetch()

  async function _submit(v: "up" | "down", commentValue?: string) {
    setSaving(true)
    setError(null)
    try {
      const res = await authFetch(`${API}/glens/chat/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
          verdict: v,
          comment: commentValue?.trim() ? commentValue.trim() : null,
        }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        setError(detail?.detail ?? `Failed (${res.status})`)
        return
      }
      setVerdict(v)
      onSubmit?.(v)
      if (v === "down" && !commentValue) setShowComment(true)
    } finally {
      setSaving(false)
    }
  }

  const iconBtn = (v: "up" | "down", active: boolean) => (
    <button
      type="button"
      onClick={() => _submit(v)}
      disabled={saving}
      aria-label={v === "up" ? "Helpful" : "Not helpful"}
      title={v === "up" ? "Helpful" : "Not helpful"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 26,
        height: 26,
        color: active
          ? (v === "up" ? "var(--ok, #10b981)" : "var(--warn, #d97706)")
          : "var(--text-muted)",
        background: "transparent",
        border: "1px solid transparent",
        borderRadius: 6,
        cursor: saving ? "wait" : "pointer",
        transition: "background 0.12s, color 0.12s",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-3, rgba(0,0,0,0.04))")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      {v === "up" ? (
        <svg width={14} height={14} viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 10v12" />
          <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7V10l5-9 2 1.4a2 2 0 0 1 .88 2.48Z" />
        </svg>
      ) : (
        <svg width={14} height={14} viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 14V2" />
          <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17v12l-5 9-2-1.4a2 2 0 0 1-.88-2.48Z" />
        </svg>
      )}
    </button>
  )

  return (
    <div style={{ display: "inline-flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
      <div style={{ display: "inline-flex", gap: 0 }}>
        {iconBtn("up", verdict === "up")}
        {iconBtn("down", verdict === "down")}
      </div>
      {showComment && verdict === "down" && (
        <div style={{ display: "flex", gap: 4, alignItems: "center", marginTop: 2 }}>
          <input
            type="text"
            value={comment}
            onChange={e => setComment(e.target.value)}
            placeholder="Anything we can improve? (optional)"
            maxLength={2000}
            autoFocus
            style={{
              width: 260,
              fontSize: 11,
              padding: "4px 8px",
              border: "1px solid var(--border)",
              borderRadius: 4,
              background: "var(--surface)",
              color: "var(--text)",
            }}
            onKeyDown={e => {
              if (e.key === "Enter") { _submit("down", comment); setShowComment(false) }
              else if (e.key === "Escape") setShowComment(false)
            }}
          />
          <button
            type="button"
            onClick={() => { _submit("down", comment); setShowComment(false) }}
            disabled={saving}
            style={{
              fontSize: 11,
              padding: "4px 10px",
              border: "1px solid var(--border)",
              borderRadius: 4,
              background: "var(--surface-2)",
              color: "var(--text)",
              cursor: saving ? "wait" : "pointer",
            }}
          >
            Send
          </button>
        </div>
      )}
      {error && (
        <div style={{ fontSize: 10, color: "var(--err, #dc2626)" }}>{error}</div>
      )}
    </div>
  )
}
