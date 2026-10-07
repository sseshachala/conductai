"use client"

import Link from "next/link"
import type { MouseEvent as ReactMouseEvent } from "react"
import { ActivityRow, ActivityHeader, type AuditEvent } from "@/components/guard/ActivityRow"
import type { ColumnKey } from "@/components/guard/common"

// ─── Grouping helpers ──────────────────────────────────────────────────────

export type RunGroup = { runId: string | null; events: AuditEvent[] }
export type WorkflowGroup = { workflowName: string; workflowId: string | null; runs: RunGroup[] }

export function buildGoalGroups(evts: AuditEvent[]): { named: WorkflowGroup[]; adhoc: AuditEvent[] } {
  const wfMap = new Map<string, WorkflowGroup>()
  const adhoc: AuditEvent[] = []

  for (const ev of evts) {
    const wfName = ev.conductai_workflow ?? ev.goal_name ?? null
    if (!wfName) {
      adhoc.push(ev)
      continue
    }
    if (!wfMap.has(wfName)) {
      wfMap.set(wfName, { workflowName: wfName, workflowId: ev.conductai_workflow_id ?? null, runs: [] })
    }
    const wfGroup = wfMap.get(wfName)!
    const runId = ev.conductai_run_id ?? null
    let runGroup = wfGroup.runs.find(r => r.runId === runId)
    if (!runGroup) {
      runGroup = { runId, events: [] }
      wfGroup.runs.push(runGroup)
    }
    runGroup.events.push(ev)
  }

  return { named: Array.from(wfMap.values()), adhoc }
}

