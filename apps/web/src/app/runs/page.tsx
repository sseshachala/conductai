"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useSearchParams } from "next/navigation"
import AppShell from "@/components/AppShell"
import { needsAttention, isActive, formatTrigger, timeAgo, duration } from "@/lib/runUtils"

interface Run {
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
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

// Map API status values to display variants used in the design
type BadgeVariant = "ok" | "run" | "wait" | "err" | "idle"

function getVariant(status: string): BadgeVariant {
  if (status === "succeeded") return "ok"
  if (status === "running") return "run"
  if (status === "paused") return "wait"
  if (status === "failed" || status === "cancelled") return "err"
  return "idle"
}

interface BadgeConfig {
  bg: string
  color: string
  border: string
  label: string
  pulse: boolean
}

const BADGE_MAP: Record<BadgeVariant, BadgeConfig> = {
  ok:   { bg: "var(--ok-bg)",   color: "var(--ok)",   border: "var(--ok)",   label: "Succeeded", pulse: false },
  run:  { bg: "var(--info-bg)", color: "var(--info)",  border: "var(--info)",  label: "Running",   pulse: true  },
  wait: { bg: "var(--warn-bg)", color: "var(--warn)",  border: "var(--warn)",  label: "Awaiting",  pulse: true  },
  err:  { bg: "var(--err-bg)",  color: "var(--err)",   border: "var(--err)",   label: "Failed",    pulse: false },
  idle: { bg: "var(--surface-3)", color: "var(--text-2)", border: "var(--border)", label: "Pending", pulse: false },
}

interface StatusBadgeProps {
  status: string
}

function StatusBadge({ status }: StatusBadgeProps) {
  const variant = getVariant(status)
  const cfg = BADGE_MAP[variant]
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1,
        padding: "3px 8px",
        borderRadius: 999,
        background: cfg.bg,
        color: cfg.color,
        border: `1px solid ${cfg.border}`,
        whiteSpace: "nowrap",
        flexShrink: 0,
      }}
    >
      {cfg.pulse && (
        <span
          className="conduct-pulse-dot"
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: cfg.color,
            flexShrink: 0,
          }}
        />
      )}
      {cfg.label}
    </span>
  )
}

interface OutcomeTextProps {
  status: string
  triggerSummary: string | null
}

function outcomeText(status: string, triggerSummary: string | null): string {
  if (triggerSummary) return triggerSummary
  if (status === "succeeded") return "Completed successfully"
  if (status === "running") return "In progress"
  if (status === "paused") return "Waiting for approval"
  if (status === "failed") return "Execution failed"
  if (status === "cancelled") return "Cancelled"
  return "Pending"
}

interface FilterChipProps {
  label: string
  count?: number
  active: boolean
  onClick: () => void
}

function FilterChip({ label, count, active, onClick }: FilterChipProps) {
  return (
    <button
      onClick={onClick}
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

function FilterPanel({
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
        onClick={e => e.stopPropagation()}
      >
        {/* Panel header */}
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

        {/* Panel body */}
        <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Repository */}
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

          {/* Playbook */}
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

          {/* Time Range */}
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

        {/* Panel footer */}
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
            onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-3)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--surface-2)")}
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}

type FilterLabel = "All" | "Running" | "Awaiting" | "Failed"
type TimeRangeLabel = "Last 24 hours" | "Last 7 days" | "Last 30 days" | "All time"

const FILTERS: FilterLabel[] = ["All", "Running", "Awaiting", "Failed"]
const TIME_RANGES: TimeRangeLabel[] = ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"]

function matchesFilter(run: Run, filter: FilterLabel): boolean {
  if (filter === "All") return true
  if (filter === "Running") return run.status === "running"
  if (filter === "Awaiting") return run.status === "paused"
  if (filter === "Failed") return run.status === "failed" || run.status === "cancelled"
  return true
}

function getTimeRangeStart(range: TimeRangeLabel): Date | null {
  const now = new Date()
  if (range === "Last 24 hours") {
    return new Date(now.getTime() - 24 * 60 * 60 * 1000)
  }
  if (range === "Last 7 days") {
    return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  }
  if (range === "Last 30 days") {
    return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
  }
  return null
}

function matchesTimeRange(run: Run, range: TimeRangeLabel): boolean {
  const startDate = getTimeRangeStart(range)
  if (!startDate) return true
  const runDate = new Date(run.created_at)
  return runDate >= startDate
}

function matchesAdvancedFilters(
  run: Run,
  repository: string | null,
  playbook: string | null,
  timeRange: TimeRangeLabel
): boolean {
  if (repository && repository !== "All repositories" && run.repo !== repository) return false
  if (playbook && playbook !== "All playbooks" && run.workflow_name !== playbook) return false
  if (!matchesTimeRange(run, timeRange)) return false
  return true
}

const GRID = "1.6fr 1fr 1.2fr 0.7fr 0.7fr 30px"
const HEADERS = ["Workflow", "Trigger", "Outcome", "Duration", "When", ""]

