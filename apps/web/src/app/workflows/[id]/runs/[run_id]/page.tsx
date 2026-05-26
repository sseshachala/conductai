"use client"

import { useEffect, useRef, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import RunTrace from "@/components/runs/RunTrace"
import ConversationTrace from "@/components/runs/ConversationTrace"
import AppShell from "@/components/AppShell"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface RunMeta {
  id: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string
  state?: Record<string, unknown> | null
  max_turns?: number | null
}

export default function RunDetailPage() {
  const { id: workflowId, run_id: runId } = useParams<{ id: string; run_id: string }>()
  const { getToken, isLoaded } = useAuth()

  const [run, setRun] = useState<RunMeta | null>(null)
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [agentModel, setAgentModel] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState<"timeline" | "trace">("timeline")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const TERMINAL = new Set(["succeeded", "failed", "cancelled"])

  async function fetchRun(headers: Record<string, string>) {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
    if (res.ok) {
      const data = await res.json()
      setRun(data)
      return data as RunMeta
    }
    return null
  }

  async function buildHeaders() {
    const token = await getToken()
    const workspaceId = getCookie("delegator_project_id")
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    if (workspaceId) headers["X-Workspace-Id"] = workspaceId
    return headers
  }

  async function refresh() {
    setRefreshing(true)
    const headers = await buildHeaders()
    await fetchRun(headers)
    setRefreshing(false)
  }

  // Stop polling as soon as run reaches a terminal state
  useEffect(() => {
    if (run && TERMINAL.has(run.status) && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
        const nodes: {data?: {type?: string; model?: string}}[] = wf.graph?.nodes ?? []
        const brainNode = nodes.find(n => n.data?.type === "brain")
        if (brainNode?.data?.model) setAgentModel(brainNode.data.model)
      }
      setLoading(false)

      if (runData && !TERMINAL.has(runData.status)) {
        pollRef.current = setInterval(async () => {
          const h = await buildHeaders()
          await fetchRun(h)
        }, 4000)
      }
    }
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId, isLoaded])

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <p className="text-stone-400 text-sm">Loading…</p>
        </div>
      </AppShell>
    )
  }

  if (!run) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <p className="text-stone-500">Run not found.</p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-xs text-stone-400 mb-5">
          <Link href="/runs" className="hover:text-stone-600">All runs</Link>
          <span>/</span>
          <Link href={`/workflows/${workflowId}`} className="hover:text-stone-600">
            {workflowName ?? workflowId.slice(0, 8)}
          </Link>
          <span>/</span>
          <span className="font-mono text-stone-500">{run.id.slice(0, 8)}…</span>
        </div>

        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-semibold text-stone-900">
                {workflowName ?? "Run trace"}
              </h2>
              {agentModel && (
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-purple-50 text-purple-600 border border-purple-100">
                  {agentModel.replace("claude-", "").replace(/-\d{10,}$/, "")}
                </span>
              )}
            </div>
            <p className="text-xs text-stone-400 mt-1 font-mono">{run.id}</p>
            {/* Trigger context */}
            {(() => {
              const trigger = (run.state as Record<string, unknown> | null | undefined)
              const t = (trigger?._trigger ?? trigger?.github_issue ?? {}) as Record<string, unknown>
              const issueNum = t.issue_number as number | undefined
              const issueTitle = (t.title ?? t.issue_title) as string | undefined
              const prUrl = (trigger?.pr_url) as string | undefined
              if (!issueNum && !prUrl) return null
              return (
                <div className="flex items-center gap-3 mt-2 flex-wrap">
                  {issueNum && (
                    <span className="text-xs text-stone-500 bg-stone-100 px-2 py-0.5 rounded">
                      Issue #{issueNum}{issueTitle ? ` — ${issueTitle}` : ""}
                    </span>
                  )}
                  {prUrl && (
                    <a href={prUrl} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-indigo-600 hover:underline font-medium">
                      View PR →
                    </a>
                  )}
                </div>
              )
            })()}
          </div>
          <div className="flex items-center gap-2 shrink-0">
          {/* Refresh button — always visible, spins while polling or manual refresh */}
          <button
            onClick={refresh}
            disabled={refreshing}
            title="Refresh"
            className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 hover:border-stone-300 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
          >
            <svg className={`w-3.5 h-3.5 inline-block mr-1 ${refreshing || (run && !TERMINAL.has(run.status)) ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {run && !TERMINAL.has(run.status) ? "Live" : "Refresh"}
          </button>
          {/* Export button */}
          <button
            onClick={() => {
              const blob = new Blob([JSON.stringify(run, null, 2)], { type: "application/json" })
              const url = URL.createObjectURL(blob)
              const a = document.createElement("a")
              a.href = url
              a.download = `run-${run.id.slice(0, 8)}.json`
              a.click()
              URL.revokeObjectURL(url)
            }}
            className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 hover:border-stone-300 rounded-lg px-3 py-1.5 transition-colors"
          >
            ↓ Export JSON
          </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 border-b border-stone-200 mb-4">
          {(["timeline", "trace"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-xs font-medium capitalize rounded-t-lg transition-colors ${
                activeTab === tab
                  ? "bg-white border border-b-white border-stone-200 text-stone-900 -mb-px"
                  : "text-stone-400 hover:text-stone-600"
              }`}
            >
              {tab === "trace" ? "AI Trace" : "Timeline"}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-xl border border-stone-200 p-6">
          {activeTab === "timeline" ? (
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
          ) : (
            <ConversationTrace
              workflowId={workflowId}
              runId={runId}
              getToken={getToken}
            />
          )}
        </div>
      </div>
    </AppShell>
  )
}
