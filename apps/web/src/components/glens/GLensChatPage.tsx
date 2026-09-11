"use client"
import { API } from "@/lib/api"

import { useEffect, useRef, useState } from "react"
import { useRouter, usePathname, useSearchParams } from "next/navigation"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useLensSessionStream, type LensSessionStream } from "@/hooks/useLensSessionStream"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"
import { GlensPageBubble } from "@/components/glens/GlensPageBubble"
import { GenericTableBubble } from "@/components/glens/GenericTableBubble"
import { BlocksBubble } from "@/components/glens/BlocksBubble"
import type { GLensSession, PolicyMapping, MessageBody, Message } from "@/components/glens/glensTypes"
import { withId, replaceLast, replaceById } from "@/components/glens/glensTypes"
import { DEFAULT_SUGGESTIONS, PAGE_SUGGESTIONS } from "@/components/glens/glensConstants"
import { Sidebar } from "@/components/glens/Sidebar"
import { ChatInput } from "@/components/glens/ChatInput"
import { MessageFooter } from "@/components/glens/MessageFooter"
import { UserBubble } from "@/components/glens/bubbles/UserBubble"
import { AnswerBubble } from "@/components/glens/bubbles/AnswerBubble"
import { LoadingBubble } from "@/components/glens/bubbles/LoadingBubble"
import { DashboardBubble } from "@/components/glens/bubbles/DashboardBubble"
import { PolicyConfirmBubble } from "@/components/glens/bubbles/PolicyConfirmBubble"
import { ActionConfirmBubble } from "@/components/glens/bubbles/ActionConfirmBubble"
import { RunBubble } from "@/components/glens/bubbles/RunBubble"


// ─── Main page ────────────────────────────────────────────────────────────────

