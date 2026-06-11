"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import { duration } from "@/lib/runUtils"

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

function statusBadgeClass(status: string): string {
  switch (status) {
    case "succeeded": return "sbadge ok"
    case "running":   return "sbadge run"
    case "failed":    return "sbadge err"
    case "cancelled": return "sbadge warn"
    default:          return "sbadge idle"
  }
}

export default function RunsPage() {
  const { id: workflowId } = useParams<{ id: string }>()
  const { getToken } = useAuth()

  const [runs, setRuns] = useState<Run[]>([])
  const [workflowName, setWorkflowName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [hoveredRunId, setHoveredRunId] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken()
        const workspaceId = getCookie("delegator_project_id")
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        if (workspaceId) headers["X-Workspace-Id"] = workspaceId

        const [runsRes, wfRes] = await Promise.all([
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs`, { headers }),
          fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers }),
        ])

        if (runsRes.ok) setRuns(await runsRes.json())
        if (wfRes.ok) {
          const wf = await wfRes.json()
          setWorkflowName(wf.name ?? null)
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

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
              Edit agent
            </Link>
          </div>

          {loading ? (
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading…</p>
          ) : runs.length === 0 ? (
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
                    boxShadow: hoveredRunId === run.id ? "0 1px 4px rgba(0,0,0,0.08)" : "none",
                    borderColor: hoveredRunId === run.id ? "var(--border)" : "var(--border)",
                  }}
                  onMouseEnter={() => setHoveredRunId(run.id)}
                  onMouseLeave={() => setHoveredRunId(null)}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                    <span className={statusBadgeClass(run.status)}>
                      {run.status}
                    </span>
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
                    {run.triggered_by && (
                      <span style={{ flexShrink: 0, fontSize: 12, color: "var(--text-muted)" }}>
                        {run.triggered_by}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    {run.max_turns != null && (
                      <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        est. {run.max_turns} turns
                      </span>
                    )}
                    <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>
                      {duration(run.started_at, run.completed_at)}
                    </span>
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {new Date(run.created_at).toLocaleString()}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
