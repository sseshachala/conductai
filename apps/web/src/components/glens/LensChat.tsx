"use client"
/**
 * LensChat — headless chat surface (messages + composer + SSE streaming loop).
 *
 * Shared by `LensPanel` (docked drawer) and `LensEmbed` (inline capability
 * per #1830). Any component that wants Lens dropped into it renders this and
 * owns the outer container.
 *
 * Streams from `/glens/chat/stream` — same endpoint the full-page canvas uses.
 * Text rendering flows through `AnswerBubble`. Mutating actor tools return
 * a `confirm_required` envelope in the SSE `done` event; those render as
 * `ActionConfirmBubble` inline so the user can Confirm/Cancel without a
 * chat round-trip. Session id is persisted to localStorage when the host
 * supplies a `persistKey` so subsequent mounts resume the same server-side
 * session.
 */

import { useEffect, useRef, useState } from "react"
import { API } from "@/lib/api"
import { LensSettings } from "./LensSettings"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { AnswerBubble } from "@/components/glens/bubbles/AnswerBubble"
import { ActionConfirmBubble } from "@/components/glens/bubbles/ActionConfirmBubble"
import { lensEntryQuestion, lensRequestError, type LensEntry } from "@/lib/lens-entry"

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "streaming"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; drilldown?: string; complex?: boolean; sessionId?: string }
  | { role: "assistant"; kind: "error"; text: string }
  | {
      role: "assistant"
      kind: "action_confirm"
      toolName: string
      approvalRequestId: string
      summary: string
      warnings?: string[]
      expiresAt?: string
    }
  | { role: "assistant"; kind: "action_done"; text: string }

export function LensChat({
  pathname,
  initialQuery,
  initialEntry,
  initialSessionId,
  onSessionId,
  onExpandMessage,
  autoFocusOnMount = true,
  placeholder = "Ask Lens…",
  emptyText = "Ask about anything on this page. Lens is Guard-enforced.",
  persistKey,
}: {
  pathname?: string | null
  initialQuery?: string | null
  initialEntry?: LensEntry | null
  initialSessionId?: string | null
  onSessionId?: (sid: string) => void
  onExpandMessage?: (sid?: string) => void
  autoFocusOnMount?: boolean
  placeholder?: string
  emptyText?: string
  /** localStorage key namespace for session_id persistence. When set, the
   *  session id is loaded on mount and saved on every server-issued update,
   *  so a page reload resumes the same server-side session (no forgotten
   *  pending_action_ids, no lost conversation). Omit to opt out. */
  persistKey?: string
}) {
  const { authFetch, workspaceId } = useAuthFetch()
  const [messages, setMessages] = useState<Message[]>([])
  const [composer, setComposer] = useState("")
  const [loading, setLoading] = useState(false)
  const [retryText, setRetryText] = useState<string | null>(null)
  const pendingEntry = useRef(initialEntry)
  const _storageKey = persistKey ? `lens.session.${persistKey}` : null
  const [sessionId, setSessionId] = useState<string | null>(() => {
    if (initialSessionId) return initialSessionId
    if (_storageKey && typeof window !== "undefined") {
      try { return window.localStorage.getItem(_storageKey) ?? null } catch { return null }
    }
    return null
  })
  const abortRef = useRef<AbortController | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const initialQuerySentRef = useRef<string | null>(null)

  useEffect(() => {
    const query = initialQuery || (initialEntry ? lensEntryQuestion(initialEntry) : null)
    if (!query || (initialEntry && !workspaceId)) return
    if (initialQuerySentRef.current === query) return
    initialQuerySentRef.current = query
    void send(query)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery, initialEntry, workspaceId])

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
    setRetryText(null)
    let receivedResponse = false
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined

    try {
      const body: Record<string, unknown> = { message: text }
      if (pendingEntry.current && pendingEntry.current.workspace_id !== workspaceId) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: lensRequestError(409) }])
        return
      }
      if (pendingEntry.current) body.entry_context = pendingEntry.current
      else if (sessionId) body.session_id = sessionId
      if (pathname) body.page_context = pathname

      const res = await authFetch(`${API}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (controller.signal.aborted) return
      receivedResponse = true
      if (!res.ok) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: lensRequestError(res.status) }])
        setRetryText(text)
        return
      }

      reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ""
      let streamedText = ""

      while (true) {
        const { done, value } = await reader.read()
        if (controller.signal.aborted) return
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === "token") {
              streamedText += evt.text
              setMessages(prev => {
                const copy = prev.slice()
                copy[copy.length - 1] = { role: "assistant", kind: "streaming", text: streamedText }
                return copy
              })
            } else if (evt.type === "done") {
              pendingEntry.current = null
              if (evt.session_id) {
                setSessionId(evt.session_id)
                onSessionId?.(evt.session_id)
                if (_storageKey && typeof window !== "undefined") {
                  try { window.localStorage.setItem(_storageKey, evt.session_id) } catch { /* quota / private mode */ }
                }
              }

              // Mutating actor tool returned a confirm envelope — render
              // ActionConfirmBubble in-place instead of the answer bubble.
              // (GLensChatPage does the same on the full-page canvas;
              // LensEmbed was missing this branch, which is why the
              // "confirm the card above" prose landed with no card.)
              if (evt.confirm_required && evt.approval_request_id) {
                setMessages(prev => {
                  const copy = prev.slice()
                  copy[copy.length - 1] = {
                    role: "assistant",
                    kind: "action_confirm",
                    toolName: (evt.tool_name as string) ?? "action",
                    approvalRequestId: evt.approval_request_id as string,
                    summary: (evt.summary as string) ?? (evt.answer as string) ?? "Confirm this action?",
                    warnings: (evt.warnings as string[] | undefined) ?? [],
                    expiresAt: evt.expires_at as string | undefined,
                  }
                  return copy
                })
                return
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
              return
            } else if (evt.type === "error") {
              setRetryText(text)
              setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: evt.message || "Error" }])
              return
            }
          }
        }
      }
      throw new Error("incomplete stream")
    } catch (e) {
      if (controller.signal.aborted || (e as Error).name === "AbortError") return
      setRetryText(text)
      setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "error", text: receivedResponse
        ? "Lens could not complete the response. Retry this investigation."
        : "Unable to connect to Lens. Please try again." }])
    } finally {
      if (reader) {
        void reader.cancel().catch(() => {})
        reader.releaseLock()
      }
      if (abortRef.current === controller) setLoading(false)
    }
  }

  return (
    <>
      <LensSettings disabled={loading} />
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
          <MsgBubble
            key={i} m={m}
            authFetch={authFetch}
            onExpand={onExpandMessage}
            onActionResolved={(text) => setMessages(prev => [...prev, { role: "assistant", kind: "action_done", text }])}
          />
        ))}
        {retryText && !loading && <button type="button" className="btn btn-secondary btn-sm"
          style={{ alignSelf: "flex-start" }} onClick={() => void send(retryText)}>Retry</button>}
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

function MsgBubble({
  m, authFetch, onExpand, onActionResolved,
}: {
  m: Message
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onExpand?: (sessionId?: string) => void
  onActionResolved: (text: string) => void
}) {
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

  if (m.kind === "action_confirm") {
    return (
      <ActionConfirmBubble
        toolName={m.toolName}
        approvalRequestId={m.approvalRequestId}
        summary={m.summary}
        warnings={m.warnings}
        expiresAt={m.expiresAt}
        authFetch={authFetch}
        stream={null}
        onResult={onActionResolved}
      />
    )
  }

  if (m.kind === "action_done") {
    return <AnswerBubble dense text={m.text} />
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