export function GroupedEvents({
  events, collapsedGroups, toggleGroup, visibleColumns, serverTimeDrift, hasMore, loadingMore, loadMore,
}: {
  events: AuditEvent[]
  collapsedGroups: Record<string, boolean>
  toggleGroup: (key: string) => void
  visibleColumns: ColumnKey[]
  serverTimeDrift: number
  hasMore: boolean
  loadingMore: boolean
  loadMore: () => void
}) {
  const { named, adhoc } = buildGoalGroups(events)
  // Header driven by <ColumnsMenu> selection — #1982.
  const tableHeader = <ActivityHeader visibleColumns={visibleColumns} />

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Named workflow groups */}
      {named.map(wfGroup => {
        const wfKey = wfGroup.workflowName
        const isCollapsed = collapsedGroups[wfKey] ?? false
        const totalEvents = wfGroup.runs.reduce((s, r) => s + r.events.length, 0)
        const blockedCount = wfGroup.runs.reduce((s, r) => s + r.events.filter(e => e.decision === "blocked").length, 0)
        const warnedCount = wfGroup.runs.reduce((s, r) => s + r.events.filter(e => e.decision === "warned").length, 0)

        return (
          <div key={wfKey} className="card" style={{ overflow: "hidden" }}>
            {/* Workflow group header */}
            <button
              onClick={() => toggleGroup(wfKey)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", textAlign: "left",
                padding: "12px 18px",
                background: "var(--surface-2)",
                border: "none",
                borderBottom: isCollapsed ? "none" : "1px solid var(--border)",
                cursor: "pointer",
              }}
            >
              <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1 }}>
                {isCollapsed ? "▶" : "▼"}
              </span>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase", color: "var(--text-muted)" }}>
                Goal
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                {wfGroup.workflowName}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 4 }}>
                {totalEvents} event{totalEvents !== 1 ? "s" : ""} · {wfGroup.runs.length} run{wfGroup.runs.length !== 1 ? "s" : ""}
              </span>
              {blockedCount > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                  background: "var(--block-bg)", color: "var(--block)", border: "1px solid var(--block-bd)",
                }}>
                  {blockedCount} blocked
                </span>
              )}
              {warnedCount > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                  background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)",
                }}>
                  {warnedCount} warned
                </span>
              )}
            </button>

            {!isCollapsed && wfGroup.runs.map((runGroup, ri) => {
              const runKey = `${wfKey}::${runGroup.runId ?? `adhoc-${ri}`}`
              const isRunCollapsed = collapsedGroups[runKey] ?? false

              return (
                <div key={runKey} style={{ borderBottom: ri < wfGroup.runs.length - 1 ? "1px solid var(--border)" : "none" }}>
                  {/* Run sub-header */}
                  <button
                    onClick={() => toggleGroup(runKey)}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      width: "100%", textAlign: "left",
                      padding: "9px 18px 9px 36px",
                      background: "transparent",
                      border: "none",
                      borderBottom: isRunCollapsed ? "none" : "1px solid var(--border)",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1 }}>
                      {isRunCollapsed ? "▶" : "▼"}
                    </span>
                    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: "var(--text-muted)" }}>
                      Run
                    </span>
                    {runGroup.runId ? (
                      <Link
                        href={`/runs/${runGroup.runId}`}
                        onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
                        style={{ fontSize: 11.5, fontFamily: "var(--font-mono, ui-monospace, monospace)", color: "var(--accent-text)", textDecoration: "none", fontWeight: 600 }}
                      >
                        {runGroup.runId}
                      </Link>
                    ) : (
                      <span style={{ fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>no run id</span>
                    )}
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {runGroup.events.length} event{runGroup.events.length !== 1 ? "s" : ""}
                    </span>
                  </button>

                  {!isRunCollapsed && (
                    <div>
                      {tableHeader}
                      {runGroup.events.map((ev, i) => (
                        <ActivityRow key={ev.id} ev={ev} isLast={i === runGroup.events.length - 1} visibleColumns={visibleColumns} nowOffsetMs={serverTimeDrift} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}

      {/* Ad-hoc events (no workflow) */}
      {adhoc.length > 0 && (() => {
        const adhocKey = "__adhoc__"
        const isCollapsed = collapsedGroups[adhocKey] ?? false
        const blockedCount = adhoc.filter(e => e.decision === "blocked").length
        const warnedCount = adhoc.filter(e => e.decision === "warned").length
        return (
          <div className="card" style={{ overflow: "hidden" }}>
            <button
              onClick={() => toggleGroup(adhocKey)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", textAlign: "left",
                padding: "12px 18px",
                background: "var(--surface-2)",
                border: "none",
                borderBottom: isCollapsed ? "none" : "1px solid var(--border)",
                cursor: "pointer",
              }}
            >
              <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1 }}>
                {isCollapsed ? "▶" : "▼"}
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-2)" }}>
                Ad-hoc sessions
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {adhoc.length} event{adhoc.length !== 1 ? "s" : ""} · no workflow attached
              </span>
              {blockedCount > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                  background: "var(--block-bg)", color: "var(--block)", border: "1px solid var(--block-bd)",
                }}>
                  {blockedCount} blocked
                </span>
              )}
              {warnedCount > 0 && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                  background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)",
                }}>
                  {warnedCount} warned
                </span>
              )}
            </button>
            {!isCollapsed && (
              <div>
                {tableHeader}
                {adhoc.map((ev, i) => (
                  <ActivityRow key={ev.id} ev={ev} isLast={i === adhoc.length - 1} visibleColumns={visibleColumns} nowOffsetMs={serverTimeDrift} />
                ))}
              </div>
            )}
          </div>
        )
      })()}

      {/* Load more */}
      {hasMore && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 0" }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Showing {events.length} events</span>
          <button
            onClick={loadMore}
            disabled={loadingMore}
            style={{ fontSize: 12, color: "var(--accent-text)", background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}
          >
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
      {!hasMore && events.length > 0 && (
        <div style={{ textAlign: "center", fontSize: 12, color: "var(--text-muted)", padding: "4px 0" }}>
          {events.length} event{events.length !== 1 ? "s" : ""} total
        </div>
      )}
    </div>
  )
}
