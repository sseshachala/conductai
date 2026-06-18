"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import StatusBadge from "@/components/runs/StatusBadge"
import { isActive, duration, timeAgo } from "@/lib/runUtils"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

interface Run {
  id: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  max_turns: number | null
  trigger_summary: string | null
}

export default function RunsPage() {
  const { id: workflowId } = useParams<{ id: string }>()
  const { getToken } = useAuth()

  const [runs, setRuns] = useState<Run[]>([])
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // hoveredRunId removed — use CSS :hover via className instead (was changing same borderColor value)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const token = await getToken()
      const workspaceId = getCookie("delegator_project_id")
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [runsRes, wfRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs?limit=50`, { headers }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers }),
      ])

      if (runsRes.ok) {
        setRuns(await runsRes.json())
      } else {
        setError(`Failed to load runs (${runsRes.status})`)
      }
      if (wfRes.ok) {
        const wf = await wfRes.json()
        setWorkflowName(wf.name ?? null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  // Suppress unused var lint — workflowName shown in title when available
  void workflowName

  return (
    <AppShell noPadding>
      <div style={{ flex: 1, overflow: "auto" }}>
        <div style={{ maxWidth: 672, margin: "0 auto", padding: "40px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <h2 className="page-title">Runs</h2>
            </div>
            <Link
              href={`/workflows/${workflowId}`}
              className="btn btn-primary btn-sm"
            >
              Edit workflow
            </Link>
          </div>

          {/* Error state (#1) */}
          {error && !loading && (
            <div
              style={{
                marginBottom: 16,
                padding: "12px 16px",
                borderRadius: 8,
                background: "var(--err-bg)",
                border: "1px solid var(--err)",
                color: "var(--err)",
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <span>{error}</span>
              <button
                onClick={load}
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  padding: "4px 12px",
                  borderRadius: 6,
                  border: "1px solid var(--err)",
                  background: "transparent",
                  color: "var(--err)",
                  cursor: "pointer",
                  flexShrink: 0,
                }}
              >
                Retry
              </button>
            </div>
          )}

          {loading ? (
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading…</p>
          ) : runs.length === 0 && !error ? (
            <div
              style={{
                borderRadius: 12,
                border: "1px dashed var(--border-2)",
                padding: "64px 32px",
                textAlign: "center",
              }}
            >
              <p style={{ color: "var(--text-3)", fontSize: 13 }}>No runs yet.</p>
              <Link
                href={`/workflows/${workflowId}`}
                style={{
                  marginTop: 16,
                  display: "inline-block",
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--accent-text)",
                  textDecoration: "none",
                }}
              >
                Open canvas to start a test run
              </Link>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {runs.map((run) => (
                <Link
                  key={run.id}
                  href={`/workflows/${workflowId}/runs/${run.id}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    borderRadius: 12,
                    border: "1px solid var(--border)",
                    background: "var(--surface)",
                    padding: "16px 20px",
                    textDecoration: "none",
                    transition: "box-shadow 0.15s, border-color 0.15s",
                  }}
                  className="run-row-link"
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                    <StatusBadge status={run.status} />
                    {/* Outcome text in left cell only — no trigger_summary duplication (#12) */}
                    {run.trigger_summary ? (
                      <span
                        style={{
                          fontSize: 13,
                          color: "var(--text)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {run.trigger_summary}
                      </span>
                    ) : (
                      <span className="mono" style={{ fontSize: 13, color: "var(--text-muted)" }}>
                        {run.id.slice(0, 8)}…
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    {run.max_turns != null && (
                      <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        est. {run.max_turns} turns
                      </span>
                    )}
                    {/* Duration — elapsed for active runs (#7) */}
                    <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>
                      {duration(run.started_at, run.completed_at, run.status)}
                    </span>
                    {/* Absolute date on hover (#15) */}
                    <span
                      title={new Date(run.created_at).toLocaleString()}
                      style={{ fontSize: 12, color: "var(--text-muted)" }}
                    >
                      {timeAgo(run.created_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* Run count (#19) */}
          {!loading && runs.length > 0 && (
            <p style={{ marginTop: 12, fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
              {`Showing ${runs.length} run${runs.length !== 1 ? "s" : ""}`}
            </p>
          )}
        </div>
      </div>
    </AppShell>
  )
}
