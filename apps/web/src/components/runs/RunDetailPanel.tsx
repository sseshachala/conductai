"use client"

import { Component, useEffect, useRef, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import RunTrace from "@/components/runs/RunTrace"
import ConversationTrace from "@/components/runs/ConversationTrace"
import { statusStyle, formatTrigger, duration, isTerminal, isActive, isAwaiting, effectiveStatus } from "@/lib/runUtils"
import RunSummaryTab from "@/components/runs/tabs/RunSummaryTab"
import RunFilesTab from "@/components/runs/tabs/RunFilesTab"
import RunApprovalsTab from "@/components/runs/tabs/RunApprovalsTab"
import RunCostTab from "@/components/runs/tabs/RunCostTab"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

// ── Tab error boundary ────────────────────────────────────────────────────────
class TabErrorBoundary extends Component<{ children: React.ReactNode }, { hasError: boolean }> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() { return { hasError: true } }
  componentDidCatch(error: Error) { console.error("[TabErrorBoundary]", error) }
  render() {
    if (this.state.hasError) {
      return (
        <p style={{ fontSize: 13, color: "var(--err)", padding: "32px 0", textAlign: "center" }}>
          Something went wrong rendering this tab — refresh.
        </p>
      )
    }
    return this.props.children
  }
}

export interface RunMeta {
  id: string
  status: string
  governance?: { blocked?: boolean } | null
  triggered_by: string | null
  trigger_summary: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string
  // Optional convenience field — /runs/{id} returns it (RunWithWorkflowOut),
  // /workflows/{wf}/runs/{id} does not. Used by ActionConfirmBubble (#1511)
  // to embed <RunDetailPanel> without a redundant workflow_id lookup.
  workflow_id?: string
  state?: Record<string, unknown> | null
  max_turns?: number | null
  actual_turns?: number | null
  repo?: string | null
}

type Tab = "summary" | "trace" | "ai-trace" | "files" | "approvals" | "cost"

export interface RunDetailPanelProps {
  workflowId: string
  runId: string
  /**
   * When true, hide the chrome that a full page would render:
   * breadcrumbs, Refresh/Export/Stop header buttons, and the outer maxWidth wrapper.
   * The parent (e.g. Lens RunBubble) supplies its own container.
   */
  embedded?: boolean
  /**
   * Seed the panel with a run record the caller already fetched (e.g. Lens
   * RunBubble hits /runs/{id} on mount). When provided, the panel skips its
   * initial fetch and renders immediately. Polling still runs for
   * non-terminal runs so any missing fields fill in on the next tick.
   */
  initialRun?: RunMeta
}

