"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"

// ─── Types ────────────────────────────────────────────────────────────────────

interface MemoryEntry {
  developer_id: string | null
  developer_email: string | null
  repo: string | null
  summary: string
  tags: string[]
  tool: string
  confidence: number
  created_at: string
  distance: number | null
}


// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTs(ts: string): string {
  try {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  } catch {
    return ts
  }
}

const selectStyle: React.CSSProperties = {
  fontSize: 12,
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "5px 10px",
  color: "var(--text-2)",
  background: "var(--surface)",
  outline: "none",
  cursor: "pointer",
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function TeamMemoryPage() {
  return <AppShell><TeamMemoryContent /></AppShell>
}

function TeamMemoryContent() {
  const { getToken } = useAuth()
  const { user } = useUser()
  const { teamId, loading: teamLoading } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()

  const [entries, setEntries] = useState<MemoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)
  const [inputValue, setInputValue] = useState("")
  const [query, setQuery] = useState("")
  const [filterDeveloper, setFilterDeveloper] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const workspaceId = activeWorkspace?.id ?? teamId ?? null
  const { permissions, loading: roleLoading } = useGuardRole(teamId, workspaceId)
  const currentUserEmail = user?.primaryEmailAddress?.emailAddress ?? null
  const developers = Array.from(new Set(entries.map(e => e.developer_email).filter(Boolean) as string[])).sort()

  const load = useCallback(async (q: string) => {
    if (!workspaceId) return
    setLoading(true)
    setError(null)

    const token = await getToken()
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`

    const trimmed = q.trim()
    const params = new URLSearchParams({ limit: "50" })
    if (trimmed) params.set("q", trimmed)
    params.set("workspace_id", workspaceId)

    try {
      const res = await fetch(`${base}/team-memory/search?${params.toString()}`, { headers })
      if (!res.ok) throw new Error(`Failed to load team memories (${res.status})`)
      const data: MemoryEntry[] = await res.json()
      data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      setEntries(data)
      setLastFetched(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [getToken, workspaceId])

  useEffect(() => {
    if (!teamLoading && !workspaceId) { setLoading(false); return }
    if (workspaceId) load(query)
  }, [load, query, teamLoading, workspaceId])

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    setInputValue(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setQuery(val), 400)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (debounceRef.current) clearTimeout(debounceRef.current)
    setQuery(inputValue)
  }

  // Non-admins can only see their own sessions
  const effectiveDeveloper = !permissions.canViewAllActivity && currentUserEmail
    ? currentUserEmail
    : filterDeveloper
  const filtered = effectiveDeveloper
    ? entries.filter(e => e.developer_email === effectiveDeveloper)
    : entries

  const isSearching = query.trim().length > 0

  return (
    <GuardShell lastFetched={lastFetched}>
      {/* Filters — same layout as Activity page */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16, flexWrap: "wrap" }}>
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, flex: 1, minWidth: 260 }}>
          <input
            type="text"
            value={inputValue}
            onChange={handleInputChange}
            placeholder="Search sessions — e.g. auth bug, deployment fix…"
            style={{ ...selectStyle, flex: 1, padding: "5px 12px" }}
          />
          {inputValue && (
            <button type="button" onClick={() => { setInputValue(""); setQuery("") }}
              style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
              Clear
            </button>
          )}
        </form>

        {permissions.canViewAllActivity && (
          <select value={filterDeveloper} onChange={e => setFilterDeveloper(e.target.value)} style={selectStyle}>
            <option value="">All developers</option>
            {developers.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}

        {filterDeveloper && (
          <button onClick={() => setFilterDeveloper("")}
            style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
            Clear filters
          </button>
        )}

        <span style={{ marginLeft: "auto", fontSize: 12.5, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="conduct-pulse-dot" style={{ background: "var(--ok)" }} />
          Captured on session exit
        </span>
      </div>

      {!roleLoading && !permissions.canViewAllActivity && (
        <div style={{ borderRadius: 8, border: "1px solid var(--warn-bd)", background: "var(--warn-bg)", padding: "8px 16px", fontSize: 12, color: "var(--warn)", marginBottom: 16 }}>
          You can view your own sessions only. Contact your admin to request broader access.
        </div>
      )}

      {error && (
        <div style={{ borderRadius: 8, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!isSearching && (
        <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
          Recent sessions
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{ height: 44, background: "var(--surface-2)", borderRadius: 8, opacity: 0.6 }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card" style={{ padding: "40px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
          {isSearching
            ? `No sessions found for "${query}".`
            : "No team memories yet. Sessions are captured automatically when developers exit Claude Code, Cursor, and Codex."
          }
        </div>
      ) : (
        <div className="card" style={{ overflow: "hidden" }}>
          {/* Table header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "1.1fr 0.8fr 2.6fr 0.7fr 1fr 0.6fr",
            gap: 12, padding: "10px 18px",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface-2)",
          }}>
            {["Developer", "Repo", "Summary", "Tool", "Tags", "Date"].map(h => (
              <div key={h} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
            ))}
          </div>

          {/* Table rows */}
          {filtered.map((entry, i) => {
            const extraTagCount = (entry.tags ?? []).length > 3 ? (entry.tags ?? []).length - 3 : 0
            const confidencePct = entry.confidence != null ? Math.round(entry.confidence * 100) : null

            return (
              <div key={`${entry.developer_id}-${entry.created_at}-${i}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1.1fr 0.8fr 2.6fr 0.7fr 1fr 0.6fr",
                  gap: 12, padding: "11px 18px",
                  borderBottom: i < filtered.length - 1 ? "1px solid var(--border)" : "none",
                  alignItems: "start",
                }}
              >
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {entry.developer_email ?? "—"}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {entry.repo ?? "—"}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--text)", lineHeight: 1.5 }}>
                  {entry.summary}
                  {confidencePct !== null && (
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 4 }}>
                      <div style={{ width: 48, height: 3, borderRadius: 2, background: "var(--border-2)", overflow: "hidden" }}>
                        <div style={{ width: `${confidencePct}%`, height: "100%", background: confidencePct >= 75 ? "var(--ok)" : confidencePct >= 40 ? "var(--warn)" : "var(--err)", borderRadius: 2 }} />
                      </div>
                      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{confidencePct}%</span>
                    </div>
                  )}
                </div>
                <div>
                  {entry.tool && (
                    <span style={{
                      fontSize: 10, fontWeight: 500,
                      color: "var(--text-2)", background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 4, padding: "1px 6px",
                      display: "inline-block",
                    }}>{entry.tool}</span>
                  )}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {(entry.tags ?? []).slice(0, 3).map(tag => (
                    <span key={tag} style={{
                      fontSize: 10, fontWeight: 500,
                      color: "var(--accent-text)", background: "var(--accent-weak)",
                      borderRadius: 4, padding: "1px 6px",
                    }}>{tag}</span>
                  ))}
                  {extraTagCount > 0 && (
                    <span style={{
                      fontSize: 10, fontWeight: 500,
                      color: "var(--text-muted)", background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 4, padding: "1px 6px",
                    }}>+{extraTagCount}</span>
                  )}
                </div>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                  {formatTs(entry.created_at)}
                </div>
              </div>
            )
          })}

          <div style={{ borderTop: "1px solid var(--border)", padding: "8px 18px", textAlign: "center", fontSize: 12, color: "var(--text-muted)" }}>
            {filtered.length} {filtered.length === 1 ? "session" : "sessions"}
          </div>
        </div>
      )}
    </GuardShell>
  )
}
