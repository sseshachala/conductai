"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api/client"

// ─── Types ─────────────────────────────────────────────────────────────────

type ApprovalStatus = "pending" | "approved" | "rejected" | "timed_out"

interface ApprovalRow {
  id: string
  rule_id: string
  rule_pack: string | null
  rule_message: string | null
  tool_name: string | null
  tool_input: Record<string, unknown>
  requester_email: string | null
  requester_agent_ident: string | null
  surface: string
  session_id: string | null
  source_run_id: string | null
  source_block_id: string | null
  approval_group: string | null
  approval_type: string
  status: ApprovalStatus
  decided_by_email: string | null
  decided_reason: string | null
  decided_at: string | null
  latency_ms: number | null
  created_at: string
  timeout_at: string
  url: string
}

interface ListOut {
  workspace_id: string
  items: ApprovalRow[]
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${Math.max(sec, 0)}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}

function timeUntil(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return "expired"
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  return `${Math.floor(min / 60)}h`
}

const STATUS_LABEL: Record<ApprovalStatus, string> = {
  pending:   "Pending",
  approved:  "Approved",
  rejected:  "Rejected",
  timed_out: "Timed out",
}

const STATUS_COLOR: Record<ApprovalStatus, { bg: string; fg: string }> = {
  pending:   { bg: "var(--warn-bg)", fg: "var(--warn)" },
  approved:  { bg: "var(--ok-bg)",   fg: "var(--ok)"   },
  rejected:  { bg: "var(--err-bg)",  fg: "var(--err)"  },
  timed_out: { bg: "var(--info-bg)", fg: "var(--info)" },
}

// ─── Page ──────────────────────────────────────────────────────────────────

