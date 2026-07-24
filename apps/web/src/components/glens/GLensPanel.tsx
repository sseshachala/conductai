"use client"
import { API } from "@/lib/api"

import { useEffect, useRef, useState, useCallback } from "react"
import { usePathname, useRouter } from "next/navigation"
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
  | { role: "assistant"; kind: "question"; text: string }
  | { role: "assistant"; kind: "dashboard"; spec: GlensDashboardSpec; sessionId: string }
  | { role: "assistant"; kind: "loading"; label?: string }

// ─── Suggestion chips ─────────────────────────────────────────────────────────

function getSuggestions(pathname: string): string[] {
  if (pathname?.includes("spend"))      return ["Who spent the most this month?", "Cost by AI tool this month"]
  if (pathname?.includes("policies"))   return ["Which rule blocked most today?", "Show recent warnings"]
  if (pathname?.includes("compliance")) return ["Recent audit events", "Who was blocked today?"]
  if (pathname?.includes("discovery"))  return ["Which agents are active?", "Show hook sessions today"]
  return ["Who was blocked today?", "Cost by AI tool this month", "How many events today?", "Show recent blocks"]
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function UserBubble({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
      <div style={{
        maxWidth: "80%",
        background: "var(--accent)",
        color: "#fff",
        borderRadius: "14px 14px 4px 14px",
        padding: "9px 14px",
        fontSize: 13,
        lineHeight: 1.5,
      }}>
        {text}
      </div>
    </div>
  )
}

function AssistantBubble({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
      <div style={{ maxWidth: "92%", width: "100%" }}>
        {children}
      </div>
    </div>
  )
}

function QuestionBubble({ text }: { text: string }) {
  return (
    <AssistantBubble>
      <div style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "9px 14px",
        fontSize: 13,
        color: "var(--text)",
        lineHeight: 1.5,
      }}>
        {text}
      </div>
    </AssistantBubble>
  )
}

function LoadingBubble({ label }: { label?: string }) {
  return (
    <AssistantBubble>
      <div style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "10px 14px",
        fontSize: 13,
        color: "var(--text-muted)",
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}>
        <span style={{ letterSpacing: 2 }}>···</span>
        {label && <span style={{ fontSize: 12, opacity: 0.8 }}>{label}</span>}
      </div>
    </AssistantBubble>
  )
}

function DashboardBubble({
  spec,
  sessionId,
  authFetch,
  onPin,
}: {
  spec: GlensDashboardSpec
  sessionId: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onPin: (sessionId: string) => void
}) {
  return (
    <AssistantBubble>
      <div style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "14px",
        width: "100%",
      }}>
        <GlensDashboard
          spec={spec}
          sessionId={sessionId}
          compact
          authFetch={authFetch}
          onPin={() => onPin(sessionId)}
        />
      </div>
    </AssistantBubble>
  )
}

function ChatInput({
  onSubmit,
  disabled,
  placeholder,
}: {
  onSubmit: (text: string) => void
  disabled: boolean
  placeholder?: string
}) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!disabled) ref.current?.focus()
  }, [disabled])

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      const trimmed = value.trim()
      if (trimmed && !disabled) {
        onSubmit(trimmed)
        setValue("")
      }
    }
  }

  return (
    <div style={{
      borderTop: "1px solid var(--border)",
      padding: "10px 12px",
      display: "flex",
      gap: 8,
      alignItems: "flex-end",
      background: "var(--surface)",
    }}>
      <textarea
        ref={ref}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKey}
        disabled={disabled}
        placeholder={placeholder ?? "Ask about your governance data…"}
        rows={1}
        style={{
          flex: 1,
          resize: "none",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "8px 10px",
          fontSize: 13,
          background: "var(--surface-2)",
          color: "var(--text)",
          outline: "none",
          fontFamily: "inherit",
          lineHeight: 1.4,
        }}
      />
      <button
        onClick={() => { const t = value.trim(); if (t && !disabled) { onSubmit(t); setValue("") } }}
        disabled={disabled || !value.trim()}
        style={{
          padding: "8px 14px",
          borderRadius: 8,
          border: "none",
          background: disabled || !value.trim() ? "var(--surface-3)" : "var(--accent)",
          color: disabled || !value.trim() ? "var(--text-muted)" : "#fff",
          fontSize: 13,
          fontWeight: 600,
          cursor: disabled || !value.trim() ? "not-allowed" : "pointer",
          flexShrink: 0,
        }}
      >
        ↵
      </button>
    </div>
  )
}

