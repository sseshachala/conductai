"use client"

import { useEffect, useRef, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { GlensDashboard } from "@/components/glens/GlensDashboard"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"

// ─── Types ────────────────────────────────────────────────────────────────────

interface GLensSession {
  id: string
  title: string
  has_dashboard: boolean
  created_at: string
}

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; skill?: string }
  | { role: "assistant"; kind: "dashboard"; spec: GlensDashboardSpec; sessionId: string }
  | { role: "assistant"; kind: "loading" }

const SUGGESTIONS = [
  "Who was blocked today?",
  "Cost by AI tool this month",
  "How many events today?",
  "Show recent blocks",
  "Which rule triggered most?",
  "Tokens saved this month",
]

const SKILL_LABELS: Record<string, string> = {
  report:    "Report",
  analytics: "Analytics",
  extract:   "Extract",
  memory:    "Memory",
  session:   "Session",
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

function Sidebar({
  sessions,
  activeId,
  onSelect,
  onDelete,
  onNew,
}: {
  sessions: GLensSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onNew: () => void
}) {
  return (
    <div style={{
      width: 240,
      flexShrink: 0,
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      background: "var(--surface-2)",
      height: "100%",
    }}>
      <div style={{ padding: "16px 14px 12px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent-text)" }}>GLens</span>
        <button
          onClick={onNew}
          style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-2)", cursor: "pointer", fontWeight: 600 }}
        >
          + New
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "10px 8px" }}>
        {sessions.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", padding: "24px 8px" }}>
            No conversations yet
          </div>
        )}
        {sessions.map(s => (
          <div
            key={s.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              marginBottom: 3,
            }}
          >
            <button
              onClick={() => onSelect(s.id)}
              style={{
                flex: 1,
                textAlign: "left",
                padding: "8px 10px",
                borderRadius: 8,
                border: "1px solid " + (s.id === activeId ? "var(--accent)" : "transparent"),
                background: s.id === activeId ? "var(--accent-weak)" : "transparent",
                cursor: "pointer",
                fontSize: 12,
                color: s.id === activeId ? "var(--accent-text)" : "var(--text-2)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {s.title}
            </button>
            <button
              onClick={() => onDelete(s.id)}
              style={{ flexShrink: 0, padding: "4px 7px", borderRadius: 6, border: "none", background: "transparent", color: "var(--text-muted)", cursor: "pointer", fontSize: 13 }}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--text-muted)" }}>
        AI governance analytics
      </div>
    </div>
  )
}

// ─── Message bubbles ──────────────────────────────────────────────────────────

function UserBubble({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
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
    </div>
  )
}

function AnswerBubble({ text, skill }: { text: string; skill?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
      <div style={{ maxWidth: "75%" }}>
        {skill && (
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 4 }}>
            {SKILL_LABELS[skill] ?? skill}
          </div>
        )}
        <div style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: "4px 14px 14px 14px",
          padding: "10px 16px",
          fontSize: 14,
          color: "var(--text)",
          lineHeight: 1.6,
        }}>
          {text}
        </div>
      </div>
    </div>
  )
}

function LoadingBubble() {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
      <div style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "12px 16px",
        fontSize: 14,
        color: "var(--text-muted)",
      }}>
        <span style={{ letterSpacing: 3 }}>···</span>
      </div>
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

// ─── Input ────────────────────────────────────────────────────────────────────

