"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { GlensDashboard } from "@/components/glens/GlensDashboard"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"
import { GlensPageBubble } from "@/components/glens/GlensPageBubble"
import { GenericTableBubble } from "@/components/glens/GenericTableBubble"
import type { Column } from "@/components/glens/GenericTableBubble"
import { BlocksBubble } from "@/components/glens/BlocksBubble"

type Attachment =
  | { type: "dashboard"; spec: GlensDashboardSpec }
  | { type: "page"; page_kind: string; data: Record<string, unknown>; warning?: string }
  | { type: "table"; rows: Record<string, unknown>[]; columns?: Column[]; warning?: string; skill?: string }
  | { type: "blocks"; blocks: Record<string, unknown>[]; warning?: string; skill?: string }
  | { type: "download"; download_url: string; download_name?: string; label?: string }

type ChatMessage = {
  id: string
  role: "user" | "assistant"
  answer: string
  thinking?: string
  attachments?: Attachment[]
  followups?: string[]
  skill?: string
  loading?: boolean
}

type SessionItem = {
  id: string
  title: string
  created_at: string
  has_dashboard: boolean
}

type ConversationMode = "page" | "panel"

const BASE_FOLLOWUPS = ["Show blocked events", "Who was affected?", "Open compliance"]

function messageId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function apiBase() {
  return process.env.NEXT_PUBLIC_API_URL ?? ""
}

function pageContextFromPath(pathname: string): string {
  if (pathname.includes("/theguard/activity")) return "activity"
  if (pathname.includes("/theguard/policies")) return "policies"
  if (pathname.includes("/theguard/spend")) return "spend"
  if (pathname.includes("/theguard/compliance")) return "compliance"
  if (pathname.includes("/theguard/discovery")) return "discovery"
  if (pathname.includes("/theguard/chat")) return "chat"
  return "governance"
}

function payloadToMessage(payload: Record<string, unknown>, fallbackAnswer = ""): ChatMessage {
  const attachments = Array.isArray(payload.attachments)
    ? payload.attachments as Attachment[]
    : buildAttachmentsFromCompatPayload(payload)

  const followups = Array.isArray(payload.followups)
    ? payload.followups.map(item => String(item))
    : BASE_FOLLOWUPS

  return {
    id: messageId(),
    role: "assistant",
    answer: String(payload.answer ?? payload.question ?? fallbackAnswer ?? ""),
    attachments,
    followups,
    skill: typeof payload.skill === "string" ? payload.skill : undefined,
    loading: false,
  }
}

function buildAttachmentsFromCompatPayload(payload: Record<string, unknown>): Attachment[] {
  const attachments: Attachment[] = []
  if (payload.spec && typeof payload.spec === "object") {
    attachments.push({ type: "dashboard", spec: payload.spec as GlensDashboardSpec })
  }
  if (payload.page_kind && payload.page_data && typeof payload.page_kind === "string" && typeof payload.page_data === "object") {
    attachments.push({
      type: "page",
      page_kind: payload.page_kind,
      data: payload.page_data as Record<string, unknown>,
      warning: typeof payload.warning === "string" ? payload.warning : undefined,
    })
  }
  if (Array.isArray(payload.blocks) && payload.blocks.length > 0) {
    attachments.push({
      type: "blocks",
      blocks: payload.blocks as Record<string, unknown>[],
      warning: typeof payload.warning === "string" ? payload.warning : undefined,
      skill: typeof payload.skill === "string" ? payload.skill : undefined,
    })
  }
  if (Array.isArray(payload.rows) && payload.rows.length > 0) {
    attachments.push({
      type: "table",
      rows: payload.rows as Record<string, unknown>[],
      columns: Array.isArray(payload.columns) ? payload.columns as Column[] : undefined,
      warning: typeof payload.warning === "string" ? payload.warning : undefined,
      skill: typeof payload.skill === "string" ? payload.skill : undefined,
    })
  }
  if (typeof payload.download_url === "string" && payload.download_url) {
    attachments.push({
      type: "download",
      download_url: payload.download_url,
      download_name: typeof payload.download_name === "string" ? payload.download_name : undefined,
      label: "Download CSV",
    })
  }
  return attachments
}

function parseAssistantContent(content: string): ChatMessage {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    return payloadToMessage(parsed)
  } catch {
    return {
      id: messageId(),
      role: "assistant",
      answer: content,
      followups: BASE_FOLLOWUPS,
    }
  }
}

