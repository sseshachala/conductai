"use client"
import { GlensDashboard } from "@/components/glens/GlensDashboard"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"

export function DashboardBubble({
  spec,
  sessionId,
  authFetch,
  drilldown,
}: {
  spec: GlensDashboardSpec
  sessionId: string
  authFetch: (url: string, options?: RequestInit) => Promise<Response>
  drilldown?: { path: string; filters?: Record<string, string> }
}) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{
        width: "100%",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "16px",
      }}>
        <GlensDashboard spec={spec} sessionId={sessionId} authFetch={authFetch} />
        {drilldown && (
          <div style={{ marginTop: 12, textAlign: "right" }}>
            <a
              href={drilldown.path}
              style={{ fontSize: 12, color: "var(--accent, #6366f1)", textDecoration: "none", fontWeight: 500 }}
            >
              View full &rarr;
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
