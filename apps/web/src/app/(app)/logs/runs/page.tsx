"use client"

import { authEnabled } from "@/lib/auth/runtime"


import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import AppShell from "@/components/AppShell"
import { needsAttention, isActive } from "@/lib/runUtils"
import { useWorkspace } from "@/lib/WorkspaceContext"
import {
  FilterChip,
  FilterPanel,
  FILTERS,
  matchesFilter,
  RunsTable,
  type FilterLabel,
  type Run,
  type TimeRangeLabel,
} from "./_components/RunsTable"

export default function RunsPage() {
  const clerkEnabled = authEnabled()
  if (clerkEnabled) return <RunsWithAuth />
  return <RunsContent getToken={null} />
}

function RunsWithAuth() {
  const { getToken } = useAuth()
  return <RunsContent getToken={getToken} />
}

const PAGE_SIZE = 50

function RunsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
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
    const wsId = activeWorkspace?.id ?? null
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

    return `${API}/runs?${params.toString()}`
  }

  // load() is stable — defined outside effect so Retry button can call it too (#1)
  async function load() {
    setLoading(true)
    setError(null)
    try {
      const url = buildRunsUrl(0)
      const res = await authFetch(url)
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
      const url = buildRunsUrl(offset)
      const res = await authFetch(url)
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
    try {
      const url = buildRunsUrl(0)
      const res = await authFetch(url)
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
              onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-2)")}
              onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface)")}
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
              onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-2)")}
              onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface)")}
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
                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { if (!loadingMore) e.currentTarget.style.background = "var(--surface-2)" }}
                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { e.currentTarget.style.background = "var(--surface)" }}
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
