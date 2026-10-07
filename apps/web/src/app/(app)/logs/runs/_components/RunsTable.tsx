"use client"

import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react"
import Link from "next/link"
import StatusBadge from "@/components/runs/StatusBadge"
import { formatTrigger, timeAgo, duration, effectiveStatus } from "@/lib/runUtils"

export interface Run {
  id: string
  workflow_id: string
  workflow_name: string
  project_id: string | null
  project_name: string | null
  status: string
  triggered_by: string | null
  trigger_summary: string | null
  repo: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  created_at: string
  governance?: { blocked?: boolean; rule_id?: string; reason_code?: string } | null
}

function outcomeText(status: string, triggerSummary: string | null): string {
  if (triggerSummary) return triggerSummary
  if (status === "succeeded") return "Completed successfully"
  if (status === "running") return "In progress"
  if (status === "paused") return "Waiting for approval"
  if (status === "failed") return "Execution failed"
  if (status === "cancelled") return "Cancelled"
  if (status === "skipped") return "Skipped"
  return "Queued"
}

interface FilterChipProps {
  label: string
  count?: number
  active: boolean
  onClick: () => void
}

export function FilterChip({ label, count, active, onClick }: FilterChipProps) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{
        height: 30,
        cursor: "pointer",
        fontWeight: 600,
        fontSize: 12.5,
        padding: "0 12px",
        borderRadius: 999,
        border: `1px solid ${active ? "var(--accent-ring)" : "var(--border)"}`,
        background: active ? "var(--accent-weak)" : "var(--surface)",
        color: active ? "var(--accent-text)" : "var(--text-2)",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        transition: "background .12s, border-color .12s, color .12s",
        outline: "none",
      }}
    >
      {label}
      {count !== undefined && (
        <span style={{ opacity: 0.6, marginLeft: 2 }}>· {count}</span>
      )}
    </button>
  )
}

interface FilterPanelProps {
  isOpen: boolean
  onClose: () => void
  repositories: string[]
  playbooks: string[]
  selectedRepository: string | null
  selectedPlaybook: string | null
  selectedTimeRange: TimeRangeLabel
  onRepositoryChange: (repo: string | null) => void
  onPlaybookChange: (playbook: string | null) => void
  onTimeRangeChange: (range: TimeRangeLabel) => void
  onReset: () => void
}

