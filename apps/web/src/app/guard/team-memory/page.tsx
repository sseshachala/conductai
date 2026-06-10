"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import { usePathname } from "next/navigation"
import AppShell from "@/components/AppShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface MemoryEntry {
  developer_id: string | null
  repo: string | null
  summary: string
  tags: string[]
  tool: string
  confidence: number
  created_at: string
  distance: number | null
}

// ─── Guard Shell ──────────────────────────────────────────────────────────────

const GUARD_TABS = [
  { href: "/guard",             label: "Overview"     },
  { href: "/guard/spend",       label: "Spend"        },
  { href: "/guard/policies",    label: "Policies"     },
  { href: "/guard/activity",    label: "Activity"     },
  { href: "/guard/team-memory", label: "Team Memory"  },
  { href: "/guard/settings",    label: "Settings"     },
]

function GuardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
              Guard
            </h1>
            <span className="sbadge ok" style={{ marginTop: 2 }}>
              <span className="conduct-pulse-dot" />
              live
            </span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
            MDM for AI coding tools — policies and spend limits enforced on every Claude Code, Codex, and Cursor call.
          </p>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
          last updated: just now
        </div>
      </div>
      <div className="guard-tab-nav">
        {GUARD_TABS.map(tab => {
          const isActive = tab.href === "/guard"
            ? pathname === "/guard"
            : pathname?.startsWith(tab.href)
          return (
            <Link key={tab.href} href={tab.href} className={`guard-tab${isActive ? " active" : ""}`}>
              {tab.label}
            </Link>
          )
        })}
      </div>
      {children}
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(ts: string): string {
  try {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  } catch {
    return ts
  }
}

function truncateDeveloperId(id: string | null): string {
  if (!id) return "—"
  if (id.length <= 20) return id
  return `${id.slice(0, 12)}…${id.slice(-6)}`
}

// ─── Memory card ─────────────────────────────────────────────────────────────

function MemoryCard({ entry }: { entry: MemoryEntry }) {
  return (
    <div
      className="card"
      style={{
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      {/* Summary */}
      <p
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: "var(--text)",
          margin: 0,
          lineHeight: 1.5,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {entry.summary}
      </p>

      {/* Tags */}
      {entry.tags.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          {entry.tags.map(tag => (
            <span
              key={tag}
              style={{
                fontSize: 11,
                fontWeight: 500,
                color: "var(--accent-text)",
                background: "var(--accent-weak)",
                borderRadius: 5,
                padding: "2px 7px",
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
          borderTop: "1px solid var(--border)",
          paddingTop: 8,
          marginTop: 2,
        }}
      >
        <span
          className="mono"
          style={{ fontSize: 11, color: "var(--text-muted)" }}
          title={entry.developer_id ?? "unknown"}
        >
          {truncateDeveloperId(entry.developer_id)}
        </span>

        {entry.repo && (
          <>
            <span style={{ color: "var(--border)", userSelect: "none" }}>·</span>
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>
              {entry.repo}
            </span>
          </>
        )}

        <span style={{ color: "var(--border)", userSelect: "none" }}>·</span>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {formatDate(entry.created_at)}
        </span>

        {entry.distance != null && (
          <>
            <span style={{ color: "var(--border)", userSelect: "none" }}>·</span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              relevance {(1 - entry.distance).toFixed(2)}
            </span>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Skeleton card ────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div
      className="card"
      style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}
    >
      <div style={{ height: 14, background: "var(--surface-2)", borderRadius: 5, width: "90%", opacity: 0.7 }} />
      <div style={{ height: 14, background: "var(--surface-2)", borderRadius: 5, width: "65%", opacity: 0.5 }} />
      <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
        {[40, 56, 48].map((w, i) => (
          <div key={i} style={{ height: 20, width: w, background: "var(--surface-2)", borderRadius: 5, opacity: 0.5 }} />
        ))}
      </div>
      <div style={{ height: 1, background: "var(--border)", marginTop: 2 }} />
      <div style={{ height: 11, background: "var(--surface-2)", borderRadius: 4, width: "50%", opacity: 0.4 }} />
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function TeamMemoryPage() {
  return <AppShell><TeamMemoryContent /></AppShell>
}

function TeamMemoryContent() {
  const { getToken } = useAuth()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()

  const [entries, setEntries] = useState<MemoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [inputValue, setInputValue] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const workspaceId = activeWorkspace?.id ?? teamId ?? null

  const load = useCallback(async (q: string) => {
    if (!workspaceId) return
    setLoading(true)
    setError(null)

    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`

    const params = new URLSearchParams({
      q: q.trim() || "recent",
      limit: "20",
    })
    if (workspaceId) params.set("workspace_id", workspaceId)

    try {
      const res = await fetch(`${base}/team-memory/search?${params.toString()}`, { headers })
      if (!res.ok) throw new Error(`Failed to load team memories (${res.status})`)
      const data: MemoryEntry[] = await res.json()
      setEntries(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [getToken, workspaceId])

  // Initial load and when query changes
  useEffect(() => {
    if (!teamLoading && !workspaceId) {
      setLoading(false)
      return
    }
    if (workspaceId) {
      load(query)
    }
  }, [load, query, teamLoading, workspaceId])

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    setInputValue(val)

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setQuery(val)
    }, 400)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (debounceRef.current) clearTimeout(debounceRef.current)
    setQuery(inputValue)
  }

  function handleClear() {
    setInputValue("")
    setQuery("")
    if (debounceRef.current) clearTimeout(debounceRef.current)
  }

  return (
    <GuardShell>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>Team Memory</div>
          <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>
            AI coding session summaries captured automatically when developers exit Claude Code.
          </div>
        </div>
      </div>

      {/* Search bar */}
      <form
        onSubmit={handleSubmit}
        style={{ display: "flex", gap: 8, marginBottom: 20 }}
      >
        <input
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          placeholder="Search memories — e.g. authentication, bug fix, deployment…"
          style={{
            flex: 1,
            fontSize: 13,
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "8px 14px",
            color: "var(--text)",
            background: "var(--surface)",
            outline: "none",
          }}
        />
        {inputValue && (
          <button
            type="button"
            onClick={handleClear}
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              background: "none",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "8px 12px",
              cursor: "pointer",
            }}
          >
            Clear
          </button>
        )}
        <button
          type="submit"
          className="btn btn-primary btn-sm"
          style={{ padding: "8px 18px", fontSize: 13 }}
        >
          Search
        </button>
      </form>

      {/* Error */}
      {error && (
        <div
          style={{
            borderRadius: 8,
            border: "1px solid var(--err-bd)",
            background: "var(--err-bg)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--err)",
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: 12,
          }}
        >
          {[...Array(6)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : entries.length === 0 ? (
        <div
          className="card"
          style={{ padding: "48px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}
        >
          {query
            ? `No memories found for "${query}". Try a different search term.`
            : "No team memories yet. Sessions are captured automatically when developers exit Claude Code."
          }
        </div>
      ) : (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
              gap: 12,
            }}
          >
            {entries.map((entry, i) => (
              <MemoryCard key={`${entry.developer_id ?? "anon"}-${entry.created_at}-${i}`} entry={entry} />
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: "var(--text-muted)", textAlign: "center" }}>
            {entries.length} {entries.length === 1 ? "memory" : "memories"}{query ? ` matching "${query}"` : ""}
          </div>
        </>
      )}
    </GuardShell>
  )
}
