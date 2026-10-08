import { useCallback } from "react"
import Link from "next/link"
import { GuardList, useCursorList } from "@/components/guard/common"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

export interface SessionReport {
  id: string
  developer_email: string
  archetype: string | null
  autonomy_score: number | null
  sessions: number
  commits: number
  lines_per_hour: number | null
  created_at: string
  report_md: string | null
}

export function formatReportDate(ts: string) {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

const REPORT_HEADERS = ["Actor", "Archetype", "Sessions", "Commits", "Autonomy", "Lines/hr", "Date", "Report"]
const COLS = "1.8fr 1.2fr 0.6fr 0.6fr 0.7fr 0.6fr 0.9fr 0.5fr"

function ReportRow({ r, i }: { r: SessionReport; i: number }) {
  return (
          <div style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, padding: "11px 18px", borderTop: i > 0 ? "1px solid var(--border)" : "none", alignItems: "center" }}>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.developer_email}</div>
        <div>{r.archetype ? <span style={{ fontSize: 11, fontWeight: 500, color: "var(--accent-text)", background: "var(--accent-weak)", borderRadius: 6, padding: "2px 8px" }}>{r.archetype}</span> : <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>}</div>
        <div style={{ fontSize: 12.5 }}>{r.sessions}</div>
        <div style={{ fontSize: 12.5 }}>{r.commits}</div>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: r.autonomy_score != null ? (r.autonomy_score >= 70 ? "var(--ok)" : r.autonomy_score >= 40 ? "var(--warn)" : "var(--text-2)") : "var(--text-muted)" }}>
          {r.autonomy_score != null ? r.autonomy_score.toFixed(1) : "—"}
        </div>
        <div style={{ fontSize: 12.5 }}>{r.lines_per_hour != null ? Math.round(r.lines_per_hour) : <span style={{ color: "var(--text-muted)" }}>—</span>}</div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{formatReportDate(r.created_at)}</div>
        <div><Link href={`/theguard/session-reports/${r.id}`} style={{ fontSize: 12, color: "var(--accent-text)", textDecoration: "none", fontWeight: 500 }}>View →</Link></div>
      </div>
  )
}

export function SessionReportsView({ reports, reportsLoading, reportsError }: {
  reports: SessionReport[]
  reportsLoading: boolean
  reportsError: string | null
}) {
  return (
    reportsError ? (
      <div style={{ borderRadius: 8, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>
        {reportsError}
      </div>
    ) : reportsLoading ? (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {[...Array(4)].map((_, i) => <div key={i} style={{ height: 44, background: "var(--surface-2)", borderRadius: 8, opacity: 0.6 }} />)}
      </div>
    ) : reports.length === 0 ? (
      <div className="card" style={{ padding: "40px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
        No session reports yet. Developers run <code style={{ fontSize: 12 }}>conduct session-report</code> to push data here.
      </div>
    ) : (
      <div className="card" style={{ overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          {REPORT_HEADERS.map(h => (
            <div key={h} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
          ))}
        </div>
        {reports.map((r, i) => <ReportRow key={r.id} r={r} i={i} />)}
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
          {reports.length} {reports.length === 1 ? "report" : "reports"}
        </div>
      </div>
    )
  )
}

/** Self-paging session reports (50 per page, `before` cursor on created_at). */
export function SessionReportsList({ workspaceId }: { workspaceId: string | null }) {
  const { authFetch } = useAuthFetch()
  const fetchPage = useCallback((before?: string) => guard.sessionReports.list(authFetch, {
    workspace_id: workspaceId!, limit: "50", ...(before ? { before } : {}),
  }) as Promise<SessionReport[]>, [authFetch, workspaceId])
  const cursorOf = useCallback((r: SessionReport) => `${r.created_at}|${r.id}`, [])
  const list = useCursorList<SessionReport>(fetchPage, { cursorOf, enabled: !!workspaceId })
  if (list.error && list.rows.length === 0) {
    return <div style={{ borderRadius: 8, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>{list.error}</div>
  }
  return (
    <GuardList rows={list.rows} loading={list.loading} getKey={r => r.id} hasMore={list.hasMore}
      onLoadMore={list.loadMore} loadingMore={list.loadingMore} skeletonGap
      emptyState={
        <div className="card" style={{ padding: "40px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          No session reports yet. Developers run <code style={{ fontSize: 12 }}>conduct session-report</code> to push data here.
        </div>
      }
      wrap={rows => (
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
            {REPORT_HEADERS.map(h => <div key={h} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>)}
          </div>
          {rows}
        </div>
      )}
      renderRow={(r, i) => <ReportRow r={r} i={i} />} />
  )
}
