"use client"

import Link from "next/link"
import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { formatDate, autonomyColor } from "@/lib/guardUtils"

// ─── Types ────────────────────────────────────────────────────────────────────

interface SessionReport {
  id: string
  developer_email: string
  archetype: string | null
  autonomy_score: number | null
  sessions: number
  prompts: number
  commits: number
  lines_per_hour: number | null
  tools_json: Record<string, number> | null
  created_at: string
  report_md: string | null
  planning_ratio: number | null
}


// ─── Main page ────────────────────────────────────────────────────────────────

export default function SessionReportsPage() {
  return <AppShell><SessionReportsContent /></AppShell>
}

function SessionReportsContent() {
  const { getToken } = useAuth()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()

  const [reports, setReports] = useState<SessionReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const wsId = activeWorkspace?.id ?? teamId ?? null
  const { role, loading: roleLoading } = useGuardRole(teamId, wsId)

  const load = useCallback(async () => {
    if (!wsId) return
    setLoading(true)
    setError(null)
    try {
      const token = await getToken()
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      const res = await fetch(`${base}/guard/session-reports?workspace_id=${wsId}`, { headers })
      if (!res.ok) throw new Error(`Failed to load session reports (${res.status})`)
      const data: SessionReport[] = await res.json()
      data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      setReports(data)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [getToken, wsId])

  useEffect(() => {
    if (!teamLoading && !wsId) {
      setLoading(false)
      return
    }
    if (!wsId) return
    load()
  }, [load, teamLoading, wsId])

  return (
    <GuardShell lastFetched={lastUpdated}>
      {/* Page sub-header */}
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 5 }}>Session Reports</div>
          <p style={{ margin: 0, fontSize: 13, color: "var(--text-3)" }}>
            Developer productivity trends from <code style={{ fontSize: 12 }}>conduct session-report</code> runs.
          </p>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
          Developers run <code style={{ fontSize: 11 }}>conduct session-report</code> to push data.
        </div>
      </div>

      {/* Admin gate */}
      {!roleLoading && role !== "admin" ? (
        <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
          <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)" }}>
            Session Reports are visible to workspace admins only.
          </p>
        </div>
      ) : (
        <>
          {/* Error */}
          {error && (
            <div style={{
              borderRadius: 8,
              border: "1px solid var(--err-bd)",
              background: "var(--err-bg)",
              padding: "10px 16px",
              fontSize: 13,
              color: "var(--err)",
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}>
              <span style={{ flex: 1 }}>{error}</span>
              <button
                onClick={load}
                style={{ fontSize: 12, fontWeight: 600, background: "var(--err)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 12px", cursor: "pointer", flexShrink: 0 }}
              >
                Retry
              </button>
            </div>
          )}

          {/* Loading skeletons */}
          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[...Array(6)].map((_, i) => (
                <div key={i} style={{ height: 44, background: "var(--surface-2)", borderRadius: 8, opacity: 0.6 }} />
              ))}
            </div>
          ) : reports.length === 0 ? (
            /* Empty state */
            <div className="card" style={{ padding: "40px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
              No session reports yet. Developers run <code style={{ fontSize: 12 }}>conduct session-report</code> to push data here.
            </div>
          ) : (
            /* Table */
            <div className="card" style={{ overflow: "hidden" }}>
              {/* Table header */}
              <div style={{
                display: "grid",
                gridTemplateColumns: "1.8fr 1.2fr 0.6fr 0.6fr 0.7fr 0.6fr 0.9fr 0.5fr",
                gap: 12,
                padding: "10px 18px",
                borderBottom: "1px solid var(--border)",
                background: "var(--surface-2)",
              }}>
                {["Developer", "Archetype", "Sessions", "Commits", "Autonomy", "Lines/hr", "Date", "Report"].map(h => (
                  <div key={h} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
                ))}
              </div>

              {/* Table rows */}
              {reports.map((report, i) => (
                <div
                  key={report.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1.8fr 1.2fr 0.6fr 0.6fr 0.7fr 0.6fr 0.9fr 0.5fr",
                    gap: 12,
                    padding: "11px 18px",
                    borderBottom: i < reports.length - 1 ? "1px solid var(--border)" : "none",
                    alignItems: "center",
                  }}
                >
                  {/* Developer */}
                  <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {report.developer_email}
                  </div>

                  {/* Archetype */}
                  <div>
                    {report.archetype ? (
                      <span style={{
                        fontSize: 11,
                        fontWeight: 500,
                        color: "var(--accent-text)",
                        background: "var(--accent-weak)",
                        borderRadius: 6,
                        padding: "2px 8px",
                      }}>
                        {report.archetype}
                      </span>
                    ) : (
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
                    )}
                  </div>

                  {/* Sessions */}
                  <div style={{ fontSize: 12.5, color: "var(--text)" }}>
                    {report.sessions}
                  </div>

                  {/* Commits */}
                  <div style={{ fontSize: 12.5, color: "var(--text)" }}>
                    {report.commits}
                  </div>

                  {/* Autonomy */}
                  <div>
                    {report.autonomy_score !== null ? (
                      <span style={{ fontSize: 12.5, fontWeight: 700, color: autonomyColor(report.autonomy_score) }}>
                        {report.autonomy_score.toFixed(1)}
                      </span>
                    ) : (
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
                    )}
                  </div>

                  {/* Lines/hr */}
                  <div style={{ fontSize: 12.5, color: "var(--text)" }}>
                    {report.lines_per_hour !== null ? Math.round(report.lines_per_hour) : <span style={{ color: "var(--text-muted)" }}>—</span>}
                  </div>

                  {/* Date */}
                  <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                    {formatDate(report.created_at)}
                  </div>

                  {/* Report link */}
                  <div>
                    <Link
                      href={`/guard/session-reports/${report.id}`}
                      style={{ fontSize: 12, color: "var(--accent-text)", textDecoration: "none", fontWeight: 500 }}
                      aria-label={`View session report for ${report.developer_email}`}
                    >
                      View →
                    </Link>
                  </div>
                </div>
              ))}

              <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
                {reports.length} {reports.length === 1 ? "report" : "reports"}
              </div>
            </div>
          )}
        </>
      )}
    </GuardShell>
  )
}