export default function ApprovalsPage() {
  const { authFetch, workspaceId } = useAuthFetch()
  const searchParams = useSearchParams()
  const highlight = searchParams?.get("highlight") ?? null
  const [filter, setFilter] = useState<ApprovalStatus | "all">(highlight ? "all" : "pending")
  const [items, setItems] = useState<ApprovalRow[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [reasonMap, setReasonMap] = useState<Record<string, string>>({})
  const [lastFetched, setLastFetched] = useState<Date | null>(null)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    setErr(null)
    try {
      const url = `${API}/guard/approvals?status=${filter}&limit=100`
      const res = await authFetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: ListOut = await res.json()
      setItems(data.items)
      setLastFetched(new Date())
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId, filter])

  useEffect(() => {
    load()
  }, [load])

  // Poll every 5s while viewing pending — cheap and reliable, avoids SSE plumbing.
  useEffect(() => {
    if (filter !== "pending") return
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [filter, load])

  useEffect(() => {
    if (!highlight || items.length === 0) return
    if (items.some(r => r.id === highlight)) {
      setExpandedId(highlight)
      const el = typeof document !== "undefined" ? document.getElementById(`approval-${highlight}`) : null
      el?.scrollIntoView({ behavior: "smooth", block: "center" })
    }
  }, [highlight, items])

  const decide = useCallback(
    async (row: ApprovalRow, decision: "approved" | "rejected") => {
      setBusyId(row.id)
      try {
        const reason = (reasonMap[row.id] || "").trim() || undefined
        const res = await authFetch(`${API}/guard/approvals/${row.id}/decide`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, reason }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
          throw new Error(body.detail || `HTTP ${res.status}`)
        }
        await load()
      } catch (e) {
        setErr((e as Error).message)
      } finally {
        setBusyId(null)
      }
    },
    [authFetch, load, reasonMap],
  )

  const counts = useMemo(() => {
    const c = { pending: 0, approved: 0, rejected: 0, timed_out: 0 }
    for (const r of items) c[r.status] += 1
    return c
  }, [items])

  return (
    <AppShell>
      <GuardShell lastFetched={lastFetched}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: "var(--text)" }}>Approvals</h2>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              Human-in-the-loop pauses triggered by Guard rules with action=approval.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {(["pending", "approved", "rejected", "timed_out", "all"] as const).map(k => (
              <button
                key={k}
                onClick={() => setFilter(k)}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  background: filter === k ? "var(--surface-2)" : "transparent",
                  color: "var(--text)",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {k === "all" ? "All" : STATUS_LABEL[k as ApprovalStatus]}
                {k !== "all" && filter !== k && counts[k as ApprovalStatus] > 0 && (
                  <span style={{ marginLeft: 6, color: "var(--text-muted)" }}>{counts[k as ApprovalStatus]}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {err && (
          <div style={{ padding: 12, borderRadius: 6, background: "var(--err-bg)", color: "var(--err)", fontSize: 13, marginBottom: 16 }}>
            {err}
          </div>
        )}

        {loading && items.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>Loading…</div>
        )}

        {!loading && items.length === 0 && !err && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>
            No {filter === "all" ? "" : STATUS_LABEL[filter as ApprovalStatus].toLowerCase()} approvals.
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map(row => {
            const isExpanded = expandedId === row.id
            const color = STATUS_COLOR[row.status]
            const isPending = row.status === "pending"
            return (
              <div
                key={row.id}
                id={`approval-${row.id}`}
                style={{
                  border: `1px solid ${highlight === row.id ? "var(--info)" : "var(--border)"}`,
                  borderRadius: 8,
                  background: "var(--surface)",
                  padding: 14,
                  boxShadow: highlight === row.id ? "0 0 0 3px var(--info-bg)" : undefined,
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: 4,
                          background: color.bg,
                          color: color.fg,
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: 0.4,
                        }}
                      >
                        {STATUS_LABEL[row.status]}
                      </span>
                      <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "var(--text)" }}>
                        {row.rule_id}
                      </span>
                      {row.rule_pack && (
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({row.rule_pack})</span>
                      )}
                      {row.approval_type === "peer" && (
                        <span style={{ fontSize: 10, padding: "1px 5px", background: "var(--info-bg)", color: "var(--info)", borderRadius: 3, fontWeight: 700 }}>
                          PEER
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 6 }}>
                      {row.rule_message || "Guard rule requires approval."}
                    </div>
                    <div style={{ display: "flex", gap: 12, fontSize: 12, color: "var(--text-muted)", flexWrap: "wrap" }}>
                      <span>
                        <b style={{ color: "var(--text)" }}>who</b>: {row.requester_email || row.requester_agent_ident || "unknown"}
                      </span>
                      <span>
                        <b style={{ color: "var(--text)" }}>from</b>: {row.surface}
                      </span>
                      {row.tool_name && (
                        <span>
                          <b style={{ color: "var(--text)" }}>tool</b>: {row.tool_name}
                        </span>
                      )}
                      {row.source_run_id && (
                        <span>
                          <b style={{ color: "var(--text)" }}>run</b>: {row.source_run_id.slice(0, 8)}…
                        </span>
                      )}
                      <span>{timeAgo(row.created_at)}</span>
                      {isPending && (
                        <span style={{ color: "var(--warn)" }}>expires in {timeUntil(row.timeout_at)}</span>
                      )}
                      {row.status !== "pending" && row.decided_by_email && (
                        <span>
                          <b style={{ color: "var(--text)" }}>decided by</b>: {row.decided_by_email}
                        </span>
                      )}
                      {row.latency_ms !== null && row.latency_ms !== undefined && row.status !== "pending" && (
                        <span>{Math.round(row.latency_ms / 1000)}s to decide</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : row.id)}
                    style={{
                      background: "transparent",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      padding: "4px 10px",
                      fontSize: 12,
                      color: "var(--text-muted)",
                      cursor: "pointer",
                    }}
                  >
                    {isExpanded ? "Hide" : "Snapshot"}
                  </button>
                </div>

                {isExpanded && (
                  <pre
                    style={{
                      marginTop: 12,
                      padding: 12,
                      background: "var(--surface-2)",
                      borderRadius: 6,
                      fontSize: 11,
                      color: "var(--text-muted)",
                      overflow: "auto",
                      maxHeight: 240,
                    }}
                  >
                    {JSON.stringify(row.tool_input, null, 2)}
                  </pre>
                )}

                {isPending && (
                  <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="text"
                      placeholder="Reason (optional)"
                      value={reasonMap[row.id] || ""}
                      onChange={e => setReasonMap(m => ({ ...m, [row.id]: e.target.value }))}
                      style={{
                        flex: 1,
                        padding: "6px 10px",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        background: "var(--surface-2)",
                        color: "var(--text)",
                        fontSize: 12,
                      }}
                    />
                    <button
                      onClick={() => decide(row, "rejected")}
                      disabled={busyId === row.id}
                      style={{
                        padding: "6px 14px",
                        borderRadius: 6,
                        border: "1px solid var(--err)",
                        background: "transparent",
                        color: "var(--err)",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: busyId === row.id ? "not-allowed" : "pointer",
                      }}
                    >
                      Reject
                    </button>
                    <button
                      onClick={() => decide(row, "approved")}
                      disabled={busyId === row.id}
                      style={{
                        padding: "6px 14px",
                        borderRadius: 6,
                        border: "1px solid var(--ok)",
                        background: "var(--ok)",
                        color: "white",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: busyId === row.id ? "not-allowed" : "pointer",
                      }}
                    >
                      {busyId === row.id ? "…" : "Approve"}
                    </button>
                  </div>
                )}

                {row.decided_reason && (
                  <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)", fontStyle: "italic" }}>
                    “{row.decided_reason}”
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </GuardShell>
    </AppShell>
  )
}
