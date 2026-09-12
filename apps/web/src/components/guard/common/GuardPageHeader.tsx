// Standard header for every Guard sub-page.
//
// Title on the left, optional "live" pill next to it, description
// below, last-updated stamp in the top-right. Pages currently roll
// their own headers — some have live pills, some have descriptions,
// most inconsistent spacing. This centralizes the pattern.
//
// Not meant to replace <GuardShell> (which owns the rail and the top
// "Guard · live" bar). This is the *inside* of a page — the section
// title + one-liner + right-aligned status.

import { timeAgo } from "./GuardTimeCount"

export function GuardPageHeader({
  title,
  description,
  live = false,
  lastUpdated,
  right,
}: {
  title: string
  description?: string
  live?: boolean
  lastUpdated?: Date | null
  right?: React.ReactNode
}) {
  return (
    <div style={{
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: 24,
      marginBottom: 16,
    }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h2 style={{
            fontSize: 18, fontWeight: 700, margin: 0, color: "var(--text)",
          }}>
            {title}
          </h2>
          {live && (
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              fontSize: 11, fontWeight: 600, padding: "2px 8px",
              borderRadius: 12, background: "var(--ok-bg)", color: "var(--ok)",
            }}>
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "var(--ok)",
              }} />
              live
            </span>
          )}
        </div>
        {description && (
          <div style={{
            fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5,
          }}>
            {description}
          </div>
        )}
      </div>
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap",
      }}>
        {lastUpdated && <span>last updated: {timeAgo(lastUpdated)}</span>}
        {right}
      </div>
    </div>
  )
}