interface RunRowProps {
  run: Run
  onClick: () => void
}

function RunRow({ run, onClick }: RunRowProps) {
  const [hovered, setHovered] = useState(false)
  const ts = run.started_at ?? run.created_at
  const triggerLabel = formatTrigger(run.triggered_by)
  const triggerDetail = run.trigger_summary ?? (run.repo ? run.repo : null)
  const durationStr = duration(run.started_at, run.completed_at)

  return (
    <div
      role="row"
      onClick={onClick}
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
      }}
    >
      {/* Workflow */}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {run.workflow_name}
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

      {/* Outcome */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <StatusBadge status={run.status} />
        <span style={{ fontSize: 12.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {outcomeText(run.status, run.trigger_summary)}
        </span>
      </div>

      {/* Duration */}
      <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, color: "var(--text-3)" }}>
        {durationStr}
      </div>

      {/* When */}
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
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
    </div>
  )
}

interface RunsTableProps {
  runs: Run[]
  onNavigate: (run: Run) => void
}

function RunsTable({ runs, onNavigate }: RunsTableProps) {
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
      {/* Header row */}
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

      {/* Data rows */}
      <div>
        {runs.map(run => (
          <RunRow
            key={run.id}
            run={run}
            onClick={() => onNavigate(run)}
          />
        ))}
      </div>
    </div>
  )
}

export default function RunsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <RunsWithAuth />
  return <RunsContent getToken={null} />
}

function RunsWithAuth() {
  const { getToken } = useAuth()
  return <RunsContent getToken={getToken} />
}

const PAGE_SIZE = 50

function RunsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const router = useRouter()
  // Keep searchParams import for potential future use; suppress lint by referencing it
  const searchParams = useSearchParams()
  void searchParams

  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [activeFilter, setActiveFilter] = useState<FilterLabel>("All")
  const [filterOpen, setFilterOpen] = useState(false)
  const [selectedRepository, setSelectedRepository] = useState<string | null>(null)
  const [selectedPlaybook, setSelectedPlaybook] = useState<string | null>(null)
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRangeLabel>("All time")

  async function buildHeaders() {
    const headers: Record<string, string> = {}
    if (getToken) {
      const t = await getToken()
      if (t) headers["Authorization"] = `Bearer ${t}`
    }
    const wsId = getCookie("delegator_project_id")
    if (wsId) headers["X-Workspace-Id"] = wsId
    return headers
  }

  function buildRunsUrl(baseOffset: number = 0): string {
    const params = new URLSearchParams()
    params.append("limit", PAGE_SIZE.toString())
    params.append("offset", baseOffset.toString())
    
    // Add advanced filters
    if (selectedRepository && selectedRepository !== "All repositories") {
      params.append("repository", selectedRepository)
    }
    if (selectedPlaybook && selectedPlaybook !== "All playbooks") {
      params.append("workflow_name", selectedPlaybook)
    }
    
    // Convert time range to created_after timestamp
    if (selectedTimeRange !== "All time") {
      const now = new Date()
      let daysBack = 7 // default
      if (selectedTimeRange === "Last 24 hours") daysBack = 1
      else if (selectedTimeRange === "Last 7 days") daysBack = 7
      else if (selectedTimeRange === "Last 30 days") daysBack = 30
      const afterDate = new Date(now.getTime() - daysBack * 24 * 60 * 60 * 1000)
      params.append("created_after", afterDate.toISOString())
    }
    
    return `${process.env.NEXT_PUBLIC_API_URL}/runs?${params.toString()}`
  }

  useEffect(() => {
    async function load() {
      const headers = await buildHeaders()
      try {
        const url = buildRunsUrl(0)
        const res = await fetch(url, { headers })
        if (res.ok) {
          const data: Run[] = await res.json()
          setRuns(data)
          setHasMore(data.length === PAGE_SIZE)
          setOffset(PAGE_SIZE)
        }
      } finally {
        setLoading(false)
      }
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepository, selectedPlaybook, selectedTimeRange])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const headers = await buildHeaders()
      const url = buildRunsUrl(offset)
      const res = await fetch(url, { headers })
      if (res.ok) {
        const data: Run[] = await res.json()
        setRuns(prev => [...prev, ...data])
        setHasMore(data.length === PAGE_SIZE)
        setOffset(o => o + PAGE_SIZE)
      }
    } finally {
      setLoadingMore(false)
    }
  }

  async function handleRefresh() {
    setLoading(true)
    setRuns([])
    setOffset(0)
    setHasMore(false)
    const headers = await buildHeaders()
    try {
      const url = buildRunsUrl(0)
      const res = await fetch(url, { headers })
      if (res.ok) {
        const data: Run[] = await res.json()
        setRuns(data)
        setHasMore(data.length === PAGE_SIZE)
        setOffset(PAGE_SIZE)
      }
    } finally {
      setLoading(false)
    }
  }

  function handleNavigate(run: Run) {
    router.push(`/workflows/${run.workflow_id}/runs/${run.id}`)
  }

  // Extract unique repositories and playbooks
  const repositories = Array.from(new Set(runs.map(r => r.repo).filter(Boolean))).sort() as string[]
  const playbooks = Array.from(new Set(runs.map(r => r.workflow_name))).sort()

  // Apply all filters
  const shownRuns = runs.filter(r => {
    if (!matchesFilter(r, activeFilter)) return false
    if (!matchesAdvancedFilters(r, selectedRepository, selectedPlaybook, selectedTimeRange)) return false
    return true
  })

  // Count badges for chips
  const countFor = (f: FilterLabel) => {
    if (f === "All") return runs.length
    return runs.filter(r => matchesFilter(r, f)).length
  }

  // Keep existing derived counts (used for backwards compat logic)
  const _needsReview = runs.filter(r => needsAttention(r.status)).length
  void _needsReview
  const _activeRuns = runs.filter(r => isActive(r.status)).length
  void _activeRuns

  function handleResetFilters() {
    setSelectedRepository(null)
    setSelectedPlaybook(null)
    setSelectedTimeRange("All time")
    setFilterOpen(false)
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>

        {/* Page header */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            marginBottom: 20,
          }}
        >
          <div>
            <h1
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "var(--text)",
                lineHeight: 1.2,
                margin: 0,
              }}
            >
              Runs
            </h1>
            <p
              style={{
                fontSize: 13.5,
                color: "var(--text-muted)",
                marginTop: 4,
                marginBottom: 0,
              }}
            >
              Every agent run across your workspace — live trace, outcome, and duration.
            </p>
          </div>

          <div style={{ marginLeft: "auto", display: "flex", gap: 9 }}>
            {/* Filter button (placeholder — filter is done by chips) */}
            <button
              onClick={() => setFilterOpen(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                height: 34,
                padding: "0 14px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text-2)",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                transition: "background .12s",
                outline: "none",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
              onMouseLeave={e => (e.currentTarget.style.background = "var(--surface)")}
            >
              <svg width={15} height={15} viewBox="0 0 15 15" fill="none" aria-hidden>
                <path d="M1.5 4h12M4 7.5h7M6.5 11h2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
              </svg>
              Filter
            </button>

            <button
              onClick={handleRefresh}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                height: 34,
                padding: "0 14px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text-2)",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                transition: "background .12s",
                outline: "none",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
              onMouseLeave={e => (e.currentTarget.style.background = "var(--surface)")}
            >
              <svg width={15} height={15} viewBox="0 0 15 15" fill="none" aria-hidden>
                <path d="M13 2.5A6.5 6.5 0 1 1 6.5 1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
                <path d="M13 1v3h-3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Refresh
            </button>
          </div>
        </div>

        {/* Filter chips */}
        <div style={{ display: "flex", gap: 7, marginBottom: 16 }}>
          {FILTERS.map(f => (
            <FilterChip
              key={f}
              label={f}
              count={f === "All" ? countFor("All") : undefined}
              active={activeFilter === f}
              onClick={() => setActiveFilter(f)}
            />
          ))}
        </div>

        {/* Runs table / skeleton */}
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1, 2, 3, 4, 5].map(i => (
              <div
                key={i}
                style={{
                  height: 56,
                  borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                  opacity: 0.6,
                }}
                className="animate-pulse"
              />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <div
            style={{
              borderRadius: 12,
              border: "1.5px dashed var(--border-2)",
              padding: "80px 0",
              textAlign: "center",
            }}
          >
            <p style={{ fontWeight: 600, color: "var(--text-2)", marginBottom: 4 }}>No runs yet</p>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Runs are executions of installed agents. Open an agent and trigger a test run.
            </p>
          </div>
        ) : (
          <RunsTable runs={shownRuns} onNavigate={handleNavigate} />
        )}

        {/* Load more */}
        {!loading && hasMore && (
          <div style={{ marginTop: 16, textAlign: "center" }}>
            <button
              onClick={loadMore}
              disabled={loadingMore}
              style={{
                fontSize: 13,
                color: "var(--text-2)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "7px 20px",
                background: "var(--surface)",
                cursor: loadingMore ? "not-allowed" : "pointer",
                opacity: loadingMore ? 0.5 : 1,
                transition: "background .12s",
              }}
              onMouseEnter={e => { if (!loadingMore) e.currentTarget.style.background = "var(--surface-2)" }}
              onMouseLeave={e => { e.currentTarget.style.background = "var(--surface)" }}
            >
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          </div>
        )}

        {/* Filter Panel */}
        <FilterPanel
          isOpen={filterOpen}
          onClose={() => setFilterOpen(false)}
          repositories={repositories}
          playbooks={playbooks}
          selectedRepository={selectedRepository}
          selectedPlaybook={selectedPlaybook}
          selectedTimeRange={selectedTimeRange}
          onRepositoryChange={setSelectedRepository}
          onPlaybookChange={setSelectedPlaybook}
          onTimeRangeChange={setSelectedTimeRange}
          onReset={handleResetFilters}
        />
      </div>
    </AppShell>
  )
}