export default function RunDetailPanel({ workflowId, runId, embedded = false, initialRun }: RunDetailPanelProps) {
  const { getToken, isLoaded } = useAuth()
  const { authFetch } = useAuthFetch()

  const [run, setRun] = useState<RunMeta | null>(initialRun ?? null)
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [projectName, setProjectName] = useState<string | null>(null)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [agentModel, setAgentModel] = useState<string | null>(null)
  const [loading, setLoading] = useState(!initialRun)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>("summary")
  const [approvalDecision, setApprovalDecision] = useState<"approved" | "rejected" | null>(null)
  const [approvingRun, setApprovingRun] = useState(false)
  const [sseActive, setSseActive] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchRun() {
    try {
      const res = await authFetch(`${API}/workflows/${workflowId}/runs/${runId}`)
      if (res.ok) { const data = await res.json(); setRun(data); return data as RunMeta }
      setFetchError(res.status === 403 ? "Access denied — you may not be a member of this workspace." : res.status === 404 ? "Run not found." : `Error ${res.status} — could not load run.`)
      return null
    } catch {
      setFetchError("Could not reach the server — check your connection and refresh.")
      return null
    }
  }

  async function refresh() {
    setRefreshing(true)
    await fetchRun()
    setRefreshing(false)
  }

  async function stopRun() {
    setStopping(true)
    try {
      await authFetch(`${API}/workflows/${workflowId}/runs/${runId}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" } })
      setRun(prev => prev ? { ...prev, status: "cancelled" } : prev)
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    } finally { setStopping(false) }
  }

  async function handleApproval(decision: "approved" | "rejected") {
    setApprovingRun(true)
    try {
      await authFetch(
        `${API}/workflows/${workflowId}/runs/${runId}/approve`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) }
      )
      setApprovalDecision(decision)
      setRun(prev => prev ? { ...prev, status: decision === "approved" ? "running" : "cancelled" } : prev)
    } catch {
      // non-fatal — show decision optimistically
      setApprovalDecision(decision)
    } finally { setApprovingRun(false) }
  }

  useEffect(() => {
    if (run && isTerminal(run.status) && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null
    }
  }, [run?.status])

  useEffect(() => {
    if (!isLoaded) return
    async function load() {
      // #1508 follow-up — skip the initial fetchRun when the parent seeded us
      // with a run record; polling still starts below for non-terminal runs.
      const [runData, wfRes] = await Promise.all([
        initialRun ? Promise.resolve(initialRun) : fetchRun(),
        authFetch(`${API}/workflows/${workflowId}`),
      ])
      if (wfRes.ok) {
        const wf = await wfRes.json()
        setWorkflowName(wf.name ?? null)
        setProjectName(wf.project_name ?? null)
        setProjectId(wf.project_id ?? null)
        const nodes: {data?: {type?: string; model?: string}}[] = wf.graph?.nodes ?? []
        const brainNode = nodes.find(n => n.data?.type === "brain")
        if (brainNode?.data?.model) setAgentModel(brainNode.data.model)
      }
      setLoading(false)
      if (runData && !isTerminal(runData.status)) {
        pollRef.current = setInterval(async () => { await fetchRun() }, 4000)
      }
    }
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId, isLoaded])

  // ponytail: outer wrapper collapses to a bare fragment when embedded, so the
  // parent (Lens RunBubble, iframe host, etc.) controls the container.
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    embedded
      ? <>{children}</>
      : <div style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 24px" }}>{children}</div>

  if (loading) return (
    <Wrapper>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {[240, 180, 120].map(w => (
          <div key={w} style={{ height: 24, borderRadius: 8, background: "var(--surface-2)", width: `${w}px` }} />
        ))}
      </div>
    </Wrapper>
  )
  if (!run) return (
    <Wrapper>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 256 }}>
        <p style={{ fontSize: 14, color: "var(--text-3)" }}>{fetchError ?? "Run not found."}</p>
      </div>
    </Wrapper>
  )

  const s = statusStyle(effectiveStatus(run))
  const tabs: { id: Tab; label: string }[] = [
    { id: "summary",  label: "Summary"  },
    { id: "trace",    label: "Steps"    },
    { id: "ai-trace", label: "AI Trace" },
    { id: "files",    label: "Files"    },
    { id: "approvals",label: "Approvals"},
    { id: "cost",     label: "Cost"     },
  ]

  const triggerCtx = run.state as Record<string, unknown> | null | undefined
  const t = ((triggerCtx?._trigger ?? triggerCtx?.github_issue) ?? {}) as Record<string, unknown>
  const issueNum = t.issue_number as number | undefined
  const issueTitle = (t.title ?? t.issue_title) as string | undefined
  const prUrl = triggerCtx?.pr_url as string | undefined
  const prNum = (t.pull_request as Record<string,unknown>)?.number as number | undefined

  // Compute tokens and cost totals for StatRow (same logic as Cost tab)
  const statState = (run.state ?? {}) as Record<string, unknown>
  const statBlocks = Object.entries(statState).filter(([k]) => !k.startsWith("__") && !k.startsWith("_"))
  let statTotalTokens = 0, statTotalCost = 0
  for (const [, val] of statBlocks) {
    const v = val as Record<string, unknown>
    statTotalTokens += ((v?.input_tokens as number) || 0) + ((v?.output_tokens as number) || 0)
    statTotalCost   += (v?.cost_usd as number) || 0
  }
  const statTokensDisplay = statTotalTokens > 0 ? statTotalTokens.toLocaleString() : "—"
  const statCostDisplay   = statTotalCost   > 0 ? `$${statTotalCost.toFixed(2)}`   : "—"

  const sKey = statusKey(run.status)

  return (
    <Wrapper>
      {/* Breadcrumb — hidden when embedded (parent supplies its own context) */}
      {!embedded && (
        <nav style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)", marginBottom: 16 }}>
          <Link href="/projects" style={{ color: "var(--text-3)", textDecoration: "none" }}>Projects</Link>
          {projectId && projectName && (<><span>/</span><Link href={`/projects/${projectId}`} style={{ color: "var(--text-3)", textDecoration: "none", maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "inline-block" }}>{projectName}</Link></>)}
          <span>/</span>
          <Link href={`/workflows/${workflowId}`} style={{ color: "var(--text-3)", textDecoration: "none", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "inline-block" }}>{workflowName ?? workflowId.slice(0,8)}</Link>
          <span>/</span>
          <span className="mono" style={{ color: "var(--text-2)", fontSize: 11 }}>{run.id.slice(0,8)}…</span>
        </nav>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 22 }}>
        <div>
          {/* Line 1: title + project chip + status badge */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
            <h2 className="page-title" style={{ fontSize: 24, margin: 0 }}>{workflowName ?? "Run"}</h2>
            {projectName && <span className="chip" style={{ textTransform: "uppercase", letterSpacing: ".06em", fontSize: 10, height: 21 }}>{projectName}</span>}
            {agentModel && (
              <span className="chip" style={{ background: "var(--accent-weak)", color: "var(--accent-text)" }}>
                {agentModel.replace("claude-","").replace(/-\d{10,}$/,"")}
              </span>
            )}
            <span className={`sbadge ${sKey}`} style={{ height: 24, fontSize: 12.5 }}>
              {(sKey === "run" || sKey === "wait") && <span className="dot pulse" style={{ background: sKey === "wait" ? "var(--warn)" : "var(--info)" }} />}
              {s.label}
            </span>
          </div>
          {/* Line 2: issue chip + issue text / trigger */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "var(--text-3)" }}>
            {issueNum ? (
              <>
                <span className="chip bk-trigger" style={{ height: 20, fontSize: 10.5, flexShrink: 0 }}>Issue</span>
                <span>{issueTitle ? `${run.triggered_by?.split(":")[0] ?? ""}:${issueNum?.toString() ?? ""} — ${issueTitle}` : formatTrigger(run.triggered_by)}</span>
                {prNum && prUrl && <a href={prUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}>PR #{prNum} →</a>}
              </>
            ) : (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{run.trigger_summary ?? formatTrigger(run.triggered_by)}</span>
            )}
          </div>
          {/* Line 3: run UUID */}
          <p className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 7, margin: "7px 0 0" }}>{run.id}</p>
        </div>

        {/* Action buttons — hidden when embedded (parent surface owns actions) */}
        {!embedded && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {isActive(run.status) && !isAwaiting(run.status) && (
              <button onClick={stopRun} disabled={stopping} className="btn btn-ghost btn-sm" aria-label="Stop run" style={{ color: "var(--err)", borderColor: "var(--err-bd)" }}>
                {stopping ? "Stopping…" : "⏹ Stop"}
              </button>
            )}
            {/* Only show refresh button when SSE is not streaming — one live indicator is enough */}
            {!sseActive && (
              <button onClick={refresh} disabled={refreshing} className="btn btn-ghost btn-sm" aria-label="Refresh run" title="Refresh">
                <svg style={{ width: 13, height: 13, display: "inline", marginRight: 4, animation: refreshing ? "spin 1s linear infinite" : "none" }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </button>
            )}
            <button
              aria-label="Export run data"
              onClick={() => { const b = new Blob([JSON.stringify(run,null,2)],{type:"application/json"}); const u=URL.createObjectURL(b); const a=document.createElement("a"); a.href=u; a.download=`run-${run.id.slice(0,8)}.json`; a.click(); URL.revokeObjectURL(u) }}
              className="btn btn-ghost btn-sm">
              ↓ Export
            </button>
          </div>
        )}
      </div>

      {/* StatRow metric bar */}
      <div className="card" style={{ display: "flex", padding: 0, overflow: "hidden", marginBottom: 22 }}>
        {([
          ["Duration",     duration(run.started_at, run.completed_at), false],
          ["Turns",        run.actual_turns ? `${run.actual_turns}${run.max_turns ? ` / ${run.max_turns} est.` : ""}` : run.max_turns ? `— / ${run.max_turns} est.` : "—", false],
          ["Tokens",       statTokensDisplay, false],
          ["Est. cost",    statCostDisplay, false],
          ["Triggered by", formatTrigger(run.triggered_by), true],
        ] as [string, string, boolean][]).map(([label, value, mono], i, arr) => (
          <div key={label} style={{
            flex: i === arr.length - 1 ? 1.4 : 1,
            padding: "16px 20px",
            borderLeft: i ? "1px solid var(--border)" : "none",
          }}>
            <div className="eyebrow" style={{ marginBottom: 7 }}>{label}</div>
            <div style={{ fontSize: mono ? 14 : 18, fontWeight: 680, letterSpacing: "-.01em", fontFamily: mono ? "var(--font-mono, monospace)" : undefined, color: "var(--text)" }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="Run detail tabs"
        style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 24, overflowX: "auto" }}
        onKeyDown={(e) => {
          const idx = tabs.findIndex(t => t.id === activeTab)
          if (e.key === "ArrowRight") { e.preventDefault(); setActiveTab(tabs[(idx + 1) % tabs.length].id) }
          if (e.key === "ArrowLeft")  { e.preventDefault(); setActiveTab(tabs[(idx - 1 + tabs.length) % tabs.length].id) }
        }}
      >
        {tabs.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: "none",
              border: "none",
              padding: "9px 14px",
              fontSize: 13.5,
              fontWeight: activeTab === tab.id ? 600 : 500,
              whiteSpace: "nowrap",
              cursor: "pointer",
              marginBottom: -1,
              color: activeTab === tab.id ? "var(--text)" : "var(--text-3)",
              borderBottom: `2px solid ${activeTab === tab.id ? "var(--accent)" : "transparent"}`,
            }}>
            {tab.label}
          </button>
        ))}
      </div>

      <div>
        {/* Summary */}
        {activeTab === "summary" && (
          <TabErrorBoundary><RunSummaryTab run={run} projectName={projectName} /></TabErrorBoundary>
        )}

        {/* Trace (timeline) */}
        {activeTab === "trace" && (
          <TabErrorBoundary>
          <RunTrace
            workflowId={workflowId}
            runId={runId}
            initialStatus={run.status}
            initialMeta={{
              triggered_by: run.triggered_by,
              started_at: run.started_at,
              completed_at: run.completed_at,
              paused_at: run.paused_at,
              current_block_id: run.current_block_id,
              workflow_version_id: run.workflow_version_id ?? null,
            }}
            maxTurns={run.max_turns ?? null}
            getToken={getToken}
            onSseConnected={() => { setSseActive(true); if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }}
            onSseEnded={() => {
              setSseActive(false)
              if (!run || isTerminal(run.status)) return
              if (!pollRef.current) {
                pollRef.current = setInterval(async () => { await fetchRun() }, 4000)
              }
            }}
          />
          </TabErrorBoundary>
        )}

        {/* AI Trace */}
        {activeTab === "ai-trace" && (
          <TabErrorBoundary>
          <ConversationTrace workflowId={workflowId} runId={runId} getToken={getToken} />
          </TabErrorBoundary>
        )}

        {/* Files */}
        {activeTab === "files" && (
          <TabErrorBoundary><RunFilesTab run={run} /></TabErrorBoundary>
        )}

        {/* Approvals */}
        {activeTab === "approvals" && (
          <TabErrorBoundary>
            <RunApprovalsTab
              run={run}
              approvalDecision={approvalDecision}
              approvingRun={approvingRun}
              onApproval={handleApproval}
            />
          </TabErrorBoundary>
        )}

        {/* Cost */}
        {activeTab === "cost" && (
          <TabErrorBoundary><RunCostTab run={run} /></TabErrorBoundary>
        )}
      </div>
    </Wrapper>
  )
}

function statusKey(status: string): string {
  if (status === "running") return "run"
  if (status === "succeeded") return "ok"
  if (status === "failed") return "err"
  if (status === "paused") return "warn"
  if (status === "cancelled") return "idle"
  return "idle"
}
