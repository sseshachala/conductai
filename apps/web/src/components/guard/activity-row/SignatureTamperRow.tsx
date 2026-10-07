"use client"

import { useState } from "react"
import { timeAgo } from "@/lib/runUtils"
import type { AuditEvent } from "./types"
import { ToolBadge, formatTs } from "./badges"

/** Row + inline drill-down for policy_signature_invalid events. */
export function SignatureTamperRow({ ev, isLast = false }: { ev: AuditEvent; isLast?: boolean }) {
  const [open, setOpen] = useState(false)

  let expected_signature = ""
  let computed_signature = ""
  let policy_version     = ""
  let hostname           = ev.hostname ?? ""
  try {
    const payload = JSON.parse(ev.input_summary ?? "{}")
    expected_signature = payload.expected_signature ?? ""
    computed_signature = payload.computed_signature ?? ""
    policy_version     = payload.policy_version ?? ""
    if (!hostname) hostname = payload.hostname ?? ""
  } catch { /* non-fatal */ }

  const cols = "0.8fr 1.4fr 1fr 1.2fr 1.8fr 0.9fr 0.8fr 0.9fr"

  return (
    <>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: "grid",
          gridTemplateColumns: cols,
          gap: 12,
          padding: "11px 18px",
          borderBottom: isLast && !open ? "none" : "1px solid var(--border)",
          alignItems: "center",
          background: "var(--err-bg)",
          cursor: "pointer",
        }}
        title="Click to see signature details"
      >
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }} title={formatTs(ev.ts)}>{timeAgo(ev.ts)}</div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {ev.user_email ?? "—"}
        </div>
        <div><ToolBadge tool={ev.ai_tool} /></div>
        <div className="mono" style={{ fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--err)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
          </svg>
          tampered
        </div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          Policy file tampered on {hostname || "unknown"} ({ev.user_email ?? "—"})
        </div>
        <div><span className="sbadge err" style={{ textTransform: "capitalize" }}>blocked</span></div>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--err)" }}>policy_signature_invalid</div>
        <div><span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>—</span></div>
      </div>

      {open && (
        <div style={{
          padding: "14px 24px 18px",
          borderBottom: isLast ? "none" : "1px solid var(--border)",
          background: "color-mix(in srgb, var(--err-bg) 60%, var(--surface))",
          fontSize: 12,
        }}>
          <div style={{ fontWeight: 700, color: "var(--err)", marginBottom: 10 }}>Signature mismatch detail</div>
          <table style={{ borderCollapse: "collapse", width: "100%", fontFamily: "var(--font-mono, ui-monospace, monospace)", fontSize: 11.5 }}>
            <tbody>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, paddingBottom: 6, whiteSpace: "nowrap" }}>Expected signature</td>
                <td style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{expected_signature || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, paddingBottom: 6, whiteSpace: "nowrap" }}>Computed signature</td>
                <td style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{computed_signature || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, paddingBottom: 6, whiteSpace: "nowrap" }}>Policy version</td>
                <td style={{ color: "var(--text-2)" }}>{policy_version || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, whiteSpace: "nowrap" }}>Hostname</td>
                <td style={{ color: "var(--text-2)" }}>{hostname || "—"}</td>
              </tr>
              <tr>
                <td style={{ color: "var(--text-muted)", paddingRight: 16, whiteSpace: "nowrap" }}>Timestamp</td>
                <td style={{ color: "var(--text-2)" }}>{formatTs(ev.ts)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