function parseSseBlock(block: string): { event: string; data: string } | null {
  const lines = block.split("\n").filter(Boolean)
  if (lines.length === 0) return null
  const event = lines.find(line => line.startsWith("event:"))?.slice(6).trim() ?? "message"
  const data = lines
    .filter(line => line.startsWith("data:"))
    .map(line => line.slice(5).trim())
    .join("\n")
  return { event, data }
}

function AssistantBubble({
  message,
  authFetch,
  sessionId,
  onQuickReply,
  onOpenFullPage,
}: {
  message: ChatMessage
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  sessionId: string | null
  onQuickReply: (text: string) => void
  onOpenFullPage: () => void
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "flex-start" }}>
        <div
          style={{
            maxWidth: "100%",
            width: "100%",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: "4px 14px 14px 14px",
            padding: "14px 16px",
          }}
        >
          {message.answer && (
            <div style={{ fontSize: 14, color: "var(--text)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              {message.answer.trim()}
            </div>
          )}
          {message.thinking && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontStyle: "italic", marginTop: message.answer ? 10 : 0 }}>
              {message.thinking}
            </div>
          )}
        </div>
      </div>

      {message.attachments?.map((attachment, index) => {
        if (attachment.type === "dashboard") {
          return (
            <div key={index} style={{ paddingLeft: 8 }}>
              <GlensDashboard
                spec={attachment.spec}
                sessionId={sessionId ?? "live"}
                compact
                authFetch={authFetch}
                onPin={onOpenFullPage}
              />
            </div>
          )
        }
        if (attachment.type === "page") {
          return (
            <GlensPageBubble
              key={index}
              answer=""
              pageKind={attachment.page_kind as never}
              data={attachment.data}
              warning={attachment.warning}
            />
          )
        }
        if (attachment.type === "table") {
          return (
            <GenericTableBubble
              key={index}
              answer=""
              columns={attachment.columns}
              rows={attachment.rows}
              warning={attachment.warning}
              skill={attachment.skill}
            />
          )
        }
        if (attachment.type === "blocks") {
          return (
            <BlocksBubble
              key={index}
              answer=""
              blocks={attachment.blocks as never[]}
              warning={attachment.warning}
              skill={attachment.skill}
            />
          )
        }
        if (attachment.type === "download") {
          return (
            <div key={index} style={{ display: "flex", justifyContent: "flex-start" }}>
              <a
                href={attachment.download_url}
                download={attachment.download_name}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "10px 12px",
                  borderRadius: 10,
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  textDecoration: "none",
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                ⬇ {attachment.label ?? "Download"}
              </a>
            </div>
          )
        }
        return null
      })}

      {message.followups && message.followups.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, paddingLeft: 4 }}>
          {message.followups.map(followup => (
            <button
              key={followup}
              type="button"
              onClick={() => onQuickReply(followup)}
              style={{
                padding: "6px 10px",
                borderRadius: 999,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text-2)",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              {followup}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function UserBubble({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end" }}>
      <div
        style={{
          maxWidth: "82%",
          background: "var(--accent)",
          color: "white",
          borderRadius: "14px 4px 14px 14px",
          padding: "12px 14px",
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </div>
    </div>
  )
}

function SessionList({
  sessions,
  activeId,
  onSelect,
  onNewChat,
}: {
  sessions: SessionItem[]
  activeId: string | null
  onSelect: (id: string) => void
  onNewChat: () => void
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, height: "100%" }}>
      <button
        type="button"
        onClick={onNewChat}
        style={{
          padding: "10px 12px",
          borderRadius: 10,
          border: "1px solid var(--border)",
          background: "var(--surface-2)",
          color: "var(--text)",
          textAlign: "left",
          cursor: "pointer",
          fontWeight: 600,
        }}
      >
        + New chat
      </button>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, overflowY: "auto" }}>
        {sessions.map(session => (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelect(session.id)}
            style={{
              padding: "10px 12px",
              borderRadius: 10,
              border: activeId === session.id ? "1px solid var(--accent)" : "1px solid var(--border)",
              background: activeId === session.id ? "rgba(99,102,241,0.08)" : "var(--surface)",
              color: "var(--text)",
              textAlign: "left",
              cursor: "pointer",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{session.title || "Untitled chat"}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {new Date(session.created_at).toLocaleDateString()} {session.has_dashboard ? "• dashboard" : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

export function GLensConversation({ mode }: { mode: ConversationMode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { authFetch } = useAuthFetch()
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [panelOpen, setPanelOpen] = useState(mode === "page")
  const [openerLoaded, setOpenerLoaded] = useState(false)
  const endRef = useRef<HTMLDivElement | null>(null)
  const pageContext = useMemo(() => pageContextFromPath(pathname), [pathname])

  const refreshSessions = useCallback(async () => {
    const res = await authFetch(`${apiBase()}/glens/sessions`)
    if (!res.ok) return
    const data = await res.json()
    setSessions(Array.isArray(data) ? data : [])
  }, [authFetch])

  const loadOpener = useCallback(async () => {
    if (openerLoaded || activeId) return
    const res = await authFetch(`${apiBase()}/glens/opener?page_context=${encodeURIComponent(pageContext)}`)
    if (!res.ok) return
    const data = await res.json()
    setMessages([payloadToMessage(data)])
    setOpenerLoaded(true)
  }, [activeId, authFetch, openerLoaded, pageContext])

  const loadSession = useCallback(async (sessionId: string) => {
    const res = await authFetch(`${apiBase()}/glens/sessions/${sessionId}`)
    if (!res.ok) return
    const data = await res.json()
    const restored = Array.isArray(data.messages)
      ? data.messages.flatMap((message: Record<string, unknown>) => {
          if (message.role === "user") {
            return [{
              id: messageId(),
              role: "user" as const,
              answer: String(message.content ?? ""),
            }]
          }
          if (message.role === "assistant") {
            return [parseAssistantContent(String(message.content ?? ""))]
          }
          return []
        })
      : []
    setActiveId(sessionId)
    setMessages(restored)
    setOpenerLoaded(true)
    if (mode === "panel") setPanelOpen(true)
  }, [authFetch, mode])

  const startNewChat = useCallback(() => {
    setActiveId(null)
    setMessages([])
    setOpenerLoaded(false)
  }, [])

  useEffect(() => {
    refreshSessions()
  }, [refreshSessions])

  useEffect(() => {
    if (!activeId && panelOpen) {
      loadOpener()
    }
  }, [activeId, loadOpener, panelOpen])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return
    setLoading(true)
    const placeholderId = messageId()
    setInput("")
    setMessages(prev => [
      ...prev,
      { id: messageId(), role: "user", answer: trimmed },
      { id: placeholderId, role: "assistant", answer: "", thinking: "Getting Guard context ready…", followups: [], loading: true },
    ])

    const body = JSON.stringify({
      message: trimmed,
      session_id: activeId ?? undefined,
      page_context: pageContext,
    })

    try {
      const res = await authFetch(`${apiBase()}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      })
      if (!res.ok || !res.body) {
        const fallback = await authFetch(`${apiBase()}/glens/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        })
        if (!fallback.ok) throw new Error("Chat unavailable")
        const payload = await fallback.json()
        const nextMessage = payloadToMessage(payload)
        setMessages(prev => prev.map(message => (
          message.id === placeholderId ? nextMessage : message
        )))
        const nextId = typeof payload.session_id === "string" ? payload.session_id : null
        if (nextId) setActiveId(nextId)
        await refreshSessions()
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let streamedAnswer = ""

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split("\n\n")
        buffer = blocks.pop() ?? ""

        for (const block of blocks) {
          const event = parseSseBlock(block)
          if (!event || !event.data) continue
          const data = JSON.parse(event.data) as Record<string, unknown>

          if (event.event === "thinking") {
            setMessages(prev => prev.map(message => (
              message.id === placeholderId
                ? { ...message, thinking: String(data.thinking ?? "Thinking…") }
                : message
            )))
          }

          if (event.event === "answer_delta") {
            streamedAnswer += String(data.delta ?? "")
            setMessages(prev => prev.map(message => (
              message.id === placeholderId
                ? { ...message, answer: streamedAnswer.trimStart() }
                : message
            )))
          }

          if (event.event === "final") {
            const nextMessage = payloadToMessage(data, streamedAnswer)
            setMessages(prev => prev.map(message => (
              message.id === placeholderId ? nextMessage : message
            )))
            const nextId = typeof data.session_id === "string" ? data.session_id : null
            if (nextId) setActiveId(nextId)
            await refreshSessions()
          }

          if (event.event === "error") {
            setMessages(prev => prev.map(message => (
              message.id === placeholderId
                ? { ...message, answer: String(data.error ?? "Something went wrong."), thinking: undefined, loading: false }
                : message
            )))
          }
        }
      }
    } catch {
      setMessages(prev => prev.map(message => (
        message.id === placeholderId
          ? { ...message, answer: "GLens could not answer right now. Please retry.", thinking: undefined, loading: false }
          : message
      )))
    } finally {
      setLoading(false)
      setOpenerLoaded(true)
    }
  }, [activeId, authFetch, loading, pageContext, refreshSessions])

  const chatPane = (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
        background: "var(--surface)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "16px 18px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text)" }}>GLens</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Guard-aware chat grounded in your governance data</div>
        </div>
        {mode === "panel" && (
          <button
            type="button"
            onClick={() => router.push("/theguard/chat")}
            style={{
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              borderRadius: 10,
              padding: "8px 10px",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Open full page ↗
          </button>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "18px", display: "flex", flexDirection: "column", gap: 16 }}>
        {messages.map(message => (
          message.role === "user" ? (
            <UserBubble key={message.id} text={message.answer} />
          ) : (
            <AssistantBubble
              key={message.id}
              message={message}
              authFetch={authFetch}
              sessionId={activeId}
              onQuickReply={sendMessage}
              onOpenFullPage={() => router.push("/theguard/chat")}
            />
          )
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          void sendMessage(input)
        }}
        style={{
          borderTop: "1px solid var(--border)",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about Guard activity, compliance, spend, policies, or exports…"
          rows={3}
          style={{
            width: "100%",
            resize: "vertical",
            borderRadius: 12,
            border: "1px solid var(--border)",
            background: "var(--surface-2)",
            color: "var(--text)",
            padding: "12px 14px",
            fontSize: 14,
          }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Context: {pageContext}
          </div>
          <button
            type="submit"
            disabled={loading || !input.trim()}
            style={{
              padding: "10px 14px",
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: loading ? "var(--surface-2)" : "var(--accent)",
              color: loading ? "var(--text-muted)" : "white",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 600,
            }}
          >
            {loading ? "Working…" : "Send"}
          </button>
        </div>
      </form>
    </div>
  )

  if (mode === "panel") {
    return (
      <>
        {!panelOpen && (
          <button
            type="button"
            onClick={() => setPanelOpen(true)}
            style={{
              position: "fixed",
              right: 24,
              bottom: 24,
              zIndex: 40,
              borderRadius: 999,
              padding: "12px 16px",
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              color: "var(--text)",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            GLens
          </button>
        )}

        {panelOpen && (
          <div
            style={{
              position: "fixed",
              right: 16,
              bottom: 16,
              width: 440,
              maxWidth: "calc(100vw - 32px)",
              height: "min(760px, calc(100vh - 32px))",
              border: "1px solid var(--border)",
              borderRadius: 16,
              background: "var(--surface)",
              boxShadow: "0 24px 60px rgba(15, 23, 42, 0.24)",
              zIndex: 50,
              display: "grid",
              gridTemplateColumns: "160px 1fr",
              overflow: "hidden",
            }}
          >
            <div style={{ borderRight: "1px solid var(--border)", padding: 12, minHeight: 0 }}>
              <SessionList sessions={sessions} activeId={activeId} onSelect={loadSession} onNewChat={startNewChat} />
            </div>
            <div style={{ minWidth: 0, minHeight: 0, position: "relative" }}>
              <button
                type="button"
                onClick={() => setPanelOpen(false)}
                style={{
                  position: "absolute",
                  top: 12,
                  right: 12,
                  zIndex: 2,
                  borderRadius: 999,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                  padding: "4px 8px",
                  cursor: "pointer",
                }}
              >
                ×
              </button>
              {chatPane}
            </div>
          </div>
        )}
      </>
    )
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "280px minmax(0, 1fr)",
        gap: 16,
        minHeight: "calc(100vh - 140px)",
      }}
    >
      <div style={{ border: "1px solid var(--border)", borderRadius: 16, background: "var(--surface)", padding: 14, minHeight: 0 }}>
        <SessionList sessions={sessions} activeId={activeId} onSelect={loadSession} onNewChat={startNewChat} />
      </div>
      <div style={{ border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden", minHeight: 0 }}>
        {chatPane}
      </div>
    </div>
  )
}
