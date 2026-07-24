"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { useParams } from "next/navigation"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import Link from "next/link"
import StatusBadge from "@/components/runs/StatusBadge"
import { isActive, duration, timeAgo, effectiveStatus } from "@/lib/runUtils"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface Run {
  id: string
  status: string
  governance?: { blocked?: boolean } | null
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  max_turns: number | null
  trigger_summary: string | null
}

const PAGE_SIZE = 50

export default function RunsPage() {
  const { id: workflowId } = useParams<{ id: string }>()
  const { activeWorkspace } = useWorkspace()

  const [runs, setRuns] = useState<Run[]>([])
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { authFetch } = useAuthFetch()

  const fetchRuns = useCallback(async (currentOffset: number, append = false) => {
    try {
      const res = await authFetch(
        `${API}/workflows/${workflowId}/runs?limit=${PAGE_SIZE}&offset=${currentOffset}`
      )
      if (!res.ok) { setError(`Failed to load runs (${res.status})`); return }
      const data: Run[] = await res.json()
      setRuns(prev => append ? [...prev, ...data] : data)
      setHasMore(data.length === PAGE_SIZE)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs")
    }
  }, [authFetch, workflowId])

  // Initial load — workflow name + runs in parallel
  useEffect(() => {
    let cancelled = false
    async function init() {
      const [runsRes, wfRes] = await Promise.all([
        authFetch(`${API}/workflows/${workflowId}/runs?limit=${PAGE_SIZE}&offset=0`),
        authFetch(`${API}/workflows/${workflowId}`),
      ])
      if (cancelled) return
      if (runsRes.ok) {
        const data: Run[] = await runsRes.json()
        setRuns(data)
        setHasMore(data.length === PAGE_SIZE)
      } else {
        setError(`Failed to load runs (${runsRes.status})`)
      }
      if (wfRes.ok) {
        const wf = await wfRes.json()
        setWorkflowName(wf.name ?? null)
      }
      setLoading(false)
    }
    init()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  // Poll every 4s only while there are active runs and user hasn't paginated
  useEffect(() => {
    if (loading || offset > 0) return
    const hasActive = runs.some(r => isActive(r.status))
    if (!hasActive) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return
    }
    if (!pollRef.current) {
      pollRef.current = setInterval(() => fetchRuns(0, false), 4000)
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [runs, loading, offset, fetchRuns])

  async function loadMore() {
    const next = offset + PAGE_SIZE
    setOffset(next)
    setLoadingMore(true)
    await fetchRuns(next, true)
    setLoadingMore(false)
  }

  return (
    <div style={{ flex: 1, overflow: "auto" }}>
      <div style={{ maxWidth: 672, margin: "0 auto", padding: "40px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
          <h2 className="page-title">{workflowName ? `${workflowName} — Runs` : "Runs"}</h2>
          <Link href={`/workflows/${workflowId}`} className="btn btn-primary btn-sm">
            Edit workflow
          </Link>
        </div>

        {error && (
          <div style={{ marginBottom: 16, padding: "12px 16px", borderRadius: 8, background: "var(--err-bg)", border: "1px solid var(--err)", color: "var(--err)", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <span>{error}</span>
            <button onClick={() => fetchRuns(0, false)} style={{ fontSize: 12, fontWeight: 600, padding: "4px 12px", borderRadius: 6, border: "1px solid var(--err)", background: "transparent", color: "var(--err)", cursor: "pointer", flexShrink: 0 }}>
              Retry
            </button>
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[...Array(5)].map((_, i) => (
              <div key={i} style={{ borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)", padding: "16px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 64, height: 20, borderRadius: 6, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite" }} />
                  <div style={{ width: 180, height: 14, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite" }} />
                </div>
                <div style={{ display: "flex", gap: 16 }}>
                  <div style={{ width: 48, height: 12, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite" }} />
                  <div style={{ width: 56, height: 12, borderRadius: 4, background: "var(--surface-3)", animation: "pulse 1.4s ease-in-out infinite" }} />
                </div>
              </div>
            ))}
          </div>
        ) : runs.length === 0 && !error ? (
          <div style={{ borderRadius: 12, border: "1px dashed var(--border-2)", padding: "64px 32px", textAlign: "center" }}>
            <p style={{ color: "var(--text-3)", fontSize: 13 }}>No runs yet.</p>
            <Link href={`/workflows/${workflowId}`} style={{ marginTop: 16, display: "inline-block", fontSize: 13, fontWeight: 500, color: "var(--accent-text)", textDecoration: "none" }}>
              Open canvas to start a test run
            </Link>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {runs.map((run) => (
              <Link
                key={run.id}
                href={`/workflows/${workflowId}/runs/${run.id}`}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)", padding: "16px 20px", textDecoration: "none", transition: "box-shadow 0.15s, border-color 0.15s" }}
                className="run-row-link"
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                  <StatusBadge status={effectiveStatus(run)} />
                  {run.trigger_summary ? (
                    <span style={{ fontSize: 13, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {run.trigger_summary}
                    </span>
                  ) : (
                    <span className="mono" style={{ fontSize: 13, color: "var(--text-muted)" }}>{run.id.slice(0, 8)}…</span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  {run.max_turns != null && (
                    <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>est. {run.max_turns} turns</span>
                  )}
                  <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>
                    {duration(run.started_at, run.completed_at, run.status)}
                  </span>
                  <span title={new Date(run.created_at).toLocaleString()} style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {timeAgo(run.created_at)}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}

        {!loading && runs.length > 0 && (
          <p style={{ marginTop: 12, fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
            {`Showing ${runs.length} run${runs.length !== 1 ? "s" : ""}`}
          </p>
        )}

        {hasMore && !loading && (
          <div style={{ textAlign: "center", marginTop: 12 }}>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 13 }}
              onClick={loadMore}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