export function FilterPanel({
  isOpen,
  onClose,
  repositories,
  playbooks,
  selectedRepository,
  selectedPlaybook,
  selectedTimeRange,
  onRepositoryChange,
  onPlaybookChange,
  onTimeRangeChange,
  onReset,
}: FilterPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return
    const el = panelRef.current?.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    el?.focus()
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.5)",
        zIndex: 40,
      }}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Filter runs"
        style={{
          position: "fixed",
          top: 60,
          right: 24,
          width: 340,
          background: "var(--surface)",
          borderRadius: 12,
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
          zIndex: 50,
        }}
        onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
      >
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h3 style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", margin: 0 }}>Filter runs</h3>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: 16,
              padding: "2px 6px",
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Repository
            </label>
            <select
              value={selectedRepository || "All repositories"}
              onChange={e => onRepositoryChange(e.target.value === "All repositories" ? null : e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                fontSize: 13,
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--surface-2)",
                color: "var(--text)",
                cursor: "pointer",
                outline: "none",
              }}
            >
              <option value="All repositories">All repositories</option>
              {repositories.map(repo => (
                <option key={repo} value={repo}>
                  {repo || "Unknown"}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Playbook
            </label>
            <select
              value={selectedPlaybook || "All playbooks"}
              onChange={e => onPlaybookChange(e.target.value === "All playbooks" ? null : e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                fontSize: 13,
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--surface-2)",
                color: "var(--text)",
                cursor: "pointer",
                outline: "none",
              }}
            >
              <option value="All playbooks">All playbooks</option>
              {playbooks.map(playbook => (
                <option key={playbook} value={playbook}>
                  {playbook}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Time range
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {TIME_RANGES.map(range => (
                <button
                  key={range}
                  onClick={() => onTimeRangeChange(range)}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 6,
                    border: `1px solid ${selectedTimeRange === range ? "var(--accent-ring)" : "var(--border)"}`,
                    background: selectedTimeRange === range ? "var(--accent-weak)" : "var(--surface-2)",
                    color: selectedTimeRange === range ? "var(--accent-text)" : "var(--text-2)",
                    fontSize: 13,
                    cursor: "pointer",
                    textAlign: "left",
                    fontWeight: selectedTimeRange === range ? 600 : 500,
                    transition: "background .12s, border-color .12s",
                    outline: "none",
                  }}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div
          style={{
            padding: "12px 20px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: 8,
            justifyContent: "flex-end",
          }}
        >
          <button
            onClick={onReset}
            style={{
              padding: "6px 14px",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              color: "var(--text-2)",
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
              transition: "background .12s",
              outline: "none",
            }}
            onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-3)")}
            onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-2)")}
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}

export type FilterLabel = "All" | "Running" | "Succeeded" | "Awaiting" | "Failed"
export type TimeRangeLabel = "Last 24 hours" | "Last 7 days" | "Last 30 days" | "All time"

export const FILTERS: FilterLabel[] = ["All", "Running", "Succeeded", "Awaiting", "Failed"]
const TIME_RANGES: TimeRangeLabel[] = ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"]

export function matchesFilter(run: Run, filter: FilterLabel): boolean {
  if (filter === "All") return true
  if (filter === "Running") return run.status === "running"
  if (filter === "Succeeded") return run.status === "succeeded"
  if (filter === "Awaiting") return run.status === "paused"
  if (filter === "Failed") return run.status === "failed" || run.status === "cancelled"
  return true
}

const GRID = "1.6fr 1fr 1.2fr 0.7fr 0.7fr 30px"
const HEADERS = ["Workflow", "Trigger", "Outcome", "Duration", "When", ""]

interface RunRowProps {
  run: Run
}

function RunRow({ run }: RunRowProps) {
  const [hovered, setHovered] = useState(false)
  const ts = run.started_at ?? run.created_at
  const triggerLabel = formatTrigger(run.triggered_by)
  // Only show repo under workflow name — trigger_summary lives in Outcome only (#12)
  const triggerDetail = run.repo ?? null
  const durationStr = duration(run.started_at, run.completed_at, run.status)

  return (
    <Link
      href={`/workflows/${run.workflow_id}/runs/${run.id}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "grid",
        gridTemplateColumns: GRID,
        gap: 14,
        padding: "13px 20px",
        borderBottom: "1px solid var(--border)",
        alignItems: "center",
        cursor: "pointer",
        transition: "background .12s",
        background: hovered ? "var(--surface-2)" : "transparent",
        textDecoration: "none",
      }}
    >
      {/* Workflow + project breadcrumb */}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}>
          {run.project_name && run.project_id && (
            <>
              <Link
                href={`/projects/${run.project_id}`}
                onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
                style={{ fontSize: 11.5, color: "var(--text-3)", fontWeight: 500, whiteSpace: "nowrap", textDecoration: "none", flexShrink: 0 }}
                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.color = "var(--accent-text)")}
                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.color = "var(--text-3)")}
              >
                {run.project_name}
              </Link>
              <span style={{ color: "var(--border-2)", fontSize: 11, flexShrink: 0 }}>/</span>
            </>
          )}
          <span
            style={{ fontWeight: 600, fontSize: 13.5, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {run.workflow_name}
          </span>
        </div>
        {triggerDetail && (
          <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 11, color: "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {triggerDetail}
          </div>
        )}
      </div>

      {/* Trigger */}
      <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {triggerLabel}
      </div>

      {/* Outcome — StatusBadge + trigger_summary text here only (#12) */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <StatusBadge status={effectiveStatus(run)} />
        <span style={{ fontSize: 12.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {outcomeText(run.status, run.trigger_summary)}
        </span>
      </div>

      {/* Duration (#7 — elapsed for active runs) */}
      <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, color: "var(--text-3)" }}>
        {durationStr}
      </div>

      {/* When — absolute date on hover (#15) */}
      <div
        title={new Date(run.created_at).toLocaleString()}
        style={{ fontSize: 12, color: "var(--text-muted)" }}
      >
        {timeAgo(ts)}
      </div>

      {/* Chevron */}
      <svg
        width={15}
        height={15}
        viewBox="0 0 15 15"
        fill="none"
        style={{ color: "var(--text-muted)", flexShrink: 0 }}
        aria-hidden
      >
        <path d="M5.5 3.5L9.5 7.5L5.5 11.5" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </Link>
  )
}

interface RunsTableProps {
  runs: Run[]
}

export function RunsTable({ runs }: RunsTableProps) {
  if (runs.length === 0) {
    return (
      <div
        style={{
          borderRadius: 12,
          border: "1.5px dashed var(--border-2)",
          padding: "64px 0",
          textAlign: "center",
        }}
      >
        <p style={{ fontWeight: 500, color: "var(--text-2)", marginBottom: 4 }}>No runs</p>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Nothing to show for this filter.</p>
      </div>
    )
  }

  return (
    <div
      style={{
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: "var(--surface)",
        overflow: "hidden",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: GRID,
          gap: 14,
          padding: "11px 20px",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface-2)",
        }}
      >
        {HEADERS.map((h, i) => (
          <div
            key={i}
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.07em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
            }}
          >
            {h}
          </div>
        ))}
      </div>

      <div>
        {runs.map(run => (
          <RunRow key={run.id} run={run} />
        ))}
      </div>
    </div>
  )
}
