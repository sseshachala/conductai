"use client"

import { useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import { useParams, usePathname } from "next/navigation"
import AppShell from "@/components/AppShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"

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

// ─── Guard Shell (matches all other guard pages) ──────────────────────────────

const GUARD_TABS = [
  { href: "/guard",                 label: "Overview"        },
  { href: "/guard/spend",           label: "Spend"           },
  { href: "/guard/policies",        label: "Policies"        },
  { href: "/guard/activity",        label: "Activity"        },
  { href: "/guard/session-reports", label: "Session Reports" },
  { href: "/guard/team-memory",     label: "Team Memory"     },
  { href: "/guard/settings",        label: "Settings"        },
]

function GuardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
              Guard
            </h1>
            <span className="sbadge ok" style={{ marginTop: 2 }}>
              <span className="conduct-pulse-dot" />
              live
            </span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
            MDM for AI coding tools — policies and spend limits enforced on every Claude Code, Codex, and Cursor call.
          </p>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
          last updated: just now
        </div>
      </div>
      <div className="guard-tab-nav">
        {GUARD_TABS.map(tab => {
          const isActive = tab.href === "/guard"
            ? pathname === "/guard"
            : pathname?.startsWith(tab.href)
          return (
            <Link key={tab.href} href={tab.href} className={`guard-tab${isActive ? " active" : ""}`}>
              {tab.label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(ts: string): string {
  try {
    return new Date(ts).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    })
  } catch {
    return ts
  }
}

function autonomyColor(score: number): string {
  if (score >= 70) return "var(--ok)"
  if (score >= 50) return "var(--warn)"
  return "var(--err)"
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SessionReportDetailPage() {
  return <AppShell><SessionReportDetailContent /></AppShell>
}

function SessionReportDetailContent() {
  const { getToken } = useAuth()
  const { id } = useParams<{ id: string }>()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()

  const [report, setReport] = useState<SessionReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  const wsId = activeWorkspace?.id ?? teamId ?? null
  const { role } = useGuardRole(teamId, wsId)

  useEffect(() => {
    if (!teamLoading && !wsId) {
      setLoading(false)
      return
    }
    if (!wsId) return

    async function load() {
      setLoading(true)
      setError(null)
      setNotFound(false)
      try {
        const token = await getToken()
        const base = process.env.NEXT_PUBLIC_API_URL ?? ""
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        const res = await fetch(`${base}/guard/session-reports/${id}?workspace_id=${wsId}`, { headers })
        if (res.status === 404) {
          setNotFound(true)
          return
        }
        if (!res.ok) throw new Error(`Failed to load session report (${res.status})`)
        const data: SessionReport = await res.json()
        setReport(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error")
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [getToken, wsId, teamLoading, id])

  const topTools: [string, number][] = report?.tools_json
    ? Object.entries(report.tools_json).sort((a, b) => b[1] - a[1]).slice(0, 12)
    : []

  return (
    <GuardShell>
      {/* Back link */}
      <div style={{ marginBottom: 16 }}>
        <Link
          href="/guard/session-reports"
          style={{ fontSize: 13, color: "var(--text-3)", textDecoration: "none" }}
        >
          ← Session Reports
        </Link>
      </div>

      {/* Admin gate */}
      {role !== "admin" ? (
        <div style={{ padding: "48px 24px", textAlign: "center" }}>
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
            }}>
              {error}
            </div>
          )}

          {/* Not found */}
          {notFound && (
            <div style={{ padding: "48px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
              Report not found.
            </div>
          )}

          {/* Loading skeletons */}
          {loading && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ height: 56, background: "var(--surface-2)", borderRadius: 12, opacity: 0.6 }} />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12 }}>
                {[...Array(4)].map((_, i) => (
                  <div key={i} style={{ height: 96, background: "var(--surface-2)", borderRadius: 12, opacity: 0.6 }} />
                ))}
              </div>
              <div style={{ height: 48, background: "var(--surface-2)", borderRadius: 12, opacity: 0.6 }} />
              <div style={{ height: 300, background: "var(--surface-2)", borderRadius: 12, opacity: 0.6 }} />
            </div>
          )}

          {/* Report content */}
          {!loading && !notFound && report && (
            <>
              {/* Page header */}
              <div style={{ marginBottom: 20 }}>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: "0 0 4px" }}>
                  Session Report
                </h2>
                <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  {report.developer_email} · {formatDate(report.created_at)}
                </div>
              </div>

              {/* Archetype banner */}
              {report.archetype && (
                <div style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  padding: "16px 20px",
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  marginBottom: 16,
                }}>
                  <span style={{
                    fontSize: 13,
                    fontWeight: 700,
                    background: "var(--accent-weak)",
                    color: "var(--accent-text)",
                    border: "1px solid var(--accent-bd, var(--accent-weak))",
                    borderRadius: 8,
                    padding: "6px 14px",
                    whiteSpace: "nowrap",
                  }}>
                    {report.archetype}
                  </span>
                  <span style={{ fontSize: 13, color: "var(--text-3)" }}>
                    Autonomy score {report.autonomy_score !== null ? report.autonomy_score.toFixed(1) : "—"}/100
                    {report.planning_ratio !== null && (
                      <> &nbsp;·&nbsp; Planning ratio {report.planning_ratio.toFixed(2)}</>
                    )}
                  </span>
                </div>
              )}

              {/* KPI grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12, marginBottom: 24 }}>
                {[
                  { label: "Sessions", value: report.sessions, unit: null, color: "var(--text)" },
                  { label: "Prompts", value: report.prompts, unit: null, color: "var(--text)" },
                  { label: "Commits", value: report.commits, unit: null, color: "var(--text)" },
                  {
                    label: "Autonomy",
                    value: report.autonomy_score !== null ? report.autonomy_score.toFixed(1) : "—",
                    unit: "/ 100",
                    color: report.autonomy_score !== null ? autonomyColor(report.autonomy_score) : "var(--text-muted)",
                  },
                ].map(card => (
                  <div key={card.label} style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    padding: "18px 20px",
                  }}>
                    <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 8 }}>
                      {card.label}
                    </div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: card.color, lineHeight: 1 }}>
                      {card.value}
                    </div>
                    {card.unit && (
                      <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>{card.unit}</div>
                    )}
                  </div>
                ))}
              </div>

              {/* Top Tools — tag pills */}
              {topTools.length > 0 && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 10 }}>
                    Top Tools
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {topTools.map(([tool]) => (
                      <span key={tool} style={{
                        display: "inline-block",
                        fontSize: 12,
                        fontWeight: 600,
                        background: "var(--surface-2)",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        padding: "4px 10px",
                        color: "var(--text-2)",
                      }}>
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Full report */}
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 10 }}>
                  Report
                </div>
                {report.report_md ? (
                  <div
                    style={{
                      background: "var(--surface)",
                      border: "1px solid var(--border)",
                      borderRadius: 12,
                      padding: "20px 24px",
                      fontSize: 13,
                      color: "var(--text-2)",
                      lineHeight: 1.7,
                    }}
                    dangerouslySetInnerHTML={{
                      __html: report.report_md
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/"/g, "&quot;")
                        .replace(/'/g, "&#39;")
                        .replace(/\n/g, "<br>"),
                    }}
                  />
                ) : (
                  <div style={{ padding: "24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                    No report text available.
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </GuardShell>
  )
}
