"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { usePathname } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface GLensSession {
  id: string
  title: string
  has_dashboard: boolean
  created_at: string
}

interface GLensKpiTile {
  label: string
  value: string | number
}

interface GLensChart {
  label: string
}

interface GLensTable {
  label: string
  endpoint: string
  columns: string[]
}

interface GLensSpec {
  title: string
  kpis: GLensKpiTile[]
  charts: GLensChart[]
  table?: GLensTable
}

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

// ─── Hook: fetch with auth ─────────────────────────────────────────────────

function useAuthFetch() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()

  const authFetch = useCallback(
    async (url: string, options: RequestInit = {}): Promise<Response> => {
      const token = await getToken()
      const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> | undefined),
      }
      if (token) headers["Authorization"] = `Bearer ${token}`
      if (activeWorkspace?.id) headers["X-Workspace-ID"] = activeWorkspace.id
      return fetch(url, { ...options, headers })
    },
    [getToken, activeWorkspace],
  )

  return { authFetch, workspaceId: activeWorkspace?.id ?? null }
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
        onClick={() => { if (value.trim()) { onSubmit(value.trim()); setValue("") } }}
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

function KpiTile({ label, value }: GLensKpiTile) {
  return (
    <div
      style={{
        flex: "1 1 140px",
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-card)",
        padding: "14px 16px",
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text)" }}>
        {value}
      </div>
    </div>
  )
}

