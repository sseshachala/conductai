"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guardInbox } from "@/lib/api"
import type {
  InboxRow,
  InboxEvent,
  InboxStatus,
  InboxSeverity,
  InboxSource,
  ResolvedReason,
} from "@/lib/api"

// ─── Formatting helpers ───────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${Math.max(sec, 0)}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

const SEVERITY_COLOR: Record<string, { bg: string; fg: string }> = {
  critical: { bg: "var(--err-bg)",  fg: "var(--err)"  },
  medium:   { bg: "var(--warn-bg)", fg: "var(--warn)" },
  low:      { bg: "var(--info-bg)", fg: "var(--info)" },
}

const STATUS_COLOR: Record<string, { bg: string; fg: string }> = {
  open:     { bg: "var(--warn-bg)", fg: "var(--warn)" },
  triaging: { bg: "var(--info-bg)", fg: "var(--info)" },
  resolved: { bg: "var(--ok-bg)",   fg: "var(--ok)"   },
}

const REASON_LABEL: Record<ResolvedReason, string> = {
  expected:         "Expected — working as intended",
  escalated:        "Escalated to security team",
  exception_added:  "Exception added to policy",
  false_positive:   "False positive — rule too broad",
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default function GuardInboxPage() {
  const { authFetch } = useAuthFetch()
  const [rows, setRows] = useState<InboxRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)

  const [statusFilter, setStatusFilter] = useState<InboxStatus | "all">("open")
  const [severityFilter, setSeverityFilter] = useState<InboxSeverity | "all">("all")
  const [sourceFilter, setSourceFilter] = useState<InboxSource | "all">("all")

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [events, setEvents] = useState<Record<string, InboxEvent[]>>({})
  const [busyId, setBusyId] = useState<string | null>(null)

  // Resolve form state — one row can be open at a time so a flat map is fine.
  const [reasonMap, setReasonMap] = useState<Record<string, ResolvedReason>>({})
  const [noteMap, setNoteMap] = useState<Record<string, string>>({})

  // Extend-backfill state
  const [backfillDays, setBackfillDays] = useState<number>(60)
  const [backfillBusy, setBackfillBusy] = useState(false)
  const [backfillMsg, setBackfillMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await guardInbox.list(authFetch, {
        status: statusFilter === "all" ? undefined : statusFilter,
        severity: severityFilter === "all" ? undefined : severityFilter,
        source: sourceFilter === "all" ? undefined : sourceFilter,
        limit: 200,
      })
      setRows(data)
      setLastFetched(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed")
    } finally {
      setLoading(false)
    }
  }, [authFetch, statusFilter, severityFilter, sourceFilter])

  useEffect(() => { void load() }, [load])

  const toggleExpand = useCallback(async (row: InboxRow) => {
    if (expandedId === row.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(row.id)
    if (!events[row.id]) {
      try {
        const ev = await guardInbox.events(authFetch, row.id, 20)
        setEvents(prev => ({ ...prev, [row.id]: ev }))
      } catch (e) {
        setError(e instanceof Error ? e.message : "events load failed")
      }
    }
  }, [authFetch, events, expandedId])

  const applyStatus = useCallback(async (row: InboxRow, next: InboxStatus) => {
    setBusyId(row.id)
    try {
      const reason = reasonMap[row.id]
      const note = noteMap[row.id]
      const updated = await guardInbox.patch(authFetch, row.id, {
        status: next,
        resolved_reason: next === "resolved" ? reason : undefined,
        resolved_note: next === "resolved" ? note : undefined,
      })
      setRows(prev => prev.map(r => (r.id === row.id ? updated : r)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "update failed")
    } finally {
      setBusyId(null)
    }
  }, [authFetch, reasonMap, noteMap])

  const runBackfill = useCallback(async () => {
    setBackfillBusy(true)
    setBackfillMsg(null)
    try {
      const r = await guardInbox.backfill(authFetch, backfillDays)
      setBackfillMsg(`Synced last ${r.days} days — ${r.inserted} events touched.`)
      await load()
    } catch (e) {
      setBackfillMsg(e instanceof Error ? e.message : "backfill failed")
    } finally {
      setBackfillBusy(false)
    }
  }, [authFetch, backfillDays, load])

  const counts = useMemo(() => {
    const c = { open: 0, triaging: 0, resolved: 0 }
    for (const r of rows) {
      if (r.status === "open") c.open += 1
      else if (r.status === "triaging") c.triaging += 1
      else if (r.status === "resolved") c.resolved += 1
    }
    return c
  }, [rows])

  return (
    <AppShell>
      <GuardShell lastFetched={lastFetched}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: "var(--text)" }}>Inbox</h2>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              Deduped triage of blocked, warned, and approved events. One row per rule × source × message.
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
            <span>Sync events from the last</span>
            <select
              value={backfillDays}
              onChange={e => setBackfillDays(Number(e.target.value))}
              disabled={backfillBusy}
              style={{
                background: "var(--surface)",
                color: "var(--text)",
                border: "1px solid var(--border)",
                borderRadius: 4,
                padding: "4px 8px",
                fontSize: 12,
              }}
            >
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
            </select>
            <button
              onClick={runBackfill}
              disabled={backfillBusy}
              style={{
                background: "var(--surface)",
                color: "var(--text)",
                border: "1px solid var(--border)",
                borderRadius: 4,
                padding: "4px 12px",
                fontSize: 12,
                cursor: backfillBusy ? "wait" : "pointer",
              }}
            >
              {backfillBusy ? "Syncing…" : "Sync now"}
            </button>
          </div>
        </div>

        {backfillMsg && (
          <div style={{
            fontSize: 12, color: "var(--text-muted)", padding: "6px 10px",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 4, marginBottom: 12,
          }}>
            {backfillMsg}
          </div>
        )}

        {/* Filter bar */}
        <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
          {(["open", "triaging", "resolved", "all"] as const).map(k => (
            <button
              key={k}
              onClick={() => setStatusFilter(k)}
              style={{
                padding: "6px 12px",
                fontSize: 12,
                borderRadius: 4,
                border: "1px solid var(--border)",
                background: statusFilter === k ? "var(--accent-bg)" : "var(--surface)",
                color: statusFilter === k ? "var(--accent)" : "var(--text-muted)",
                fontWeight: statusFilter === k ? 600 : 400,
                cursor: "pointer",
              }}
            >
              {k === "all" ? "All" : k[0].toUpperCase() + k.slice(1)}
              {k !== "all" && counts[k as keyof typeof counts] > 0 && (
                <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.7 }}>
                  {counts[k as keyof typeof counts]}
                </span>
              )}
            </button>
          ))}
          <div style={{ width: 1, background: "var(--border)", margin: "0 4px" }} />
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value as InboxSeverity | "all")}
            style={{
              background: "var(--surface)", color: "var(--text)",
              border: "1px solid var(--border)", borderRadius: 4,
              padding: "6px 8px", fontSize: 12,
            }}
          >
            <option value="all">All severities</option>
            <option value="critical">Critical</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value as InboxSource | "all")}
            style={{
              background: "var(--surface)", color: "var(--text)",
              border: "1px solid var(--border)", borderRadius: 4,
              padding: "6px 8px", fontSize: 12,
            }}
          >
            <option value="all">All sources</option>
            <option value="proxy">Proxy</option>
            <option value="mcp">MCP</option>
            <option value="hook">Hook</option>
            <option value="runtime">Runtime</option>
          </select>
        </div>

        {error && (
          <div style={{
            fontSize: 12, color: "var(--err)", padding: "8px 12px",
            background: "var(--err-bg)", borderRadius: 4, marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        {loading && rows.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", padding: 20, textAlign: "center" }}>
            Loading…
          </div>
        )}

        {!loading && rows.length === 0 && (
          <div style={{
            fontSize: 13, color: "var(--text-muted)", padding: 40, textAlign: "center",
            background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: 6,
          }}>
            No events in this view. Blocked, warned, and approved decisions land here as they happen.
          </div>
        )}

        {rows.length > 0 && (
          <div style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
            {rows.map((row, idx) => {
              const sevColor = SEVERITY_COLOR[row.severity] ?? SEVERITY_COLOR.medium
              const statusColor = STATUS_COLOR[row.status] ?? STATUS_COLOR.open
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
                      gridTemplateColumns: "80px 1fr 80px 100px 100px 40px",
                      gap: 12,
                      padding: "12px 16px",
                      alignItems: "center",
                      cursor: "pointer",
                      fontSize: 13,
                    }}
                  >
                    <span style={{
                      display: "inline-block", padding: "2px 8px", fontSize: 11,
                      borderRadius: 4, background: sevColor.bg, color: sevColor.fg, fontWeight: 600,
                      textAlign: "center",
                    }}>
                      {row.severity}
                    </span>
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
                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                      {row.occurrences}× · {timeAgo(row.last_seen_at)}
                    </span>
                    <span style={{
                      display: "inline-block", padding: "2px 8px", fontSize: 11,
                      borderRadius: 4, background: statusColor.bg, color: statusColor.fg,
                      textAlign: "center",
                    }}>
                      {row.status}
                    </span>
                    <span style={{ color: "var(--text-muted)", textAlign: "right" }}>
                      {isExpanded ? "▾" : "▸"}
                    </span>
                  </div>

                  {isExpanded && (
                    <div style={{ padding: "0 16px 16px 16px", borderTop: "1px solid var(--border)" }}>
                      {/* Recent events */}
                      <div style={{ marginTop: 12, marginBottom: 16 }}>
                        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-muted)", marginBottom: 8 }}>
                          Recent events ({rowEvents.length})
                        </div>
                        {rowEvents.length === 0 && (
                          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No events loaded yet.</div>
                        )}
                        {rowEvents.length > 0 && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                            {rowEvents.map(e => (
                              <div key={e.id} style={{
                                display: "grid", gridTemplateColumns: "120px 80px 1fr 1fr",
                                gap: 8, padding: "4px 8px",
                                background: "var(--surface)", borderRadius: 3, color: "var(--text-muted)",
                              }}>
                                <span>{timeAgo(e.ts)}</span>
                                <span style={{ fontWeight: 500 }}>{e.decision}</span>
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
                          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-muted)", marginBottom: 8 }}>
                            Resolve
                          </div>
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
        )}
      </GuardShell>
    </AppShell>
  )
}
