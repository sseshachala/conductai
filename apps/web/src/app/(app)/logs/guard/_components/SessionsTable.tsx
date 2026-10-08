import { GuardSkeletonRows } from "@/components/guard/common"
import { ToolBadge, formatTs } from "@/components/guard/ActivityRow"

export const displayEmail = (v: string | null | undefined): string => {
  if (!v) return "—"
  // Strip synthetic prefixes from legacy rows
  if (v.startsWith("agt:")) v = v.slice(4).split("@")[0]
  if (v.startsWith("api:")) v = v.slice(4).split("@")[0]
  if (v.startsWith("user_")) return "unknown user"
  return v
}

export interface GuardSession {
  id: string
  user_email: string | null
  ai_tool: string
  started_at: string | null
  ended_at: string | null
  event_count: number
  violations_count: number
  total_cost_usd: number
  total_saved_usd: number
  client_ip: string | null
  os_info: string | null
  hostname: string | null
  intent: string | null
  session_parse_status: string | null
}

export function SessionsTable({ sessions, sessionsLoading }: { sessions: GuardSession[]; sessionsLoading: boolean }) {
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr 0.9fr 0.8fr 0.8fr 0.7fr 0.7fr 1.2fr 1.4fr",
        gap: 12, padding: "10px 18px",
        borderBottom: "1px solid var(--border)", background: "var(--surface-2)",
      }}>
        {["Actor", "Tool", "Started", "Events", "Violations", "Cost", "Saved", "Machine / IP", "OS"].map((h, i) => (
          <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
        ))}
      </div>
      {sessionsLoading ? (
        <GuardSkeletonRows count={4} />
      ) : sessions.length === 0 ? (
        <div style={{ padding: "32px 18px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          No sessions found.
        </div>
      ) : sessions.map((s, i) => (
        <div key={s.id} style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr 0.9fr 0.8fr 0.8fr 0.7fr 0.7fr 1.2fr 1.4fr",
          gap: 12, padding: "11px 18px", alignItems: "center",
          borderBottom: i < sessions.length - 1 ? "1px solid var(--border)" : "none",
        }}>
          <div style={{ overflow: "hidden" }}>
            <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{displayEmail(s.user_email)}</div>
            {s.intent && s.session_parse_status !== "failed" && (
              <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 2 }}>{s.intent}</div>
            )}
          </div>
          <div><ToolBadge tool={s.ai_tool} /></div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {s.started_at ? formatTs(s.started_at) : "—"}
          </div>
          <div style={{ fontSize: 12 }}>{s.event_count}</div>
          <div style={{ fontSize: 12, color: s.violations_count > 0 ? "var(--err)" : "var(--text-muted)", fontWeight: s.violations_count > 0 ? 600 : 400 }}>
            {s.violations_count}
          </div>
          <div className="mono" style={{ fontSize: 11.5 }}>${s.total_cost_usd.toFixed(4)}</div>
          <div className="mono" style={{ fontSize: 11.5, color: "var(--ok)" }}>${s.total_saved_usd.toFixed(4)}</div>
          <div style={{ fontSize: 11, color: "var(--text-3)" }}>
            <div className="mono" style={{ fontWeight: 600, color: "var(--text-2)" }}>{s.hostname ?? "—"}</div>
            <div style={{ marginTop: 2, color: "var(--text-muted)" }}>{s.client_ip ?? ""}</div>
          </div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {s.os_info ?? "—"}
          </div>
        </div>
      ))}
      {sessions.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
          {sessions.length} session{sessions.length !== 1 ? "s" : ""}
        </div>
      )}
      {sessions.length >= 100 && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", fontSize: 12, color: "var(--warn)", textAlign: "center" }}>
          Showing 100 sessions — older sessions may not be visible.
        </div>
      )}
    </div>
  )
}
