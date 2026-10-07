"use client"

import type { RunEvent, FailureSummary } from "./types"

// ── Run terminal row ──────────────────────────────────────────────────────────

export function RunTerminalRow({ runFailed, runCompleted }: {
  runFailed?: RunEvent
  runCompleted?: RunEvent
}) {
  if (!runFailed && !runCompleted) return null

  const isReaped = runFailed?.payload?.reaped === true
  const errMsg   = typeof runFailed?.payload?.error === "string" ? runFailed.payload.error : ""
  const failure = (runFailed?.payload?.failure as FailureSummary | undefined) ?? undefined
  const reasonCode = typeof runFailed?.payload?.reason_code === "string" ? runFailed.payload.reason_code : failure?.code
  const nextAction = typeof runFailed?.payload?.next_action === "string" ? runFailed.payload.next_action : failure?.next_action

  if (runFailed) {
    if (isReaped) {
      return (
        <div style={{ display: "flex", gap: 14, position: "relative", paddingTop: 4 }}>
          <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
            <span style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid var(--warn, #d97706)", background: "var(--warn, #d97706)", display: "grid", placeItems: "center", boxShadow: "0 0 0 4px var(--bg, #fff)" }} />
          </div>
          <div className="card" style={{ flex: 1, padding: "12px 15px", background: "var(--warn-bg, #fffbeb)", border: "1px solid var(--warn-bd, #fde68a)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <p style={{ fontWeight: 600, color: "var(--warn, #d97706)", margin: 0, fontSize: 13.5 }}>
                <span aria-hidden="true" style={{ marginRight: 4 }}>⏱</span>
                Timed out
              </p>
              <span
                className="chip"
                style={{ height: 18, fontSize: 9, fontWeight: 800, letterSpacing: ".07em", padding: "0 6px", textTransform: "uppercase", background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }}
              >
                reaped
              </span>
            </div>
            {errMsg && (
              <p style={{ marginTop: 4, fontSize: 12.5, color: "var(--warn, #d97706)", lineHeight: 1.4 }}>{errMsg}</p>
            )}
          </div>
        </div>
      )
    }
    // Blocked and Failed both render red — distinguished by the headline + reason.
    // Warn = yellow, Audit = green elsewhere; this card is for terminal outcomes only.
    const isGuardBlock = reasonCode === "GUARD_POLICY_BLOCKED"
    const color  = "var(--err, #dc2626)"
    const bg     = "var(--err-bg, #fef2f2)"
    const border = "var(--err-bd, #fecaca)"
    const headline = isGuardBlock ? "Blocked by Guard" : "Run failed"
    return (
      <div style={{ display: "flex", gap: 14, position: "relative", paddingTop: 4 }}>
        <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
          <span style={{ width: 13, height: 13, borderRadius: "50%", border: `2px solid ${color}`, background: color, display: "grid", placeItems: "center", boxShadow: "0 0 0 4px var(--bg, #fff)" }} />
        </div>
        <div className="card" style={{ flex: 1, padding: "12px 15px", background: bg, border: `1px solid ${border}` }}>
          <p style={{ fontWeight: 600, color: color, margin: 0, fontSize: 13.5 }}>
            {headline}{errMsg ? ` — ${errMsg}` : ""}
          </p>
          {isGuardBlock && (
            <p style={{ marginTop: 4, fontSize: 12, color: "var(--text-3, #78716c)" }}>
              See <a href="/theguard/activity" style={{ color: color, textDecoration: "underline" }}>Guard activity</a> for the audit event.
            </p>
          )}
          {reasonCode && (
            <p className="mono" style={{ marginTop: 4, fontSize: 11, color: "var(--text-3, #78716c)" }}>
              Reason: {reasonCode}
            </p>
          )}
          {nextAction && (
            <p style={{ marginTop: 2, fontSize: 12.5, color: "var(--text-3, #78716c)", lineHeight: 1.4 }}>
              Next: {nextAction}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: "flex", gap: 14, position: "relative", paddingTop: 4 }}>
      <div style={{ flexShrink: 0, width: 22, display: "flex", justifyContent: "center", paddingTop: 13, zIndex: 2 }}>
        <span style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid var(--ok, #16a34a)", background: "var(--ok, #16a34a)", display: "grid", placeItems: "center", boxShadow: "0 0 0 4px var(--bg, #fff)" }} />
      </div>
      <div className="card" style={{ flex: 1, padding: "12px 15px", background: "var(--ok-bg, #f0fdf4)", border: "1px solid var(--ok-bd, #bbf7d0)" }}>
        <p style={{ fontWeight: 600, color: "var(--ok, #16a34a)", margin: 0, fontSize: 13.5 }}>Run completed successfully</p>
      </div>
    </div>
  )
}