function ChartPlaceholder({ label }: { label: string }) {
  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px dashed var(--border-2)",
        borderRadius: "var(--r-card)",
        padding: "24px 16px",
        textAlign: "center",
        color: "var(--text-muted)",
        fontSize: 12,
      }}
    >
      <div style={{ fontSize: 28, marginBottom: 6 }}>📊</div>
      <div style={{ fontWeight: 600, color: "var(--text-3)", marginBottom: 2 }}>{label}</div>
      <div>chart</div>
    </div>
  )
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export function GLensPanel() {
  const pathname = usePathname()
  const { authFetch, workspaceId } = useAuthFetch()

  const [open, setOpen] = useState(false)
  const [panelState, setPanelState] = useState<PanelState>({ kind: "empty" })
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConvMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isGuardPage = pathname?.startsWith("/theguard")

  // ─── Cmd+K / Escape listener ──────────────────────────────────────────────

  useEffect(() => {
    if (!isGuardPage) return

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
  }, [isGuardPage])

  // ─── When panel opens, load session history ───────────────────────────────

  useEffect(() => {
    if (!open || !workspaceId) return
    loadSessions()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workspaceId])

  async function loadSessions() {
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await authFetch(`${base}/glens/sessions?workspace_id=${workspaceId}`)
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
    } catch {
      setPanelState({ kind: "empty" })
    }
  }

  async function restoreSession(id: string) {
    setLoading(true)
    setError(null)
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await authFetch(`${base}/glens/sessions/${id}?workspace_id=${workspaceId}`)
      if (!res.ok) {
        setError("Could not restore session.")
        setLoading(false)
        return
      }
      const data: GLensChatResponse = await res.json()
      setSessionId(data.session_id)
      applyResponse(data, [])
    } catch {
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
      if (workspaceId) body.workspace_id = workspaceId

      const res = await authFetch(`${base}/glens/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        setError(`Request failed (${res.status})`)
        setLoading(false)
        return
      }

      const data: GLensChatResponse = await res.json()
      setSessionId(data.session_id)
      applyResponse(data, newMessages)
    } catch {
      setError("Network error. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  async function applyResponse(data: GLensChatResponse, priorMessages: ConvMessage[]) {
    if (data.ready && data.spec) {
      // Fetch table rows if spec includes a table
      let tableRows: Record<string, unknown>[] = []
      if (data.spec.table?.endpoint && workspaceId) {
        try {
          const base = process.env.NEXT_PUBLIC_API_URL ?? ""
          const sep = data.spec.table.endpoint.includes("?") ? "&" : "?"
          const tableRes = await authFetch(
            `${base}${data.spec.table.endpoint}${sep}workspace_id=${workspaceId}&limit=5`,
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

  function handleExport() {
    // Export placeholder — Day 4
  }

  function handlePin() {
    // Pin placeholder — Day 4
  }

  if (!isGuardPage) return null

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
            <DashboardState
              spec={panelState.spec}
              tableRows={panelState.tableRows}
              onPin={handlePin}
              onExport={handleExport}
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

      {/* Cmd+K hint — shown when closed on guard pages */}
      {!open && (
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
  const [inputValue, setInputValue] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && inputValue.trim()) {
      onSend(inputValue.trim())
    }
  }

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
      <div style={{ display: "flex", gap: 8 }}>
        <input
          ref={inputRef}
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Or type your own question..."
          style={{
            flex: 1,
            fontSize: 13,
            padding: "9px 12px",
            borderRadius: "var(--r-btn)",
            border: "1px solid var(--border-2)",
            background: "var(--surface-2)",
            color: "var(--text)",
            outline: "none",
          }}
        />
        <button
          onClick={() => { if (inputValue.trim()) onSend(inputValue.trim()) }}
          disabled={!inputValue.trim()}
          style={{
            fontSize: 13,
            fontWeight: 600,
            padding: "9px 14px",
            borderRadius: "var(--r-btn)",
            border: "none",
            background: "var(--accent)",
            color: "#fff",
            cursor: inputValue.trim() ? "pointer" : "default",
            opacity: inputValue.trim() ? 1 : 0.5,
          }}
        >
          Go
        </button>
      </div>
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
          key={i}
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

function DashboardState({
  spec,
  tableRows,
  onPin,
  onExport,
}: {
  spec: GLensSpec
  tableRows: Record<string, unknown>[]
  onPin: () => void
  onExport: () => void
}) {
  return (
    <div>
      {/* Title + actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "var(--text)", flex: 1, margin: 0 }}>
          {spec.title}
        </h2>
        <button
          onClick={onPin}
          title="Pin to dashboard"
          style={{ fontSize: 14, background: "none", border: "1px solid var(--border)", borderRadius: "var(--r-btn)", padding: "4px 8px", cursor: "pointer", color: "var(--text-2)" }}
        >
          ↗
        </button>
        <button
          onClick={onExport}
          title="Export"
          style={{ fontSize: 14, background: "none", border: "1px solid var(--border)", borderRadius: "var(--r-btn)", padding: "4px 8px", cursor: "pointer", color: "var(--text-2)" }}
        >
          ⬇
        </button>
      </div>

      {/* KPI tiles */}
      {spec.kpis.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
          {spec.kpis.map((kpi, i) => (
            <KpiTile key={i} label={kpi.label} value={kpi.value} />
          ))}
        </div>
      )}

      {/* Charts */}
      {spec.charts.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
          {spec.charts.map((chart, i) => (
            <ChartPlaceholder key={i} label={chart.label} />
          ))}
        </div>
      )}

      {/* Table */}
      {spec.table && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 8 }}>
            {spec.table.label}
          </div>
          {tableRows.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {spec.table.columns.map(col => (
                      <th
                        key={col}
                        style={{
                          textAlign: "left",
                          padding: "6px 10px",
                          borderBottom: "1px solid var(--border)",
                          color: "var(--text-muted)",
                          fontWeight: 600,
                          textTransform: "uppercase",
                          fontSize: 10,
                          letterSpacing: ".04em",
                        }}
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((row, ri) => (
                    <tr key={ri} style={{ borderBottom: "1px solid var(--border)" }}>
                      {spec.table!.columns.map(col => (
                        <td
                          key={col}
                          style={{ padding: "8px 10px", color: "var(--text-2)", verticalAlign: "top" }}
                        >
                          {String(row[col] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "12px 0" }}>No data available.</div>
          )}
        </div>
      )}
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
            {sources.map((src, i) => (
              <li key={i} style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 4 }}>
                {src}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
