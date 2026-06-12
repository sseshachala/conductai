"use client"

import { useEffect, useRef, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import RunTrace from "@/components/runs/RunTrace"
import ConversationTrace from "@/components/runs/ConversationTrace"
import AppShell from "@/components/AppShell"
import { statusStyle, formatTrigger, duration, isTerminal, isActive } from "@/lib/runUtils"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface RunMeta {
  id: string
  status: string
  triggered_by: string | null
  trigger_summary: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string
  state?: Record<string, unknown> | null
  max_turns?: number | null
}

type Tab = "summary" | "trace" | "ai-trace" | "files" | "approvals" | "cost"

function Pill({ children, color = "stone" }: { children: React.ReactNode; color?: "stone"|"blue"|"amber"|"green"|"red" }) {
  const map: Record<string, { background: string; color: string }> = {
    stone: { background: "var(--surface-3)", color: "var(--text-2)" },
    blue:  { background: "var(--info-bg, #eff6ff)", color: "var(--info, #2563eb)" },
    amber: { background: "var(--warn-bg)", color: "var(--warn)" },
    green: { background: "var(--ok-bg)", color: "var(--ok)" },
    red:   { background: "var(--err-bg)", color: "var(--err)" },
  }
  return <span style={{ ...map[color], fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", padding: "2px 8px", borderRadius: 999 }}>{children}</span>
}

export default function RunDetailPage() {
  const { id: workflowId, run_id: runId } = useParams<{ id: string; run_id: string }>()
  const { getToken, isLoaded } = useAuth()

  const [run, setRun] = useState<RunMeta | null>(null)
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [projectName, setProjectName] = useState<string | null>(null)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [agentModel, setAgentModel] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>("summary")
  const [approvalDecision, setApprovalDecision] = useState<"approved" | "rejected" | null>(null)
  const [approvingRun, setApprovingRun] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function buildHeaders() {
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id")
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    if (workspaceId) headers["X-Workspace-Id"] = workspaceId
    return headers
  }

  async function fetchRun(headers: Record<string, string>) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
    if (res.ok) { const data = await res.json(); setRun(data); return data as RunMeta }
    setFetchError(res.status === 403 ? "Access denied — you may not be a member of this workspace." : res.status === 404 ? "Run not found." : `Error ${res.status} — could not load run.`)
    return null
  }

  async function refresh() {
    setRefreshing(true)
    await fetchRun(await buildHeaders())
    setRefreshing(false)
  }

  async function stopRun() {
    setStopping(true)
    try {
      const headers = await buildHeaders()
      headers["Content-Type"] = "application/json"
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}/cancel`, { method: "POST", headers })
      setRun(prev => prev ? { ...prev, status: "cancelled" } : prev)
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    } finally { setStopping(false) }
  }

  async function handleApproval(decision: "approved" | "rejected") {
    setApprovingRun(true)
    try {
      const headers = await buildHeaders()
      headers["Content-Type"] = "application/json"
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}/approve`,
        { method: "POST", headers, body: JSON.stringify({ decision }) }
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
      const headers = await buildHeaders()
      const [runData, wfRes] = await Promise.all([
        fetchRun(headers),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers }),
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
        pollRef.current = setInterval(async () => { await fetchRun(await buildHeaders()) }, 4000)
      }
    }
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId, isLoaded])

  if (loading) return <AppShell><div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 256 }}><p style={{ fontSize: 14, color: "var(--text-muted)" }}>Loading…</p></div></AppShell>
  if (!run) return <AppShell><div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 256 }}><p style={{ fontSize: 14, color: "var(--text-3)" }}>{fetchError ?? "Run not found."}</p></div></AppShell>

  const s = statusStyle(run.status)
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
    <AppShell>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 24px" }}>
        {/* Breadcrumb */}
        <nav style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)", marginBottom: 16 }}>
          <Link href="/projects" style={{ color: "var(--text-3)", textDecoration: "none" }}>Projects</Link>
          {projectId && projectName && (<><span>/</span><Link href={`/projects/${projectId}`} style={{ color: "var(--text-3)", textDecoration: "none", maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "inline-block" }}>{projectName}</Link></>)}
          <span>/</span>
          <Link href={`/workflows/${workflowId}`} style={{ color: "var(--text-3)", textDecoration: "none", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "inline-block" }}>{workflowName ?? workflowId.slice(0,8)}</Link>
          <span>/</span>
          <span className="mono" style={{ color: "var(--text-2)", fontSize: 11 }}>{run.id.slice(0,8)}…</span>
        </nav>

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

          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {isActive(run.status) && (
              <button onClick={stopRun} disabled={stopping} className="btn btn-ghost btn-sm" style={{ color: "var(--err)", borderColor: "var(--err-bd)" }}>
                {stopping ? "Stopping…" : "⏹ Stop"}
              </button>
            )}
            <button onClick={refresh} disabled={refreshing} className="btn btn-ghost btn-sm" title="Refresh">
              <svg style={{ width: 13, height: 13, display: "inline", marginRight: 4, animation: (refreshing || isActive(run.status)) ? "spin 1s linear infinite" : "none" }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {isActive(run.status) ? "Live" : "Refresh"}
            </button>
            <button
              onClick={() => { const b = new Blob([JSON.stringify(run,null,2)],{type:"application/json"}); const u=URL.createObjectURL(b); const a=document.createElement("a"); a.href=u; a.download=`run-${run.id.slice(0,8)}.json`; a.click(); URL.revokeObjectURL(u) }}
              className="btn btn-ghost btn-sm">
              ↓ Export
            </button>
          </div>
        </div>

        {/* StatRow metric bar */}
        <div className="card" style={{ display: "flex", padding: 0, overflow: "hidden", marginBottom: 22 }}>
          {([
            ["Duration",     duration(run.started_at, run.completed_at), false],
            ["Turns",        run.max_turns ? `— / ${run.max_turns} est.` : "—", false],
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
        <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 24, overflowX: "auto" }}>
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
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
            <div>
              {/* 2-col meta grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 40px", maxWidth: 720 }}>
                {([
                  ["Triggered by", formatTrigger(run.triggered_by), true],
                  ["Started",      run.started_at ? new Date(run.started_at).toLocaleString() : "—", false],
                  ["Completed",    run.completed_at ? new Date(run.completed_at).toLocaleString() : "—", false],
                  ["Version",      run.workflow_version_id?.slice(0, 8) ?? "—", true],
                  ["Project",      projectName ?? "—", false],
                  ["Repository",   ((t.repo ?? (triggerCtx as Record<string,unknown> | null | undefined)?.repo) as string | undefined) ?? "—", true],
                ] as [string, string, boolean][]).map(([label, value, mono]) => (
                  <div key={label} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
                    <div className={mono ? "mono" : ""} style={{ fontSize: 13.5, fontWeight: 550 }}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Approval notice */}
              {(run.status === "paused" || run.status === "waiting_approval" || run.status === "waiting") && (
                <div className="card" style={{ marginTop: 24, padding: "16px 18px", display: "flex", gap: 13, alignItems: "flex-start", maxWidth: 720 }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--warn-bg)", color: "var(--warn)" }}>
                    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <circle cx={12} cy={12} r={10} /><polyline points="12 6 12 12 16 14" />
                    </svg>
                  </span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 2 }}>Paused on approval</div>
                    <div style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.5 }}>This run is waiting on a human decision in the <b>Approvals</b> tab before it merges to main.</div>
                  </div>
                </div>
              )}

              {/* PR links */}
              {(issueNum || (prNum && prUrl)) && (
                <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {issueNum && <span className="chip">{`Issue #${issueNum}${issueTitle ? ` — ${issueTitle}` : ""}`}</span>}
                  {prNum && prUrl && <a href={prUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}>PR #{prNum} →</a>}
                </div>
              )}
            </div>
          )}

          {/* Trace (timeline) */}
          {activeTab === "trace" && (
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
            />
          )}

          {/* AI Trace */}
          {activeTab === "ai-trace" && (
            <ConversationTrace workflowId={workflowId} runId={runId} getToken={getToken} />
          )}

          {/* Files */}
          {activeTab === "files" && (() => {
            const state = (run.state ?? {}) as Record<string, unknown>
            const blocks = Object.entries(state).filter(([k]) => !k.startsWith("__") && !k.startsWith("_"))
            const allPrUrls: {url: string; num?: number; block: string}[] = []
            const allFiles: {file: string; block: string}[] = []
            let diffStat = ""
            for (const [blockId, val] of blocks) {
              const v = val as Record<string, unknown>
              if (v?.pr_url) allPrUrls.push({ url: v.pr_url as string, num: v.pr_number as number | undefined, block: blockId })
              if (Array.isArray(v?.files_changed)) {
                for (const f of v.files_changed as string[]) allFiles.push({ file: f, block: blockId })
              }
              if (v?.diff_stat && !diffStat) diffStat = v.diff_stat as string
            }
            if (prUrl && !allPrUrls.find(p => p.url === prUrl)) allPrUrls.push({ url: prUrl, num: prNum, block: "trigger" })

            if (allPrUrls.length === 0 && allFiles.length === 0 && !diffStat) return (
              <div style={{ textAlign: "center", padding: "48px 0" }}>
                <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>No file artifacts yet</p>
                <p style={{ fontSize: 13, color: "var(--text-muted)" }}>PRs opened and files changed will appear here once the run completes.</p>
              </div>
            )
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                {allPrUrls.length > 0 && (
                  <div>
                    <p className="eyebrow" style={{ marginBottom: 10 }}>Pull request</p>
                    {allPrUrls.map((pr, i) => (
                      <div key={i} className="card" style={{ padding: "15px 18px", display: "flex", alignItems: "center", gap: 12, marginBottom: i < allPrUrls.length - 1 ? 8 : 0 }}>
                        <span style={{ width: 32, height: 32, borderRadius: 8, background: "var(--text)", color: "var(--surface)", display: "grid", placeItems: "center", flexShrink: 0 }}>
                          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={18} cy={18} r={3}/><circle cx={6} cy={6} r={3}/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1={6} y1={9} x2={6} y2={21}/></svg>
                        </span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 650, fontSize: 14 }}>{pr.num ? `#${pr.num} · Pull Request` : "Pull Request"}</div>
                          <div className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>draft</div>
                        </div>
                        <a href={pr.url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm" style={{ color: "var(--accent-text)", borderColor: "var(--accent-ring, var(--border))", textDecoration: "none" }}>Open →</a>
                      </div>
                    ))}
                  </div>
                )}
                {allFiles.length > 0 && (
                  <div>
                    <p className="eyebrow" style={{ marginBottom: 10 }}>Diff summary</p>
                    <div className="card" style={{ overflow: "hidden" }}>
                      {allFiles.map(({ file }, i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 16px", borderBottom: i < allFiles.length - 1 ? "1px solid var(--border)" : "none" }}>
                          <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ color: "var(--text-muted)", flexShrink: 0 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                          <span className="mono" style={{ fontSize: 12.5, flex: 1 }}>{file}</span>
                        </div>
                      ))}
                      {diffStat && (
                        <div style={{ padding: "10px 16px", fontSize: 12, color: "var(--text-muted)", background: "var(--surface-2)" }}>{diffStat}</div>
                      )}
                    </div>
                  </div>
                )}
                {!allFiles.length && diffStat && (
                  <div>
                    <p className="eyebrow" style={{ marginBottom: 8 }}>Diff Summary</p>
                    <pre className="card mono" style={{ background: "var(--surface-3)", fontSize: 12, padding: "14px 16px", overflowX: "auto", whiteSpace: "pre-wrap", color: "var(--text-2)" }}>{diffStat}</pre>
                  </div>
                )}
              </div>
            )
          })()}

          {/* Approvals */}
          {activeTab === "approvals" && (
            <div>
              {run.status === "paused" && !approvalDecision ? (
                <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                  <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="chip bk-approval" style={{ height: 21, fontSize: 9.5, fontWeight: 800, letterSpacing: ".07em", textTransform: "uppercase" }}>Approval</span>
                    <span style={{ fontWeight: 650, fontSize: 14 }}>Awaiting review</span>
                  </div>
                  <div style={{ padding: 18 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 16 }}>
                      <span className="dot pulse" style={{ background: "var(--warn)" }} />
                      <span style={{ fontSize: 13.5, color: "var(--text-2)" }}>The run is paused and waiting for a human decision before it continues.</span>
                    </div>
                    {run.trigger_summary && (
                      <div className="card" style={{ padding: "12px 14px", background: "var(--surface-2)", marginBottom: 16 }}>
                        <div style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.5 }}>{run.trigger_summary}</div>
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 9 }}>
                      <button
                        className="btn btn-accent"
                        disabled={approvingRun}
                        onClick={() => handleApproval("approved")}
                        style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                      >
                        <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}><polyline points="20 6 9 17 4 12"/></svg>
                        Approve &amp; continue
                      </button>
                      <button
                        className="btn btn-ghost"
                        disabled={approvingRun}
                        onClick={() => handleApproval("rejected")}
                        style={{ color: "var(--err)", borderColor: "var(--err-bd)", display: "inline-flex", alignItems: "center", gap: 6 }}
                      >
                        <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ) : approvalDecision ? (
                <div className="card" style={{ padding: "16px 18px", display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, display: "grid", placeItems: "center", background: approvalDecision === "approved" ? "var(--ok-bg)" : "var(--err-bg)", color: approvalDecision === "approved" ? "var(--ok)" : "var(--err)" }}>
                    {approvalDecision === "approved"
                      ? <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}><polyline points="20 6 9 17 4 12"/></svg>
                      : <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>}
                  </span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13.5, textTransform: "capitalize" }}>{approvalDecision}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>just now</div>
                  </div>
                </div>
              ) : (() => {
                const state = run.state as Record<string, unknown> | null
                const approvals = Object.entries(state ?? {})
                  .filter(([k]) => k.startsWith("__approval_"))
                  .map(([k, v]) => ({ blockId: k.replace("__approval_", ""), decision: v as string }))
                return approvals.length > 0 ? (
                  <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    {approvals.map(({ blockId, decision }, i) => (
                      <div key={blockId} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
                        <span className="mono" style={{ fontSize: 12.5, color: "var(--text-2)" }}>{blockId}</span>
                        <span className={`sbadge ${decision === "approved" ? "ok" : "err"}`}>{decision}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ textAlign: "center", padding: "48px 0" }}>
                    <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No approval decisions recorded for this run.</p>
                  </div>
                )
              })()}
            </div>
          )}

          {/* Cost */}
          {activeTab === "cost" && (() => {
            const state = (run.state ?? {}) as Record<string, unknown>
            const blocks = Object.entries(state).filter(([k]) => !k.startsWith("__") && !k.startsWith("_"))
            let totalInput = 0, totalOutput = 0, totalCost = 0
            const rows: {block: string; input: number; output: number; cost: number; turns: number}[] = []
            for (const [blockId, val] of blocks) {
              const v = val as Record<string, unknown>
              const input  = (v?.input_tokens  as number) || 0
              const output = (v?.output_tokens as number) || 0
              const cost   = (v?.cost_usd      as number) || 0
              const turns  = (v?.turns         as number) || 0
              if (input || output || cost) {
                rows.push({ block: blockId, input, output, cost, turns })
                totalInput  += input
                totalOutput += output
                totalCost   += cost
              }
            }
            if (rows.length === 0) return (
              <div style={{ textAlign: "center", padding: "48px 0" }}>
                <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>No cost data yet</p>
                <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Token usage is recorded once the run completes.</p>
              </div>
            )
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                {/* Totals grid */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                  {[
                    { label: "Total cost",    value: `$${totalCost.toFixed(2)}`,         color: "var(--text)"     },
                    { label: "Input tokens",  value: totalInput.toLocaleString(),          color: "var(--info)" },
                    { label: "Output tokens", value: totalOutput.toLocaleString(),         color: "var(--accent-text)"  },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="card" style={{ padding: "14px 18px" }}>
                      <p className="eyebrow" style={{ marginBottom: 8 }}>{label}</p>
                      <p style={{ fontSize: 26, fontWeight: 700, color, letterSpacing: "-.01em" }}>{value}</p>
                    </div>
                  ))}
                </div>
                {/* Per-block breakdown */}
                <div>
                  <p className="eyebrow" style={{ marginBottom: 8 }}>Per block</p>
                  <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                    {/* Header row */}
                    <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 1fr 0.7fr 1fr", padding: "10px 16px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                      {["Block", "Input", "Output", "Turns", "Cost"].map((h, i) => (
                        <span key={h} className="eyebrow" style={{ textAlign: i ? "right" : "left" }}>{h}</span>
                      ))}
                    </div>
                    {rows.map((r, i) => (
                      <div key={r.block} style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 1fr 0.7fr 1fr", padding: "10px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
                        <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>{r.block}</span>
                        <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{r.input.toLocaleString()}</span>
                        <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{r.output.toLocaleString()}</span>
                        <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "right" }}>{r.turns}</span>
                        <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", textAlign: "right" }}>${r.cost.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                  <p style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 8 }}>Pricing: $3/1M input · $15/1M output (claude-sonnet-4-6)</p>
                </div>
              </div>
            )
          })()}
        </div>
      </div>
    </AppShell>
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
