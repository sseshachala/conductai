"use client"

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

// GLensSpec maps to GlensDashboardSpec — alias for clarity inside this panel
type GLensSpec = GlensDashboardSpec

interface GLensChatResponse {
  session_id: string
  ready: boolean
  question?: string
  answer?: string
  sources?: string[]
  spec?: GLensSpec
}

type PanelState =
  | { kind: "history"; sessions: GLensSession[] }
  | { kind: "empty" }
  | { kind: "clarifying"; messages: ConvMessage[] }
  | { kind: "dashboard"; sessionId: string; spec: GLensSpec; tableRows: Record<string, unknown>[] }
  | { kind: "text_answer"; answer: string; sources?: string[] }

interface ConvMessage {
  role: "user" | "assistant"
  text: string
}

// ─── Suggestion chips per page ─────────────────────────────────────────────

function getSuggestions(pathname: string): string[] {
  if (pathname.startsWith("/theguard/spend")) {
    return [
      "Spend by model this month",
      "Top spending agents",
      "Daily spend trend",
    ]
  }
  if (pathname.startsWith("/theguard/discovery")) {
    return [
      "Show unsanctioned agents",
      "Agent activity summary",
      "New agents this week",
    ]
  }
  // /theguard and /theguard/activity
  return [
    "Show blocks this month",
    "Top violations by agent",
    "Blocks vs warnings trend",
  ]
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function PanelInput({
  placeholder,
  onSubmit,
  disabled,
}: {
  placeholder: string
  onSubmit: (value: string) => void
  disabled?: boolean
}) {
  const [value, setValue] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && value.trim()) {
      onSubmit(value.trim())
      setValue("")
    }
  }

  function handleSend() {
    if (value.trim()) {
      onSubmit(value.trim())
      setValue("")
    }
  }

  return (
    <div style={{ display: "flex", gap: 8, padding: "12px 16px", borderTop: "1px solid var(--border)" }}>
      <input
        ref={inputRef}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        style={{
          flex: 1,
          fontSize: 13,
          padding: "8px 12px",
          borderRadius: "var(--r-btn)",
          border: "1px solid var(--border-2)",
          background: "var(--surface-2)",
          color: "var(--text)",
          outline: "none",
        }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        style={{
          fontSize: 13,
          fontWeight: 600,
          padding: "8px 14px",
          borderRadius: "var(--r-btn)",
          border: "none",
          background: "var(--accent)",
          color: "#fff",
          cursor: disabled || !value.trim() ? "default" : "pointer",
          opacity: disabled || !value.trim() ? 0.5 : 1,
        }}
      >
        Send
      </button>
    </div>
  )
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export function GLensPanel() {
  const pathname = usePathname()
  const router = useRouter()
  const { authFetch, workspaceId } = useAuthFetch()

  const [open, setOpen] = useState(false)
  const [panelState, setPanelState] = useState<PanelState>({ kind: "empty" })
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConvMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [glensEnabled, setGlensEnabled] = useState(false)

  // Abort controller ref — cancels in-flight fetches on unmount or superseding request
  const abortRef = useRef<AbortController | null>(null)

  const isGuardPage = pathname?.startsWith("/theguard")

  // ─── Check GLens install status ───────────────────────────────────────────

  useEffect(() => {
    if (!isGuardPage) return
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    authFetch(`${base}/glens/status`)
      .then(r => r.ok ? r.json() : { installed: false })
      .then(d => setGlensEnabled(d.installed))
      .catch(() => setGlensEnabled(false))
  }, [isGuardPage, authFetch])

  // ─── Abort in-flight requests on unmount ──────────────────────────────────

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  // ─── Cmd+K / Escape listener ──────────────────────────────────────────────

  useEffect(() => {
    if (!isGuardPage || !glensEnabled) return

    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setOpen(prev => !prev)
      }
      if (e.key === "Escape") {
        setOpen(false)
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isGuardPage, glensEnabled])

  // ─── When panel opens, load session history ───────────────────────────────

  const loadSessions = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await authFetch(`${base}/glens/sessions`, { signal: controller.signal })
      if (!res.ok) {
        setPanelState({ kind: "empty" })
        return
      }
      const sessions: GLensSession[] = await res.json()
      if (sessions.length > 0) {
        setPanelState({ kind: "history", sessions })
      } else {
        setPanelState({ kind: "empty" })
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setPanelState({ kind: "empty" })
    }
  }, [authFetch])

  useEffect(() => {
    if (!open || !workspaceId) return
    loadSessions()
  }, [open, workspaceId, loadSessions])

  async function restoreSession(id: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await authFetch(`${base}/glens/sessions/${id}`, { signal: controller.signal })
      if (!res.ok) {
        setError("Could not restore session.")
        setLoading(false)
        return
      }
      const data = await res.json()
      setSessionId(data.id)
      const history: ConvMessage[] = (data.messages ?? []).map((m: { role: string; content: string }) => ({
        role: m.role as "user" | "assistant",
        text: m.content,
      }))
      setMessages(history)
      if (data.spec) {
        setPanelState({ kind: "dashboard", sessionId: data.id, spec: data.spec, tableRows: [] })
      } else {
        setPanelState({ kind: "clarifying", messages: history })
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setError("Network error restoring session.")
    } finally {
      setLoading(false)
    }
  }

  function startNewConversation() {
    setSessionId(null)
    setMessages([])
    setError(null)
    setPanelState({ kind: "empty" })
  }

  async function sendMessage(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const newMessages: ConvMessage[] = [...messages, { role: "user", text }]
    setMessages(newMessages)
    setLoading(true)
    setError(null)

    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const body: Record<string, unknown> = {
        message: text,
        page_context: pathname,
      }
      if (sessionId) body.session_id = sessionId

      const res = await authFetch(`${base}/glens/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        setError(`Request failed (${res.status})`)
        setLoading(false)
        return
      }

      const data: GLensChatResponse = await res.json()
      setSessionId(data.session_id)
      await applyResponse(data, newMessages, controller)
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setError("Network error. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  async function applyResponse(
    data: GLensChatResponse,
    priorMessages: ConvMessage[],
    controller: AbortController,
  ) {
    if (data.ready && data.spec) {
      // Fetch table rows if spec includes a table
      let tableRows: Record<string, unknown>[] = []
      if (data.spec.table?.endpoint) {
        try {
          const base = process.env.NEXT_PUBLIC_API_URL ?? ""
          const tableRes = await authFetch(
            `${base}${data.spec.table.endpoint}?limit=5`,
            { signal: controller.signal },
          )
          if (tableRes.ok) {
            const raw: unknown = await tableRes.json()
            if (Array.isArray(raw)) tableRows = raw as Record<string, unknown>[]
          }
        } catch {
          // table data is non-critical; continue without it
        }
      }
      setPanelState({ kind: "dashboard", sessionId: data.session_id, spec: data.spec, tableRows })
    } else if (!data.ready && data.question) {
      const updated: ConvMessage[] = [...priorMessages, { role: "assistant", text: data.question }]
      setMessages(updated)
      setPanelState({ kind: "clarifying", messages: updated })
    } else if (!data.ready && data.answer) {
      setPanelState({ kind: "text_answer", answer: data.answer, sources: data.sources })
    } else {
      // Fallback: show as clarifying with whatever came back
      const updated: ConvMessage[] = [...priorMessages, {
        role: "assistant",
        text: data.answer ?? data.question ?? "Could not process that request.",
      }]
      setMessages(updated)
      setPanelState({ kind: "clarifying", messages: updated })
    }
  }

  function handlePin() {
    if (panelState.kind === "dashboard") {
      router.push(`/theguard/glens/${panelState.sessionId}`)
      setOpen(false)
    }
  }

  if (!isGuardPage || !glensEnabled) return null

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.25)",
            zIndex: 1000,
          }}
        />
      )}

      {/* Slide-in panel */}
      <div
        role="dialog"
        aria-label="GLens analytics panel"
        aria-modal="true"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: 420,
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
          zIndex: 1001,
          display: "flex",
          flexDirection: "column",
          transform: open ? "translateX(0)" : "translateX(100%)",
          transition: "transform 0.22s cubic-bezier(.4,0,.2,1)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "14px 16px",
            borderBottom: "1px solid var(--border)",
            gap: 10,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent)", letterSpacing: "-.01em" }}>
            GLens
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)", flex: 1 }}>
            Guard analytics
          </span>
          {panelState.kind !== "empty" && panelState.kind !== "history" && (
            <button
              onClick={startNewConversation}
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: "4px 10px",
                borderRadius: "var(--r-btn)",
                border: "1px solid var(--border-2)",
                background: "transparent",
                color: "var(--text-2)",
                cursor: "pointer",
              }}
            >
              New
            </button>
          )}
          <button
            onClick={() => setOpen(false)}
            aria-label="Close GLens panel"
            style={{
              fontSize: 16,
              lineHeight: 1,
              padding: "4px 8px",
              borderRadius: "var(--r-btn)",
              border: "none",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
          {error && (
            <div
              style={{
                padding: "10px 14px",
                marginBottom: 12,
                background: "var(--err-bg)",
                border: "1px solid var(--err-bd)",
                borderRadius: "var(--r-card)",
                fontSize: 13,
                color: "var(--err)",
              }}
            >
              {error}
            </div>
          )}

          {loading && (
            <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "8px 0" }}>
              Thinking...
            </div>
          )}

          {!loading && panelState.kind === "history" && (
            <HistoryState
              sessions={panelState.sessions}
              onNew={startNewConversation}
              onRestore={restoreSession}
            />
          )}

          {!loading && panelState.kind === "empty" && (
            <EmptyState suggestions={getSuggestions(pathname ?? "")} onSend={sendMessage} />
          )}

          {!loading && panelState.kind === "clarifying" && (
            <ClarifyingState messages={panelState.messages} />
          )}

          {!loading && panelState.kind === "dashboard" && (
            <GlensDashboard
              spec={panelState.spec}
              sessionId={panelState.sessionId}
              tableRows={panelState.tableRows}
              compact={true}
              authFetch={authFetch}
              onPin={handlePin}
            />
          )}

          {!loading && panelState.kind === "text_answer" && (
            <TextAnswerState answer={panelState.answer} sources={panelState.sources} />
          )}
        </div>

        {/* Footer input — shown in clarifying, dashboard, text_answer states */}
        {(panelState.kind === "clarifying" ||
          panelState.kind === "dashboard" ||
          panelState.kind === "text_answer") && (
          <PanelInput
            placeholder="Follow-up question..."
            onSubmit={sendMessage}
            disabled={loading}
          />
        )}
      </div>

      {/* Cmd+K hint — shown when closed on guard pages and GLens is installed */}
      {!open && glensEnabled && (
        <button
          onClick={() => setOpen(true)}
          title="Open GLens (Cmd+K)"
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            zIndex: 999,
            fontSize: 11,
            fontWeight: 700,
            padding: "7px 13px",
            borderRadius: "var(--r-btn)",
            border: "1px solid var(--border-2)",
            background: "var(--surface)",
            color: "var(--text-2)",
            boxShadow: "var(--shadow-md)",
            cursor: "pointer",
            letterSpacing: ".02em",
          }}
        >
          GLens <kbd style={{ fontSize: 10, marginLeft: 4, opacity: 0.7 }}>⌘K</kbd>
        </button>
      )}
    </>
  )
}

// ─── State views ──────────────────────────────────────────────────────────────

function HistoryState({
  sessions,
  onNew,
  onRestore,
}: {
  sessions: GLensSession[]
  onNew: () => void
  onRestore: (id: string) => void
}) {
  return (
    <div>
      <button
        onClick={onNew}
        style={{
          width: "100%",
          fontSize: 13,
          fontWeight: 600,
          padding: "10px 14px",
          borderRadius: "var(--r-btn)",
          border: "1px solid var(--accent)",
          background: "var(--accent-weak)",
          color: "var(--accent-text)",
          cursor: "pointer",
          marginBottom: 16,
          textAlign: "left",
        }}
      >
        + New conversation
      </button>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 8 }}>
        Recent sessions
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {sessions.map(s => (
          <button
            key={s.id}
            onClick={() => onRestore(s.id)}
            style={{
              width: "100%",
              textAlign: "left",
              padding: "10px 12px",
              borderRadius: "var(--r-card)",
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span style={{ flex: 1, fontSize: 13, color: "var(--text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {s.title}
            </span>
            {s.has_dashboard && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4, background: "var(--accent-weak)", color: "var(--accent-text)", flexShrink: 0 }}>
                dashboard
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}

function EmptyState({
  suggestions,
  onSend,
}: {
  suggestions: string[]
  onSend: (text: string) => void
}) {
  return (
    <div>
      <h2 style={{ fontSize: 17, fontWeight: 700, color: "var(--text)", marginBottom: 6, marginTop: 8 }}>
        What do you want to see?
      </h2>
      <p style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 20 }}>
        Ask a question or pick a suggestion below.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
        {suggestions.map(s => (
          <button
            key={s}
            onClick={() => onSend(s)}
            className="chip"
            style={{ textAlign: "left", fontSize: 13, padding: "9px 14px" }}
          >
            {s}
          </button>
        ))}
      </div>
      <PanelInput placeholder="Or type your own question..." onSubmit={onSend} />
    </div>
  )
}

function ClarifyingState({ messages }: { messages: ConvMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {messages.map((m, i) => (
        <div
          key={`${m.role}-${i}`}
          style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "85%",
            padding: "10px 14px",
            borderRadius: "var(--r-card)",
            background: m.role === "user" ? "var(--accent)" : "var(--surface-2)",
            color: m.role === "user" ? "#fff" : "var(--text)",
            border: m.role === "user" ? "none" : "1px solid var(--border)",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          {m.text}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

function TextAnswerState({ answer, sources }: { answer: string; sources?: string[] }) {
  return (
    <div>
      <div
        style={{
          fontSize: 14,
          color: "var(--text)",
          lineHeight: 1.6,
          marginBottom: sources && sources.length > 0 ? 16 : 0,
        }}
      >
        {answer}
      </div>
      {sources && sources.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>
            Sources
          </div>
          <ul style={{ margin: 0, padding: "0 0 0 16px" }}>
            {sources.map((src) => (
              <li key={src} style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 4 }}>
                {src}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