// ─── History list ─────────────────────────────────────────────────────────────

function HistoryList({
  sessions,
  onRestore,
  onDelete,
  onNew,
}: {
  sessions: GLensSession[]
  onRestore: (id: string) => void
  onDelete: (id: string) => void
  onNew: () => void
}) {
  if (sessions.length === 0) return null
  return (
    <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 8 }}>
        Recent
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {sessions.map(s => (
          <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button
              onClick={() => onRestore(s.id)}
              style={{
                flex: 1, textAlign: "left", padding: "7px 10px", borderRadius: 8,
                border: "1px solid var(--border)", background: "var(--surface-2)",
                cursor: "pointer", fontSize: 12, color: "var(--text-2)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                display: "flex", alignItems: "center", gap: 6,
              }}
            >
              {s.has_dashboard && <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 4, background: "var(--accent-weak)", color: "var(--accent-text)", flexShrink: 0 }}>chart</span>}
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</span>
            </button>
            <button
              onClick={() => onDelete(s.id)}
              title="Delete"
              style={{ flexShrink: 0, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer", fontSize: 13 }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export function GLensPanel() {
  const pathname = usePathname()
  const router = useRouter()
  const { authFetch, workspaceId } = useAuthFetch()

  const [open, setOpen] = useState(false)
  const [glensEnabled, setGlensEnabled] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<GLensSession[]>([])
  const [loading, setLoading] = useState(false)
  const [showHistory, setShowHistory] = useState(true)

  const abortRef = useRef<AbortController | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const isGuardPage = pathname?.startsWith("/theguard") && pathname !== "/theguard/chat"
  const SESSION_KEY = "glens_active_session"

  // ─── Install gate ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (!isGuardPage) return
    authFetch(`${API}/glens/status`)
      .then(r => r.ok ? r.json() : { installed: false })
      .then(d => setGlensEnabled(d.installed))
      .catch(() => setGlensEnabled(false))
  }, [isGuardPage, authFetch])

  // ─── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => () => { abortRef.current?.abort() }, [])

  // ─── Cmd+K ────────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!isGuardPage || !glensEnabled) return
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setOpen(p => !p) }
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [isGuardPage, glensEnabled])

  // ─── Load history + restore last session when panel opens ─────────────────

  useEffect(() => {
    if (!open || !workspaceId) return
    authFetch(`${API}/glens/sessions`)
      .then(r => r.ok ? r.json() : [])
      .then((list: GLensSession[]) => {
        setSessions(list)
        // Auto-restore last active session if no thread yet
        if (messages.length === 0) {
          const lastId = sessionStorage.getItem(SESSION_KEY)
          if (lastId && list.find(s => s.id === lastId)) {
            restoreSession(lastId)
          }
        }
      })
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workspaceId])

  // ─── Scroll thread to bottom on new messages ──────────────────────────────

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [messages])

  // ─── Actions ──────────────────────────────────────────────────────────────

  function startNew() {
    abortRef.current?.abort()
    setSessionId(null)
    setMessages([])
    setShowHistory(true)
    sessionStorage.removeItem(SESSION_KEY)
  }

  async function deleteSession(id: string) {
    await authFetch(`${API}/glens/sessions/${id}`, { method: "DELETE" }).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== id))
    if (sessionId === id) startNew()
  }

  async function restoreSession(id: string) {
    setLoading(true)
    setShowHistory(false)
    try {
      const res = await authFetch(`${API}/glens/sessions/${id}`)
      if (!res.ok) return
      const data = await res.json()
      setSessionId(data.id)

      const thread: Message[] = []
      for (const m of (data.messages ?? [])) {
        if (m.role === "user") {
          thread.push({ role: "user", text: m.content })
        } else {
          // Assistant messages are raw JSON — parse and show only the question text
          try {
            const parsed = JSON.parse(m.content)
            if (parsed.ready === false && parsed.question) {
              thread.push({ role: "assistant", kind: "question", text: parsed.question })
            }
            // ready:true messages are skipped — dashboard shown below
          } catch {
            // non-JSON fallback (shouldn't happen)
            thread.push({ role: "assistant", kind: "question", text: m.content })
          }
        }
      }

      if (data.spec) {
        thread.push({ role: "assistant", kind: "dashboard", spec: data.spec, sessionId: data.id })
      }

      setMessages(thread)
    } finally {
      setLoading(false)
    }
  }

  async function sendMessage(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setShowHistory(false)
    setMessages(prev => [...prev, { role: "user", text }, { role: "assistant", kind: "loading" }])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (sessionId) body.session_id = sessionId

      const res = await authFetch(`${API}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "question", text: `Request failed (${res.status}). Try again.` }])
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
          } else if (evt.type === "done") {
            if (evt.session_id) {
              setSessionId(evt.session_id as string)
              sessionStorage.setItem(SESSION_KEY, evt.session_id as string)
              setSessions(prev => {
                const exists = prev.find(s => s.id === evt.session_id)
                if (exists) return prev
                return [{ id: evt.session_id as string, title: text.slice(0, 60), has_dashboard: !!evt.spec, created_at: new Date().toISOString() }, ...prev]
              })
            }
            if (evt.ready && evt.spec) {
              setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "dashboard", spec: evt.spec as GlensDashboardSpec, sessionId: evt.session_id as string }])
            } else {
              setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "question", text: (evt.answer as string) ?? "Could you clarify what you're looking for?" }])
            }
          } else if (evt.type === "error") {
            setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "question", text: (evt.message as string) ?? "Something went wrong." }])
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "question", text: "Network error. Please try again." }])
    } finally {
      setLoading(false)
    }
  }

  function pinSession(sid: string) {
    router.push(`/theguard/glens/${sid}`)
    setOpen(false)
  }

  if (!isGuardPage || !glensEnabled) return null

  const suggestions = getSuggestions(pathname ?? "")
  const hasThread = messages.length > 0

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 998, background: "rgba(0,0,0,0.25)", backdropFilter: "blur(2px)" }}
        />
      )}

      {/* Panel */}
      {open && (
        <div style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: 440,
          zIndex: 999,
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "var(--shadow-xl)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}>

          {/* Header */}
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 16px 12px",
            borderBottom: "1px solid var(--border)",
            flexShrink: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: "var(--accent-text)" }}>GLens</span>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Guard analytics</span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={startNew}
                style={{ fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text-2)", cursor: "pointer" }}
              >
                New
              </button>
              <button
                onClick={() => setOpen(false)}
                style={{ fontSize: 16, padding: "4px 8px", borderRadius: 6, border: "none", background: "transparent", color: "var(--text-muted)", cursor: "pointer", lineHeight: 1 }}
              >
                ×
              </button>
            </div>
          </div>

          {/* History (collapsed when thread active) */}
          {showHistory && sessions.length > 0 && (
            <HistoryList
              sessions={sessions}
              onRestore={restoreSession}
              onDelete={deleteSession}
              onNew={startNew}
            />
          )}

          {/* Thread */}
          <div
            ref={threadRef}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px 14px 8px",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Empty state */}
            {!hasThread && (
              <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 12 }}>
                <div style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center", paddingBottom: 8 }}>
                  Ask anything about your governance data
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, justifyContent: "center" }}>
                  {suggestions.map(s => (
                    <button
                      key={s}
                      onClick={() => sendMessage(s)}
                      style={{
                        fontSize: 12, padding: "6px 12px", borderRadius: 20,
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

            {/* Messages */}
            {messages.map((msg, i) => {
              if (msg.role === "user") return <UserBubble key={i} text={msg.text} />
              if (msg.kind === "loading") return <LoadingBubble key={i} label={msg.label} />
              if (msg.kind === "question") return <QuestionBubble key={i} text={msg.text} />
              if (msg.kind === "dashboard") return (
                <DashboardBubble
                  key={i}
                  spec={msg.spec}
                  sessionId={msg.sessionId}
                  authFetch={authFetch}
                  onPin={pinSession}
                />
              )
              return null
            })}
          </div>

          {/* Input */}
          <ChatInput
            onSubmit={sendMessage}
            disabled={loading}
            placeholder={hasThread ? "Follow up…" : "Ask about your governance data…"}
          />
        </div>
      )}

      {/* Cmd+K hint */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          title="Open GLens (Cmd+K)"
          style={{
            position: "fixed", bottom: 24, right: 24, zIndex: 999,
            fontSize: 11, fontWeight: 700, padding: "7px 13px",
            borderRadius: "var(--r-btn)", border: "1px solid var(--border-2)",
            background: "var(--surface)", color: "var(--text-2)",
            cursor: "pointer", boxShadow: "var(--shadow)",
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <span style={{ color: "var(--accent-text)" }}>✦</span>
          GLens
          <kbd style={{ fontSize: 10, opacity: 0.6, fontFamily: "inherit" }}>⌘K</kbd>
        </button>
      )}
    </>
  )
}
