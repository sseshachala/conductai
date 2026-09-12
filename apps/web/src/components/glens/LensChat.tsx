"use client"
/**
 * LensChat — headless chat surface (messages + composer + SSE streaming loop).
 *
 * Shared by `LensPanel` (docked drawer) and `LensEmbed` (inline capability
 * per #1830). Any component that wants Lens dropped into it renders this and
 * owns the outer container.
 *
 * Streams from `/glens/chat/stream` — same endpoint the full-page canvas uses.
 * All rendering flows through `AnswerBubble` — one bubble, one markdown parser.
 */

import { useEffect, useRef, useState } from "react"
import { API } from "@/lib/api"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { AnswerBubble } from "@/components/glens/bubbles/AnswerBubble"

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "streaming"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; drilldown?: string; complex?: boolean; sessionId?: string }
  | { role: "assistant"; kind: "error"; text: string }

export function LensChat({
  pathname,
  initialQuery,
  initialSessionId,
  onSessionId,
  onExpandMessage,
  autoFocusOnMount = true,
  placeholder = "Ask Lens…",
  emptyText = "Ask about anything on this page. Lens is Guard-enforced.",
}: {
  pathname?: string | null
  initialQuery?: string | null
  initialSessionId?: string | null
  onSessionId?: (sid: string) => void
  onExpandMessage?: (sid?: string) => void
  autoFocusOnMount?: boolean
  placeholder?: string
  emptyText?: string
}) {
  const { authFetch } = useAuthFetch()
  const [messages, setMessages] = useState<Message[]>([])
  const [composer, setComposer] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId ?? null)
  const abortRef = useRef<AbortController | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const initialQuerySentRef = useRef<string | null>(null)

  useEffect(() => {
    if (!initialQuery) return
    if (initialQuerySentRef.current === initialQuery) return
    initialQuerySentRef.current = initialQuery
    void send(initialQuery)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery])

  useEffect(() => {
    if (autoFocusOnMount && !initialQuery) composerRef.current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  async function send(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, { role: "user", text }, { role: "assistant", kind: "streaming", text: "" }])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (sessionId) body.session_id = sessionId
      if (pathname) body.page_context = pathname

      const res = await authFetch(`${API}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!res.ok) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: `Request failed (${res.status}).` }])
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ""
      let streamedText = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === "token") {
              streamedText += evt.text
              setMessages(prev => {
                const copy = prev.slice()
                copy[copy.length - 1] = { role: "assistant", kind: "streaming", text: streamedText }
                return copy
              })
            } else if (evt.type === "done") {
              if (evt.session_id) {
                setSessionId(evt.session_id)
                onSessionId?.(evt.session_id)
              }
              const complex = Boolean(evt.spec || evt.blocks || evt.page_kind)
              setMessages(prev => {
                const copy = prev.slice()
                copy[copy.length - 1] = {
                  role: "assistant",
                  kind: "answer",
                  text: evt.answer || streamedText || "",
                  drilldown: evt.drilldown?.path,
                  complex,
                  sessionId: evt.session_id,
                }
                return copy
              })
            } else if (evt.type === "error") {
              setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: evt.message || "Error" }])
            }
          } catch { /* ignore malformed SSE payloads */ }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return
      setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: (e as Error).message }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div
        ref={bodyRef}
        style={{
          flex: 1, minHeight: 0, overflowY: "auto", padding: 14,
          display: "flex", flexDirection: "column",
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 8 }}>
            {emptyText}
          </div>
        )}

        {messages.map((m, i) => (
          <MsgBubble key={i} m={m} onExpand={onExpandMessage} />
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          const q = composer.trim()
          if (!q || loading) return
          setComposer("")
          void send(q)
        }}
        style={{
          borderTop: "1px solid var(--border)", padding: 10,
          background: "var(--surface-1)",
        }}
      >
        <textarea
          ref={composerRef}
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              const q = composer.trim()
              if (!q || loading) return
              setComposer("")
              void send(q)
            }
          }}
          placeholder={placeholder}
          rows={2}
          disabled={loading}
          style={{
            width: "100%", resize: "none", border: "1px solid var(--border)",
            borderRadius: 6, padding: "8px 10px", fontSize: 13,
            background: "var(--surface-2)", color: "var(--text)", outline: "none",
            fontFamily: "inherit",
          }}
        />
      </form>
    </>
  )
}

function MsgBubble({ m, onExpand }: { m: Message; onExpand?: (sessionId?: string) => void }) {
  if (m.role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
        <div style={{
          maxWidth: "85%", background: "var(--accent, #6366f1)", color: "#fff",
          borderRadius: "14px 14px 4px 14px", padding: "8px 12px", fontSize: 13, lineHeight: 1.5,
        }}>{m.text}</div>
      </div>
    )
  }

  if (m.kind === "streaming") {
    return <AnswerBubble dense streaming text={m.text} />
  }

  if (m.kind === "error") {
    return <AnswerBubble dense tone="error" text={m.text} />
  }

  return (
    <AnswerBubble
      dense
      text={m.text}
      drilldown={m.drilldown ? { path: m.drilldown } : undefined}
      footer={m.complex && onExpand && (
        <div style={{ marginTop: 6, textAlign: "right" }}>
          <button
            onClick={() => onExpand(m.sessionId)}
            style={{
              border: "none", background: "transparent",
              fontSize: 11, color: "var(--accent, #6366f1)", cursor: "pointer",
              fontWeight: 500, padding: 0,
            }}
          >Open in Lens →</button>
        </div>
      )}
    />
  )
}
