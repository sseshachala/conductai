"use client"

import type { Dispatch, SetStateAction } from "react"
import { GuardBadge, GuardSectionHeader, timeAgo } from "@/components/guard/common"
import { AgentAvatar } from "@/components/guard/AgentAvatar"
import type { InboxRow, InboxEvent, InboxStatus, ResolvedReason } from "@/lib/api"

export const REASON_LABEL: Record<ResolvedReason, string> = {
  expected:         "Expected — working as intended",
  escalated:        "Escalated to security team",
  exception_added:  "Exception added to policy",
  false_positive:   "False positive — rule too broad",
}

export function InboxRowList({
  rows, expandedId, events, toggleExpand, reasonMap, setReasonMap, noteMap, setNoteMap, busyId, applyStatus,
}: {
  rows: InboxRow[]
  expandedId: string | null
  events: Record<string, InboxEvent[]>
  toggleExpand: (row: InboxRow) => Promise<void>
  reasonMap: Record<string, ResolvedReason>
  setReasonMap: Dispatch<SetStateAction<Record<string, ResolvedReason>>>
  noteMap: Record<string, string>
  setNoteMap: Dispatch<SetStateAction<Record<string, string>>>
  busyId: string | null
  applyStatus: (row: InboxRow, next: InboxStatus) => Promise<void>
}) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
      {rows.map((row, idx) => {
        const isExpanded = expandedId === row.id
        const rowEvents = events[row.id] ?? []
        return (
          <div key={row.id} style={{
            borderTop: idx === 0 ? "none" : "1px solid var(--border)",
            background: isExpanded ? "var(--surface-alt, var(--surface))" : "transparent",
          }}>
            <div
              onClick={() => toggleExpand(row)}
              style={{
                display: "grid",
                gridTemplateColumns: "80px 1fr 80px 32px 100px 100px 40px",
                gap: 12,
                padding: "12px 16px",
                alignItems: "center",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              <GuardBadge kind="severity" value={row.severity} />
              <div style={{ overflow: "hidden" }}>
                <div style={{ color: "var(--text)", fontWeight: 500, marginBottom: 2 }}>
                  {row.rule_id}
                </div>
                <div style={{
                  color: "var(--text-muted)", fontSize: 12,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {row.description ?? <em style={{ opacity: 0.6 }}>no description</em>}
                </div>
              </div>
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                {row.source}
              </span>
              <AgentAvatar agentId={row.agent_identity_id} size={22} />
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                {row.occurrences}× · {timeAgo(row.last_seen_at)}
              </span>
              <GuardBadge kind="status" value={row.status} />
              <span style={{ color: "var(--text-muted)", textAlign: "right" }}>
                {isExpanded ? "▾" : "▸"}
              </span>
            </div>

            {isExpanded && (
              <div style={{ padding: "0 16px 16px 16px", borderTop: "1px solid var(--border)" }}>
                {/* Recent events */}
                <div style={{ marginTop: 12, marginBottom: 16 }}>
                  <GuardSectionHeader title="Recent events" subtitle={`${rowEvents.length}`} />
                  {rowEvents.length === 0 && (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No events loaded yet.</div>
                  )}
                  {rowEvents.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                      {rowEvents.map(e => (
                        <div key={e.id} style={{
                          display: "grid", gridTemplateColumns: "120px 80px 28px 1fr 1fr",
                          gap: 8, padding: "4px 8px",
                          background: "var(--surface)", borderRadius: 3, color: "var(--text-muted)",
                        }}>
                          <span>{timeAgo(e.ts)}</span>
                          <GuardBadge kind="decision" value={e.decision} />
                          <AgentAvatar agentId={e.agent_identity_id} size={20} />
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {e.ai_tool ?? "-"} {e.user_email ? `· ${e.user_email}` : ""}
                          </span>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {e.provider ? `${e.provider}/${e.model}` : (e.input_summary ?? "")}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Resolve form */}
                {row.status !== "resolved" && (
                  <div style={{
                    padding: 12, background: "var(--surface)", borderRadius: 6,
                    border: "1px solid var(--border)",
                  }}>
                    <GuardSectionHeader title="Resolve" />
                    <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                      {(Object.keys(REASON_LABEL) as ResolvedReason[]).map(r => (
                        <label key={r} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text)" }}>
                          <input
                            type="radio"
                            name={`reason-${row.id}`}
                            value={r}
                            checked={reasonMap[row.id] === r}
                            onChange={() => setReasonMap(m => ({ ...m, [row.id]: r }))}
                          />
                          {REASON_LABEL[r]}
                        </label>
                      ))}
                    </div>
                    <textarea
                      placeholder="Optional note (500 char cap)"
                      value={noteMap[row.id] ?? ""}
                      onChange={e => setNoteMap(m => ({ ...m, [row.id]: e.target.value.slice(0, 500) }))}
                      style={{
                        width: "100%", minHeight: 60, padding: 8, fontSize: 12,
                        background: "var(--bg)", color: "var(--text)",
                        border: "1px solid var(--border)", borderRadius: 4, marginBottom: 8,
                        fontFamily: "inherit",
                      }}
                    />
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        onClick={() => applyStatus(row, "resolved")}
                        disabled={busyId === row.id || !reasonMap[row.id]}
                        style={{
                          padding: "6px 14px", fontSize: 12, borderRadius: 4,
                          background: reasonMap[row.id] ? "var(--accent)" : "var(--surface)",
                          color: reasonMap[row.id] ? "var(--accent-fg, white)" : "var(--text-muted)",
                          border: "1px solid var(--border)",
                          cursor: busyId === row.id || !reasonMap[row.id] ? "not-allowed" : "pointer",
                          fontWeight: 500,
                        }}
                      >
                        {busyId === row.id ? "Saving…" : "Mark resolved"}
                      </button>
                      <button
                        onClick={() => applyStatus(row, "triaging")}
                        disabled={busyId === row.id || row.status === "triaging"}
                        style={{
                          padding: "6px 14px", fontSize: 12, borderRadius: 4,
                          background: "var(--surface)", color: "var(--text-muted)",
                          border: "1px solid var(--border)", cursor: "pointer",
                        }}
                      >
                        Move to triaging
                      </button>
                    </div>
                  </div>
                )}

                {row.status === "resolved" && (
                  <div style={{
                    padding: 12, background: "var(--surface)", borderRadius: 6,
                    border: "1px solid var(--border)", fontSize: 12, color: "var(--text-muted)",
                  }}>
                    <div style={{ marginBottom: 4 }}>
                      Resolved by <strong>{row.resolved_by ?? "unknown"}</strong>
                      {row.resolved_at && <> · {timeAgo(row.resolved_at)}</>}
                    </div>
                    {row.resolved_reason && (
                      <div style={{ marginBottom: 4 }}>
                        Reason: {REASON_LABEL[row.resolved_reason as ResolvedReason] ?? row.resolved_reason}
                      </div>
                    )}
                    {row.resolved_note && (
                      <div style={{ marginTop: 6, fontStyle: "italic" }}>&ldquo;{row.resolved_note}&rdquo;</div>
                    )}
                    <button
                      onClick={() => applyStatus(row, "open")}
                      disabled={busyId === row.id}
                      style={{
                        marginTop: 8, padding: "4px 10px", fontSize: 11, borderRadius: 4,
                        background: "var(--surface)", color: "var(--text-muted)",
                        border: "1px solid var(--border)", cursor: "pointer",
                      }}
                    >
                      Reopen
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
