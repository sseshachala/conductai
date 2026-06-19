"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import StatusBadge from "@/components/runs/StatusBadge"
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

function FilterChip({ label, count, active, onClick }: FilterChipProps) {
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
        onClick={e => e.stopPropagation()}
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

type FilterLabel = "All" | "Running" | "Succeeded" | "Awaiting" | "Failed"
type TimeRangeLabel = "Last 24 hours" | "Last 7 days" | "Last 30 days" | "All time"

const FILTERS: FilterLabel[] = ["All", "Running", "Succeeded", "Awaiting", "Failed"]
const TIME_RANGES: TimeRangeLabel[] = ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"]

function matchesFilter(run: Run, filter: FilterLabel): boolean {
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
                onClick={e => e.stopPropagation()}
                style={{ fontSize: 11.5, color: "var(--text-3)", fontWeight: 500, whiteSpace: "nowrap", textDecoration: "none", flexShrink: 0 }}
                onMouseEnter={e => (e.currentTarget.style.color = "var(--accent-text)")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
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
        <StatusBadge status={run.status} />
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

function RunsTable({ runs }: RunsTableProps) {
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
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [activeStatus, setActiveStatus] = useState<FilterLabel>("All")
  const [filterOpen, setFilterOpen] = useState(false)
  const [selectedRepository, setSelectedRepository] = useState<string | null>(null)
  const [selectedPlaybook, setSelectedPlaybook] = useState<string | null>(null)
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRangeLabel>("All time")
  // searchQuery drives the visible input; debouncedQuery fires the fetch (#5)
  const [searchQuery, setSearchQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Track whether this is the initial mount to avoid double-load
  const didMountRef = useRef(false)

  function handleSearchChange(value: string) {
    setSearchQuery(value)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      setDebouncedQuery(value)
    }, 400)
  }

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

    if (selectedRepository && selectedRepository !== "All repositories") {
      params.append("repository", selectedRepository)
    }
    if (selectedPlaybook && selectedPlaybook !== "All playbooks") {
      params.append("workflow_name", selectedPlaybook)
    }
    if (debouncedQuery.trim()) {
      params.append("q", debouncedQuery.trim())
    }
    if (selectedTimeRange !== "All time") {
      const now = new Date()
      let daysBack = 7
      if (selectedTimeRange === "Last 24 hours") daysBack = 1
      else if (selectedTimeRange === "Last 7 days") daysBack = 7
      else if (selectedTimeRange === "Last 30 days") daysBack = 30
      const afterDate = new Date(now.getTime() - daysBack * 24 * 60 * 60 * 1000)
      params.append("created_after", afterDate.toISOString())
    }

    return `${process.env.NEXT_PUBLIC_API_URL}/runs?${params.toString()}`
  }

  // load() is stable — defined outside effect so Retry button can call it too (#1)
  async function load() {
    setLoading(true)
    setError(null)
    const headers = await buildHeaders()
    try {
      const url = buildRunsUrl(0)
      const res = await fetch(url, { headers })
      if (res.ok) {
        const data: Run[] = await res.json()
        setRuns(data)
        setHasMore(data.length === PAGE_SIZE)
        setOffset(PAGE_SIZE)
      } else {
        setError(`Failed to load runs (${res.status})`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs")
    } finally {
      setLoading(false)
    }
  }

  // When server-side filters change, reset client chips and reload (#8)
  useEffect(() => {
    setActiveStatus("All")
    setSearchQuery("")
    setDebouncedQuery("")
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepository, selectedPlaybook, selectedTimeRange])

  // When debounced search changes, reload (skip initial mount to avoid double-load)
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true
      return
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const headers = await buildHeaders()
      const url = buildRunsUrl(offset)
      const res = await fetch(url, { headers })
      if (res.ok) {
        const data: Run[] = await res.json()
        if (data.length === 0) {
          // Exact-multiple edge-case (#6): server returned nothing on next page
          setHasMore(false)
        } else {
          setRuns(prev => [...prev, ...data])
          setHasMore(data.length === PAGE_SIZE)
          setOffset(o => o + PAGE_SIZE)
        }
      }
    } finally {
      setLoadingMore(false)
    }
  }

  // Keep existing data visible during refresh — don't clear upfront (#2)
  async function handleRefresh() {
    setLoading(true)
    setError(null)
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
      } else {
        setError(`Failed to refresh (${res.status})`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh")
    } finally {
      setLoading(false)
    }
  }

  // Extract unique repositories and playbooks from loaded data
  const repositories = Array.from(new Set(runs.map(r => r.repo).filter(Boolean))).sort() as string[]
  const playbooks = Array.from(new Set(runs.map(r => r.workflow_name))).sort()

  // Client-side filter: status chips only (search is server-side now)
  const shownRuns = runs.filter(r => matchesFilter(r, activeStatus))

  // Counts for all chips (#10)
  const countFor = (f: FilterLabel) => {
    if (f === "All") return runs.length
    return runs.filter(r => matchesFilter(r, f)).length
  }

  function handleResetFilters() {
    setSelectedRepository(null)
    setSelectedPlaybook(null)
    setSelectedTimeRange("All time")
    setFilterOpen(false)
  }

  // needsAttention imported for consumers of this module — suppress lint
  void needsAttention
  void isActive

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

        {/* Error state with Retry (#1) */}
        {error && !loading && (
          <div
            style={{
              marginBottom: 16,
              padding: "12px 16px",
              borderRadius: 8,
              background: "var(--err-bg)",
              border: "1px solid var(--err)",
              color: "var(--err)",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <span>{error}</span>
            <button
              onClick={load}
              style={{
                fontSize: 12,
                fontWeight: 600,
                padding: "4px 12px",
                borderRadius: 6,
                border: "1px solid var(--err)",
                background: "transparent",
                color: "var(--err)",
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Search + status filter chips (#17 aria-label, #18 aria-pressed) */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <input
            type="search"
            aria-label="Search runs"
            placeholder="Search by agent or project…"
            value={searchQuery}
            onChange={e => handleSearchChange(e.target.value)}
            style={{
              height: 32, padding: "0 12px", borderRadius: 8, fontSize: 13,
              border: "1px solid var(--border)", background: "var(--surface)",
              color: "var(--text)", outline: "none", width: 220,
            }}
          />
          <div style={{ display: "flex", gap: 7 }}>
            {FILTERS.map(f => (
              <FilterChip
                key={f}
                label={f}
                count={countFor(f)}
                active={activeStatus === f}
                onClick={() => setActiveStatus(f)}
              />
            ))}
          </div>
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
        ) : runs.length === 0 && !error ? (
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
          <RunsTable runs={shownRuns} />
        )}

        {/* Run count + Load more (#19, #6) */}
        {!loading && runs.length > 0 && (
          <div style={{ marginTop: 16, display: "flex", alignItems: "center", justifyContent: "center", gap: 16, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {`Showing ${runs.length} run${runs.length !== 1 ? "s" : ""}${hasMore ? " — load more to see all" : ""}`}
            </span>
            {hasMore && (
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
            )}
          </div>
        )}

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
