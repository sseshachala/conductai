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

interface PolicyMapping {
  field: string
  column: string
  description: string
}

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; skill?: string }
  | { role: "assistant"; kind: "dashboard"; spec: GlensDashboardSpec; sessionId: string }
  | { role: "assistant"; kind: "loading" }
  | { role: "assistant"; kind: "policy_confirm"; answer: string; action: string; draft: Record<string, unknown>; mapping: PolicyMapping[]; targetRuleId?: string; sessionId: string; skill: string }

const SUGGESTIONS = [
  "Who was blocked today?",
  "Cost by AI tool this month",
  "How many events today?",
  "Show recent blocks",
  "Which rule triggered most?",
  "Tokens saved this month",
]

const SKILL_LABELS: Record<string, string> = {
  report:       "Report",
  analytics:    "Analytics",
  extract:      "Extract",
  memory:       "Memory",
  session:      "Session",
  rules:        "Rules",
  guard_config: "Guard Config",
  spend_config: "Spend Config",
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

const SKILL_APPLY_URL: Record<string, string> = {
  rules:        "/glens/policy/apply",
  guard_config: "/glens/guard_config/apply",
  spend_config: "/glens/spend_config/apply",
}

function _applyBody(skill: string, action: string, draft: Record<string, unknown>, targetRuleId?: string) {
  if (skill === "rules") return { action, draft, target_rule_id: targetRuleId }
  if (skill === "guard_config") return { draft }
  if (skill === "spend_config") return draft   // SpendConfigApplyRequest fields are top-level
  return { action, draft }
}

function PolicyConfirmBubble({
  answer,
  action,
  skill,
  draft,
  mapping,
  targetRuleId,
  sessionId,
  authFetch,
  onResult,
}: {
  answer: string
  action: string
  skill: string
  draft: Record<string, unknown>
  mapping: PolicyMapping[]
  targetRuleId?: string
  sessionId: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  onResult: (text: string) => void
}) {
  const [status, setStatus] = useState<"pending" | "loading" | "done">("pending")
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  async function confirm() {
    setStatus("loading")
    const url = `${base}${SKILL_APPLY_URL[skill] ?? "/glens/policy/apply"}`
    try {
      const res = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_applyBody(skill, action, draft, targetRuleId)),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        onResult(`Failed to apply: ${err.detail ?? res.status}`)
      } else {
        const data = await res.json()
        const label = data.rule_id ? `"${data.rule_id}"` : data.scope ?? ""
        onResult(`${label} ${data.action} successfully.`.trim())
      }
    } catch {
      onResult("Network error. Please try again.")
    }
    setStatus("done")
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{ maxWidth: "80%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "16px 20px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>Policy</div>
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 16, lineHeight: 1.5 }}>{answer}</div>

        {/* Field → Column mapping table */}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 16 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Field</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Value</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Column</th>
              <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)", fontWeight: 600 }}>Description</th>
            </tr>
          </thead>
          <tbody>
            {mapping.map(m => (
              <tr key={m.field} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--accent-text)" }}>{m.field}</td>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text)" }}>{String(draft[m.field] ?? "—")}</td>
                <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text-2)", fontSize: 11 }}>{m.column}</td>
                <td style={{ padding: "6px 8px", color: "var(--text-muted)" }}>{m.description}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {status === "pending" && (
          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={confirm}
              style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              Confirm
            </button>
            <button
              onClick={() => onResult(`Policy ${action} cancelled.`)}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer" }}
            >
              Cancel
            </button>
          </div>
        )}
        {status === "loading" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Applying…</div>}
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
  const abortRef = useRef<AbortController | null>(null)
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
      try {
        if (data.spec && !thread.find(m => m.role === "assistant" && (m as {kind:string}).kind === "dashboard")) {
          thread.push({ role: "assistant", kind: "dashboard", spec: data.spec, sessionId: id })
        }
      } catch { /* malformed spec — skip dashboard bubble */ }
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
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, { role: "user", text }, { role: "assistant", kind: "loading" }])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (activeId) body.session_id = activeId

      const res = await authFetch(`${base}/glens/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
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

      if (data.confirm_required) {
        setMessages(prev => [...prev.slice(0, -1), {
          role: "assistant", kind: "policy_confirm",
          answer: data.answer ?? "Review the draft below:",
          action: data.action,
          draft: data.draft ?? {},
          mapping: data.mapping ?? [],
          targetRuleId: data.target_rule_id,
          sessionId: data.session_id,
          skill: data.skill ?? "rules",
        }])
      } else if (data.ready && data.spec) {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "dashboard", spec: data.spec, sessionId: data.session_id }])
      } else {
        setMessages(prev => [...prev.slice(0, -1), { role: "assistant", kind: "answer", text: data.question ?? "No answer returned.", skill: data.skill }])
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
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
              if (msg.kind === "policy_confirm") return (
                <PolicyConfirmBubble
                  key={i}
                  answer={msg.answer}
                  action={msg.action}
                  skill={msg.skill}
                  draft={msg.draft}
                  mapping={msg.mapping}
                  targetRuleId={msg.targetRuleId}
                  sessionId={msg.sessionId}
                  authFetch={authFetch}
                  onResult={text => setMessages(prev => [
                    ...prev.slice(0, i),
                    { role: "assistant", kind: "answer", text, skill: msg.skill },
                    ...prev.slice(i + 1),
                  ])}
                />
              )
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
