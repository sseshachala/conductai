"use client"
/**
 * LensPanel — right-side chat drawer (#B1 + #B2 + #B4 from epic #1214).
 *
 * Copilot-style overlay: user asks Lens without leaving the current page.
 * Streams from the same /glens/chat/stream endpoint the full page uses,
 * with `page_context` set to the caller's pathname so answers stay
 * scoped to what the user is looking at.
 *
 * Rich responses (blocks / page / dashboard bubbles) collapse to a
 * "View in Lens →" affordance — the panel is optimised for quick text
 * answers; the full canvas is one click away.
 */

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { API } from "@/lib/api"
import { useAuthFetch } from "@/hooks/useAuthFetch"

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "streaming"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; drilldown?: string; complex?: boolean; sessionId?: string }
  | { role: "assistant"; kind: "error"; text: string }

export function LensPanel({
  open,
  initialQuery,
  pathname,
  onClose,
}: {
  open: boolean
  initialQuery: string | null
  pathname: string | null
  onClose: () => void
}) {
  const router = useRouter()
  const { authFetch } = useAuthFetch()
  const [messages, setMessages] = useState<Message[]>([])
  const [composer, setComposer] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const initialQuerySentRef = useRef<string | null>(null)

  // Auto-send the initial query once per open/query pair.
  useEffect(() => {
    if (!open || !initialQuery) return
    if (initialQuerySentRef.current === initialQuery) return
    initialQuerySentRef.current = initialQuery
    void send(initialQuery)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialQuery])

  // Focus composer when opened without an initial query.
  useEffect(() => {
    if (open && !initialQuery) composerRef.current?.focus()
  }, [open, initialQuery])

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages])

  // Escape closes.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

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
              if (evt.session_id) setSessionId(evt.session_id)
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

  if (!open) return null

  return (
    <div
      style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 420, zIndex: 300,
        background: "var(--surface)", borderLeft: "1px solid var(--border)",
        display: "flex", flexDirection: "column",
        boxShadow: "-4px 0 20px rgba(0,0,0,.12)",
      }}
      role="dialog"
      aria-label="Ask Lens panel"
    >
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid var(--border)",
        background: "var(--surface-1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text)" }}>Lens</span>
          {pathname && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>· {pathname}</span>}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => {
              const target = sessionId ? `/lens/${sessionId}` : "/lens"
              router.push(target)
              onClose()
            }}
            title="Expand to full Lens"
            aria-label="Expand to full Lens"
            style={{
              border: "1px solid var(--border)", background: "var(--surface-2)",
              color: "var(--text-2)", padding: "3px 8px", borderRadius: 6,
              fontSize: 11, cursor: "pointer",
            }}
          >Expand →</button>
          <button
            onClick={onClose}
            title="Close"
            aria-label="Close Lens panel"
            style={{
              width: 26, height: 26, borderRadius: 6, border: "1px solid var(--border)",
              background: "var(--surface-2)", color: "var(--text-2)", cursor: "pointer",
              fontSize: 14, lineHeight: 1,
            }}
          >×</button>
        </div>
      </div>

      {/* Messages */}
      <div
        ref={bodyRef}
        style={{
          flex: 1, overflowY: "auto", padding: 14,
          display: "flex", flexDirection: "column",
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 8 }}>
            Ask about anything on this page. Lens is Guard-enforced.
          </div>
        )}

        {messages.map((m, i) => (
          <MsgBubble key={i} m={m} onExpand={(sid) => { router.push(sid ? `/lens/${sid}` : "/lens"); onClose() }} />
        ))}
      </div>

      {/* Composer */}
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
          placeholder="Ask Lens…"
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
    </div>
  )
}


function MsgBubble({ m, onExpand }: { m: Message; onExpand: (sessionId?: string) => void }) {
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
    return (
      <AssistantWrap>
        <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
        <span style={{ opacity: .5 }}>▍</span>
      </AssistantWrap>
    )
  }

  if (m.kind === "error") {
    return (
      <AssistantWrap tone="error">{m.text}</AssistantWrap>
    )
  }

  // answer
  return (
    <AssistantWrap>
      <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
      {(m.drilldown || m.complex) && (
        <div style={{ marginTop: 8, display: "flex", gap: 8, justifyContent: "flex-end" }}>
          {m.drilldown && (
            <a href={m.drilldown} style={{ fontSize: 11, color: "var(--accent, #6366f1)", textDecoration: "none", fontWeight: 500 }}>
              View full &rarr;
            </a>
          )}
          {m.complex && (
            <button
              onClick={() => onExpand(m.sessionId)}
              style={{
                border: "none", background: "transparent",
                fontSize: 11, color: "var(--accent, #6366f1)", cursor: "pointer",
                fontWeight: 500, padding: 0,
              }}
            >Open in Lens →</button>
          )}
        </div>
      )}
    </AssistantWrap>
  )
}


function AssistantWrap({ children, tone }: { children: React.ReactNode; tone?: "error" }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 10 }}>
      <div style={{
        maxWidth: "92%",
        background: tone === "error" ? "rgba(239,68,68,.08)" : "var(--surface-2)",
        border: `1px solid ${tone === "error" ? "rgba(239,68,68,.35)" : "var(--border)"}`,
        color: tone === "error" ? "#ef4444" : "var(--text)",
        borderRadius: "4px 14px 14px 14px",
        padding: "8px 12px", fontSize: 13, lineHeight: 1.5,
      }}>{children}</div>
    </div>
  )
}
