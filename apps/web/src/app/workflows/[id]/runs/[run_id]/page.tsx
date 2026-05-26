"use client"

import { useEffect, useRef, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import RunTrace from "@/components/runs/RunTrace"
import ConversationTrace from "@/components/runs/ConversationTrace"
import AppShell from "@/components/AppShell"
import { statusStyle, formatTrigger, timeAgo, duration, isTerminal, isActive } from "@/lib/runUtils"

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
  const map = { stone: "bg-stone-100 text-stone-600", blue: "bg-blue-50 text-blue-700", amber: "bg-amber-50 text-amber-700", green: "bg-green-50 text-green-700", red: "bg-red-50 text-red-600" }
  return <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${map[color]}`}>{children}</span>
}

export default function RunDetailPage() {
  const { id: workflowId, run_id: runId } = useParams<{ id: string; run_id: string }>()
  const { getToken, isLoaded } = useAuth()

  const [run, setRun] = useState<RunMeta | null>(null)
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [projectName, setProjectName] = useState<string | null>(null)
  const [agentModel, setAgentModel] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>("summary")
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

  if (loading) return <AppShell><div className="flex items-center justify-center h-64"><p className="text-stone-400 text-sm">Loading…</p></div></AppShell>
  if (!run) return <AppShell><div className="flex items-center justify-center h-64"><p className="text-stone-500">Run not found.</p></div></AppShell>

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

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-xs text-stone-400 mb-5">
          <Link href="/runs" className="hover:text-stone-600">Runs</Link>
          <span>/</span>
          <Link href={`/workflows/${workflowId}`} className="hover:text-stone-600">{workflowName ?? workflowId.slice(0,8)}</Link>
          <span>/</span>
          <span className="font-mono text-stone-500">{run.id.slice(0,8)}…</span>
        </div>

        {/* Header */}
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-semibold text-stone-900">{workflowName ?? "Run"}</h2>
              {projectName && <Pill>{projectName}</Pill>}
              {agentModel && (
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-purple-50 text-purple-600 border border-purple-100">
                  {agentModel.replace("claude-","").replace(/-\d{10,}$/,"")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-2 flex-wrap">
              <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${s.bg} ${s.text}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                {s.label}
              </span>
              <span className="text-xs text-stone-400">{formatTrigger(run.triggered_by)}</span>
              {run.trigger_summary && <span className="text-xs text-stone-500">{run.trigger_summary}</span>}
              {issueNum && <span className="text-xs text-stone-500 bg-stone-100 px-2 py-0.5 rounded">Issue #{issueNum}{issueTitle ? ` — ${issueTitle}` : ""}</span>}
              {prNum && prUrl && <a href={prUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-indigo-600 hover:underline font-medium">PR #{prNum} →</a>}
            </div>
            <p className="text-[11px] text-stone-400 mt-1.5 font-mono">{run.id}</p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isActive(run.status) && (
              <button onClick={stopRun} disabled={stopping}
                className="text-xs text-red-500 hover:text-red-700 border border-red-200 hover:border-red-300 bg-red-50 hover:bg-red-100 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40 font-medium">
                {stopping ? "Stopping…" : "⏹ Stop"}
              </button>
            )}
            <button onClick={refresh} disabled={refreshing} title="Refresh"
              className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40">
              <svg className={`w-3.5 h-3.5 inline-block mr-1 ${refreshing || isActive(run.status) ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {isActive(run.status) ? "Live" : "Refresh"}
            </button>
            <button
              onClick={() => { const b = new Blob([JSON.stringify(run,null,2)],{type:"application/json"}); const u=URL.createObjectURL(b); const a=document.createElement("a"); a.href=u; a.download=`run-${run.id.slice(0,8)}.json`; a.click(); URL.revokeObjectURL(u) }}
              className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 rounded-lg px-3 py-1.5 transition-colors">
              ↓ Export
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-stone-200 mb-4">
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-xs font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? "bg-white border border-b-white border-stone-200 text-stone-900 -mb-px"
                  : "text-stone-400 hover:text-stone-600"
              }`}>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-xl border border-stone-200 p-6">

          {/* Summary */}
          {activeTab === "summary" && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                {[
                  ["Status",    s.label],
                  ["Trigger",   formatTrigger(run.triggered_by)],
                  ["Started",   run.started_at ? timeAgo(run.started_at) : "—"],
                  ["Duration",  duration(run.started_at, run.completed_at)],
                  ["Max turns", run.max_turns?.toString() ?? "—"],
                  ["Run ID",    run.id.slice(0,8) + "…"],
                ].map(([label, value]) => (
                  <div key={label}>
                    <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-0.5">{label}</p>
                    <p className="text-sm text-stone-800 font-medium">{value}</p>
                  </div>
                ))}
              </div>
              {run.trigger_summary && (
                <div className="pt-4 border-t border-stone-100">
                  <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">Trigger context</p>
                  <p className="text-sm text-stone-700">{run.trigger_summary}</p>
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

          {/* AI Trace (conversation) */}
          {activeTab === "ai-trace" && (
            <ConversationTrace workflowId={workflowId} runId={runId} getToken={getToken} />
          )}

          {/* Files — stub */}
          {activeTab === "files" && (
            <div className="text-center py-12">
              <p className="text-stone-500 font-medium mb-1">Files & artifacts</p>
              <p className="text-stone-400 text-sm">PRs opened, files changed, and other outputs will appear here.</p>
              {prUrl && (
                <a href={prUrl} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 mt-4 text-sm text-indigo-600 hover:underline font-medium">
                  View PR {prNum ? `#${prNum}` : ""} →
                </a>
              )}
            </div>
          )}

          {/* Approvals */}
          {activeTab === "approvals" && (
            <div>
              {run.status === "paused" ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
                  <p className="font-semibold mb-1">Waiting for approval</p>
                  <p className="text-amber-700">This run is paused and waiting for a human decision before continuing.</p>
                </div>
              ) : (() => {
                const state = run.state as Record<string, unknown> | null
                const approvals = Object.entries(state ?? {})
                  .filter(([k]) => k.startsWith("__approval_"))
                  .map(([k, v]) => ({ blockId: k.replace("__approval_", ""), decision: v as string }))
                return approvals.length > 0 ? (
                  <div className="divide-y divide-stone-100">
                    {approvals.map(({ blockId, decision }) => (
                      <div key={blockId} className="flex items-center justify-between py-3">
                        <span className="text-sm text-stone-600 font-mono">{blockId}</span>
                        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${decision === "approved" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                          {decision}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <p className="text-stone-400 text-sm">No approval decisions recorded for this run.</p>
                  </div>
                )
              })()}
            </div>
          )}

          {/* Cost — stub */}
          {activeTab === "cost" && (
            <div className="text-center py-12">
              <p className="text-stone-500 font-medium mb-1">Cost & token usage</p>
              <p className="text-stone-400 text-sm">Per-run token tracking is coming soon.</p>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