function ChatInput({ onSubmit, disabled }: { onSubmit: (t: string) => void; disabled: boolean }) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { if (!disabled) ref.current?.focus() }, [disabled])

  function submit() {
    const t = value.trim()
    if (t && !disabled) { onSubmit(t); setValue("") }
  }

  return (
    <div style={{
      borderTop: "1px solid var(--border)",
      padding: "14px 20px",
      background: "var(--surface)",
      display: "flex",
      gap: 10,
      alignItems: "flex-end",
    }}>
      <textarea
        ref={ref}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }}
        disabled={disabled}
        placeholder="Ask about your governance data…"
        rows={2}
        style={{
          flex: 1,
          resize: "none",
          border: "1px solid var(--border)",
          borderRadius: 10,
          padding: "10px 14px",
          fontSize: 14,
          background: "var(--surface-2)",
          color: "var(--text)",
          outline: "none",
          fontFamily: "inherit",
          lineHeight: 1.5,
        }}
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        style={{
          padding: "10px 20px",
          borderRadius: 10,
          border: "none",
          background: disabled || !value.trim() ? "var(--surface-3)" : "var(--accent)",
          color: disabled || !value.trim() ? "var(--text-muted)" : "#fff",
          fontSize: 14,
          fontWeight: 600,
          cursor: disabled || !value.trim() ? "not-allowed" : "pointer",
          flexShrink: 0,
        }}
      >
        Send
      </button>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function GLensChatPage() {
  const { authFetch, workspaceId } = useAuthFetch()

  const [sessions, setSessions] = useState<GLensSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)

  const threadRef = useRef<HTMLDivElement>(null)
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  // Load session list
  useEffect(() => {
    if (!workspaceId) return
    authFetch(`${base}/glens/sessions`)
      .then(r => r.ok ? r.json() : [])
      .then(setSessions)
      .catch(() => {})
  }, [workspaceId, authFetch, base])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages])

  function startNew() {
    setActiveId(null)
    setMessages([])
  }

  async function selectSession(id: string) {
    setLoading(true)
    setActiveId(id)
    setMessages([])
    try {
      const res = await authFetch(`${base}/glens/sessions/${id}`)
      if (!res.ok) return
      const data = await res.json()
      const thread: Message[] = []
      for (const m of (data.messages ?? [])) {
        if (m.role === "user") {
          thread.push({ role: "user", text: m.content })
        } else {
          try {
            const p = JSON.parse(m.content)
            if (p.ready && p.spec) {
              thread.push({ role: "assistant", kind: "dashboard", spec: p.spec, sessionId: id })
            } else {
              const text = p.answer || p.question
              if (text) thread.push({ role: "assistant", kind: "answer", text, skill: p.skill })
            }
          } catch {
            thread.push({ role: "assistant", kind: "answer", text: m.content })
          }
        }
      }
      if (data.spec && !thread.find(m => m.role === "assistant" && (m as {kind:string}).kind === "dashboard")) {
        thread.push({ role: "assistant", kind: "dashboard", spec: data.spec, sessionId: id })
      }
      setMessages(thread)
    } finally {
      setLoading(false)
    }
  }

  async function deleteSession(id: string) {
    await authFetch(`${base}/glens/sessions/${id}`, { method: "DELETE" }).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== id))
    if (activeId === id) startNew()
  }

  async function sendMessage(text: string) {
    setMessages(prev => [...prev, { role: "user", text }, { role: "assistant", kind: "loading" }])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (activeId) body.session_id = activeId

      const res = await authFetch(`${base}/glens/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: `Request failed (${res.status}). Try again.` }])
        return
      }

      const data = await res.json()
      if (!activeId) {
        setActiveId(data.session_id)
        setSessions(prev => [{ id: data.session_id, title: text.slice(0, 60), has_dashboard: !!data.spec, created_at: new Date().toISOString() }, ...prev])
      }

      if (data.ready && data.spec) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "dashboard", spec: data.spec, sessionId: data.session_id }])
      } else {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: data.question ?? "No answer returned.", skill: data.skill }])
      }
    } catch {
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
        onNew={startNew}
      />

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--surface)" }}>

        {/* Thread */}
        <div
          ref={threadRef}
          style={{ flex: 1, overflowY: "auto", padding: "32px 48px" }}
        >
          {!hasThread && (
            <div style={{ maxWidth: 600, margin: "0 auto", paddingTop: 80 }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", marginBottom: 8 }}>
                What do you want to see?
              </div>
              <div style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 32 }}>
                Ask about blocks, spend, sessions, team memory — build any view on demand.
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    style={{
                      fontSize: 13, padding: "8px 14px", borderRadius: 20,
                      border: "1px solid var(--border)", background: "var(--surface-2)",
                      color: "var(--text-2)", cursor: "pointer",
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
              if (msg.role === "user") return <UserBubble key={i} text={msg.text} />
              if (msg.kind === "loading") return <LoadingBubble key={i} />
              if (msg.kind === "answer") return <AnswerBubble key={i} text={msg.text} skill={msg.skill} />
              if (msg.kind === "dashboard") return <DashboardBubble key={i} spec={msg.spec} sessionId={msg.sessionId} authFetch={authFetch} />
              return null
            })}
          </div>
        </div>

        {/* Input */}
        <ChatInput onSubmit={sendMessage} disabled={loading} />
      </div>
    </div>
  )
}