export function GLensChatPage({ initialSessionId }: { initialSessionId?: string } = {}) {
  const { authFetch, workspaceId } = useAuthFetch()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const askedFromUrlRef = useRef<string | null>(null)

  // Auto-send when arriving with ?q=… from the global "Ask Lens" bar (#1333 #5).
  // Ref-guard so React Strict-mode double-mount doesn't fire twice, and clean
  // the query out of the URL after the send so refresh doesn't re-trigger.
  useEffect(() => {
    const q = searchParams?.get("q")
    if (!q) return
    if (askedFromUrlRef.current === q) return
    askedFromUrlRef.current = q
    void sendMessage(q)
    router.replace("/lens")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const [sessions, setSessions] = useState<GLensSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  // #1480 PR 4 — SSE session stream. Returns null when the feature flag
  // (NEXT_PUBLIC_LENS_SSE_SURFACE) is off or no active session yet; bubbles
  // that opt in via useLensEvent silently degrade to the existing REST flow.
  const lensStream = useLensSessionStream(activeId)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS)
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem("glens.sidebar.collapsed") === "1"
  })

  useEffect(() => {
    if (typeof window === "undefined") return
    window.localStorage.setItem("glens.sidebar.collapsed", sidebarCollapsed ? "1" : "0")
  }, [sidebarCollapsed])

  const threadRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load session list
  useEffect(() => {
    if (!workspaceId) return
    authFetch(`${API}/glens/sessions`)
      .then(r => r.ok ? r.json() : [])
      .then(setSessions)
      .catch(() => {})
  }, [workspaceId, authFetch])

  // Deep-link entry: if the page mounted with an initialSessionId (URL
  // /lens/{id}), load it once. selectSession updates the URL via
  // router.replace, which is a no-op when we already match — so no loop.
  const initialLoadedRef = useRef(false)
  useEffect(() => {
    if (initialSessionId && !initialLoadedRef.current && workspaceId) {
      initialLoadedRef.current = true
      selectSession(initialSessionId)
    }
    // selectSession is stable within the component closure; omitting from deps
    // avoids re-firing when Redis-driven state updates cascade.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId, workspaceId])

  // Load data-grounded opener chips — page-specific chips (#C2) win over
  // /glens/opener; opener wins over DEFAULT_SUGGESTIONS.
  useEffect(() => {
    const pageMatch = pathname ? PAGE_SUGGESTIONS.find(p => p.match.test(pathname)) : null
    if (pageMatch) {
      setSuggestions(pageMatch.chips)
      return
    }
    if (!workspaceId) return
    authFetch(`${API}/glens/opener`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.chips?.length) setSuggestions(d.chips) })
      .catch(() => {})
  }, [workspaceId, authFetch, pathname])

  // Scroll to bottom on new messages
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages])

  function startNew() {
    setActiveId(null)
    setMessages([])
    router.replace("/lens")
  }

  async function selectSession(id: string) {
    router.replace(`/lens/${id}`)
    setLoading(true)
    setActiveId(id)
    setMessages([])
    try {
      const res = await authFetch(`${API}/glens/sessions/${id}`)
      if (!res.ok) return
      const data = await res.json()
      const thread: MessageBody[] = []
      for (const m of (data.messages ?? [])) {
        if (m.role === "user") {
          thread.push({ role: "user", text: m.content })
        } else {
          try {
            const p = JSON.parse(m.content)
            const rendered = m.rendered ?? {}
            if (p.ready && p.spec) {
              thread.push({ role: "assistant", kind: "dashboard", spec: p.spec, sessionId: id })
            } else if (rendered.rows?.length) {
              thread.push({ role: "assistant", kind: "table", rows: rendered.rows, answer: p.answer ?? "", skill: p.skill ?? "governance", columns: p.columns })
            } else if (rendered.blocks?.length) {
              thread.push({ role: "assistant", kind: "blocks", blocks: rendered.blocks, answer: p.answer ?? "", skill: p.skill ?? "governance" })
            } else if (p.confirm_envelope?.approval_request_id) {
              // #1480 PR 12 — rehydrate ActionConfirmBubble from persisted envelope
              const ce = p.confirm_envelope
              thread.push({
                role: "assistant", kind: "action_confirm",
                toolName: ce.tool_name,
                approvalRequestId: ce.approval_request_id,
                summary: ce.summary ?? "Confirm this action?",
                warnings: ce.warnings ?? [],
                expiresAt: ce.expires_at,
              })
            } else if (p.run_started?.run_id) {
              // #1480 PR 12 — rehydrate RunBubble from persisted envelope
              const rs = p.run_started
              thread.push({
                role: "assistant", kind: "run",
                runId: rs.run_id,
                workflowName: rs.workflow_name ?? "workflow",
                initialStatus: rs.status ?? "pending",
              })
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
      setMessages(thread.map(withId))
    } finally {
      setLoading(false)
    }
  }

  async function deleteSession(id: string) {
    await authFetch(`${API}/glens/sessions/${id}`, { method: "DELETE" }).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== id))
    if (activeId === id) startNew()
  }

  async function renameSession(id: string, title: string) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, title } : s))
    await authFetch(`${API}/glens/sessions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).catch(() => {})
  }

  function _applyData(data: Record<string, unknown>, text: string) {
    if (!activeId && data.session_id) {
      setActiveId(data.session_id as string)
      setSessions(prev => [{ id: data.session_id as string, title: text.slice(0, 60), has_dashboard: !!data.spec, created_at: new Date().toISOString() }, ...prev])
    }
    if (data.clarification_required) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "answer",
        text: (data.answer as string) ?? "I need more detail to proceed.",
        skill: (data.skill as string) ?? "rules",
        followups: data.followups as string[] | undefined,
      }))
    } else if (data.run_started) {
      // Natural-language confirm path (#1480 PR 11): user typed "yes" and
      // the LLM called confirm_pending_action which returned a run_id.
      // Render <RunBubble> — same live surface the button-click path gets.
      const rs = data.run_started as { run_id: string; workflow_name: string; status: string }
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "run",
        runId: rs.run_id,
        workflowName: rs.workflow_name,
        initialStatus: rs.status ?? "pending",
      }))
    } else if (data.confirm_required && data.approval_request_id) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "action_confirm",
        toolName: data.tool_name as string,
        approvalRequestId: data.approval_request_id as string,
        summary: (data.summary as string) ?? "Confirm this action?",
        warnings: (data.warnings as string[] | undefined) ?? [],
        expiresAt: data.expires_at as string | undefined,
      }))
    } else if (data.confirm_required) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "policy_confirm",
        answer: (data.answer as string) ?? "Review the draft below:",
        action: data.action as string,
        draft: (data.draft as Record<string, unknown>) ?? {},
        mapping: (data.mapping as PolicyMapping[]) ?? [],
        targetRuleId: data.target_rule_id as string | undefined,
        sessionId: data.session_id as string,
        skill: (data.skill as string) ?? "rules",
        warning: data.warning as string | undefined,
      }))
    } else if (data.page_kind && data.page_data) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "page",
        answer: (data.answer as string) ?? "",
        pageKind: data.page_kind as string,
        pageData: data.page_data as Record<string, unknown>,
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
      }))
    } else if (data.blocks) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "blocks",
        answer: (data.answer as string) ?? "",
        blocks: data.blocks as unknown[],
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        understoodAs: data.query_understood_as as string | undefined,
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
      }))
    } else if (data.rows) {
      setMessages(prev => replaceLast(prev, {
        role: "assistant", kind: "table",
        answer: (data.answer as string) ?? "",
        columns: data.columns as unknown[] | undefined,
        rows: data.rows as unknown[],
        warning: data.warning as string | undefined,
        skill: (data.skill as string) ?? "report",
        drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined,
        understoodAs: data.query_understood_as as string | undefined,
      }))
    } else if (data.ready && data.spec) {
      setMessages(prev => replaceLast(prev, { role: "assistant", kind: "dashboard", spec: data.spec as GlensDashboardSpec, sessionId: data.session_id as string, drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined }))
    } else {
      setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: (data.answer as string) ?? "No answer returned.", skill: data.skill as string | undefined, drilldown: data.drilldown as { path: string; filters?: Record<string, string> } | undefined, followups: data.followups as string[] | undefined, understoodAs: data.query_understood_as as string | undefined }))
    }
  }

  async function sendMessage(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setMessages(prev => [...prev, withId({ role: "user", text }), withId({ role: "assistant", kind: "loading" })])
    setLoading(true)

    try {
      const body: Record<string, unknown> = { message: text }
      if (activeId) body.session_id = activeId
      if (pathname) body.page_context = pathname

      const res = await authFetch(`${API}/glens/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: `Request failed (${res.status}). Try again.` }))
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
                return replaceLast(prev, { ...last, label: evt.label as string })
              }
              return prev
            })
          } else if (evt.type === "token") {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last?.role === "assistant" && (last.kind === "loading" || last.kind === "streaming")) {
                const current = last.kind === "streaming" ? (last as { text: string }).text : ""
                return replaceLast(prev, { role: "assistant", kind: "streaming", text: current + (evt.text as string) })
              }
              return prev
            })
          } else if (evt.type === "done") {
            _applyData(evt, text)
          } else if (evt.type === "error") {
            setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: (evt.message as string) ?? "Something went wrong." }))
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return
      setMessages(prev => replaceLast(prev, { role: "assistant", kind: "answer", text: "Network error. Please try again." }))
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
        onRename={renameSession}
        onNew={startNew}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(v => !v)}
      />

      {/* Chat area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--surface)" }}>

        {/* Thread */}
        <div
          ref={threadRef}
          style={{ flex: 1, overflowY: "auto", padding: hasThread ? "32px 48px" : "0", display: hasThread ? "block" : "flex", flexDirection: "column", justifyContent: "center" }}
        >
          {!hasThread && (
            <div style={{ maxWidth: 680, width: "100%", margin: "0 auto", padding: "32px 24px" }}>
              <div style={{ textAlign: "center", marginBottom: 28 }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: "var(--text)", marginBottom: 8, letterSpacing: "-0.01em" }}>
                  What do you want to see?
                </div>
                <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
                  Ask about blocks, spend, sessions, team memory.
                </div>
              </div>
              <div style={{ marginBottom: 20 }}>
                <ChatInput onSubmit={sendMessage} disabled={loading} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8 }}>
                {suggestions.map(s => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    style={{
                      fontSize: 13,
                      padding: "12px 14px",
                      borderRadius: 10,
                      border: "1px solid var(--border)",
                      background: "var(--surface-2)",
                      color: "var(--text-2)",
                      cursor: "pointer",
                      textAlign: "left",
                      lineHeight: 1.4,
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ maxWidth: 800, margin: "0 auto" }}>
            {messages.map((msg) => {
              if (msg.role === "user") return (
                <UserBubble
                  key={msg.id}
                  text={msg.text}
                  onEdit={newText => {
                    const cutId = msg.id
                    setMessages(prev => {
                      const cutIdx = prev.findIndex(m => m.id === cutId)
                      return cutIdx >= 0 ? prev.slice(0, cutIdx) : prev
                    })
                    sendMessage(newText)
                  }}
                />
              )
              if (msg.kind === "loading") return <LoadingBubble key={msg.id} label={msg.label} />
              if (msg.kind === "streaming") return <AnswerBubble key={msg.id} text={msg.text} skill="governance" />
              const copyText =
                msg.kind === "answer" ? msg.text :
                msg.kind === "blocks" ? msg.answer :
                msg.kind === "table"  ? msg.answer :
                msg.kind === "page"   ? msg.answer :
                msg.kind === "policy_confirm" ? msg.answer :
                        msg.kind === "action_confirm" ? msg.summary :
                undefined
              return (
                <div key={msg.id}>
                  {msg.kind === "answer" && <AnswerBubble text={msg.text} skill={msg.skill} drilldown={msg.drilldown} followups={msg.followups} onFollowup={sendMessage} understoodAs={msg.understoodAs} />}
                  {msg.kind === "dashboard" && <DashboardBubble spec={msg.spec} sessionId={msg.sessionId} authFetch={authFetch} drilldown={msg.drilldown} />}
                  {msg.kind === "blocks" && <BlocksBubble answer={msg.answer} blocks={msg.blocks as any} warning={msg.warning} skill={msg.skill} understoodAs={msg.understoodAs} drilldown={msg.drilldown} />}
                  {msg.kind === "table" && <GenericTableBubble answer={msg.answer} columns={msg.columns as any} rows={msg.rows as any} warning={msg.warning} skill={msg.skill} drilldown={msg.drilldown} understoodAs={msg.understoodAs} />}
                  {msg.kind === "page" && <GlensPageBubble answer={msg.answer} pageKind={msg.pageKind as any} data={msg.pageData} warning={msg.warning} drilldown={msg.drilldown} />}
                  {msg.kind === "action_confirm" && (
                    <ActionConfirmBubble
                      toolName={msg.toolName}
                      approvalRequestId={msg.approvalRequestId}
                      summary={msg.summary}
                      warnings={msg.warnings}
                      expiresAt={msg.expiresAt}
                      authFetch={authFetch}
                      stream={lensStream}
                      onResult={text => setMessages(prev => replaceById(prev, msg.id, { role: "assistant", kind: "answer", text }))}
                      onRunStarted={lensStream ? (runId, wfName, initialStatus) => setMessages(prev => replaceById(prev, msg.id, { role: "assistant", kind: "run", runId, workflowName: wfName, initialStatus })) : undefined}
                      onRetry={(newRunId, wfName) => setMessages(prev => [
                        ...prev,
                        withId({ role: "assistant", kind: "run", runId: newRunId, workflowName: wfName, initialStatus: "pending" }),
                      ])}
                    />
                  )}
                  {msg.kind === "run" && (
                    <RunBubble
                      runId={msg.runId}
                      workflowName={msg.workflowName}
                      initialStatus={msg.initialStatus}
                      stream={lensStream}
                      authFetch={authFetch}
                      onRetry={(newRunId, wfName) => setMessages(prev => [
                        ...prev,
                        withId({ role: "assistant", kind: "run", runId: newRunId, workflowName: wfName, initialStatus: "pending" }),
                      ])}
                    />
                  )}
                  {msg.kind === "policy_confirm" && (
                    <PolicyConfirmBubble
                      answer={msg.answer}
                      action={msg.action}
                      skill={msg.skill}
                      draft={msg.draft}
                      mapping={msg.mapping}
                      targetRuleId={msg.targetRuleId}
                      sessionId={msg.sessionId}
                      authFetch={authFetch}
                      warning={msg.warning}
                      onResult={text => setMessages(prev => replaceById(prev, msg.id, { role: "assistant", kind: "answer", text, skill: msg.skill }))}
                    />
                  )}
                  <MessageFooter text={copyText} sessionId={activeId} messageId={msg.id} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Input — bottom-anchored once the thread has content */}
        {hasThread && (
          <div style={{ borderTop: "1px solid var(--border)", background: "var(--surface)", padding: "12px 48px 16px" }}>
            <div style={{ maxWidth: 800, margin: "0 auto" }}>
              <ChatInput onSubmit={sendMessage} disabled={loading} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
