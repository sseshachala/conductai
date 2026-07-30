"use client"

import { useEffect, useMemo, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type {
  EnforcementStatus,
  GuardEnforcementCoverage,
} from "@/lib/api/guard"

const PAGE_SIZE = 25

const STATUS_META: Record<EnforcementStatus, { label: string; colour: string; background: string; border: string }> = {
  hard: {
    label: "Hard",
    colour: "var(--success, #15803d)",
    background: "var(--success-bg, #f0fdf4)",
    border: "var(--success-bd, #bbf7d0)",
  },
  conditional: {
    label: "Conditional",
    colour: "var(--warn)",
    background: "var(--warn-bg)",
    border: "var(--warn-bd, #fde68a)",
  },
  advisory: {
    label: "Advisory",
    colour: "var(--info)",
    background: "var(--info-bg)",
    border: "var(--info-bd, #bfdbfe)",
  },
  not_supported: {
    label: "Not supported",
    colour: "var(--text-muted)",
    background: "var(--surface-2)",
    border: "var(--border)",
  },
}

function StatusBadge({ status }: { status: EnforcementStatus }) {
  const meta = STATUS_META[status]
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      minWidth: 74,
      padding: "3px 7px",
      borderRadius: 999,
      border: `1px solid ${meta.border}`,
      background: meta.background,
      color: meta.colour,
      fontSize: 10.5,
      fontWeight: 650,
      whiteSpace: "nowrap",
    }}>
      {meta.label}
    </span>
  )
}

function formatAction(action: string): string {
  return action.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase())
}

function formatExceptionExpiry(value: string | null): string {
  if (!value) return "No expiry recorded"
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value))
  } catch {
    return value
  }
}

function DetailLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      marginBottom: 5,
      color: "var(--text-muted)",
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: ".06em",
      textTransform: "uppercase",
    }}>
      {children}
    </div>
  )
}

function CoverageDetails({ row }: { row: GuardEnforcementCoverage }) {
  const hasException = row.exception_active || row.exception_expired
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
      gap: 16,
      padding: "14px 16px",
      background: "var(--surface-2)",
      borderTop: "1px solid var(--border)",
    }}>
      <div>
        <DetailLabel>Rule metadata</DetailLabel>
        <div style={{ display: "grid", gap: 5, fontSize: 12, color: "var(--text-2)" }}>
          <span>Pack: <strong>{row.pack ?? "Custom"}</strong>{row.pack_version ? ` · v${row.pack_version}` : ""}</span>
          <span>Personas: <strong>{row.personas.length ? row.personas.join(", ") : "None specified"}</strong></span>
          <span>Action: <strong>{formatAction(row.action)}</strong>{row.action !== row.base_action ? ` (base: ${formatAction(row.base_action)})` : ""}</span>
          <span>State: <strong>{row.enabled ? "Enabled" : "Disabled"}</strong> · Contract v{row.enforcement_version}</span>
        </div>
      </div>

      <div>
        <DetailLabel>Requirements</DetailLabel>
        {row.requires.length ? (
          <ul style={{ margin: 0, paddingLeft: 17, color: "var(--text-2)", fontSize: 12, lineHeight: 1.55 }}>
            {row.requires.map(requirement => <li key={requirement}>{requirement}</li>)}
          </ul>
        ) : <span style={{ color: "var(--text-muted)", fontSize: 12 }}>No additional requirements.</span>}
      </div>

      <div>
        <DetailLabel>Known limitations</DetailLabel>
        {row.known_limitations.length ? (
          <ul style={{ margin: 0, paddingLeft: 17, color: "var(--text-2)", fontSize: 12, lineHeight: 1.55 }}>
            {row.known_limitations.map(limitation => <li key={limitation}>{limitation}</li>)}
          </ul>
        ) : <span style={{ color: "var(--text-muted)", fontSize: 12 }}>No known limitations listed.</span>}
      </div>

      {hasException && (
        <div style={{
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${row.exception_active ? "var(--warn-bd, #fde68a)" : "var(--err-bd)"}`,
          background: row.exception_active ? "var(--warn-bg)" : "var(--err-bg)",
        }}>
          <DetailLabel>Policy exception</DetailLabel>
          <div style={{ display: "grid", gap: 5, fontSize: 12, color: "var(--text-2)" }}>
            <strong style={{ color: row.exception_active ? "var(--warn)" : "var(--err)" }}>
              {row.exception_active ? "Active" : "Expired"}
            </strong>
            {row.exception_reason && <span>Reason: {row.exception_reason}</span>}
            <span>Expiry: {formatExceptionExpiry(row.exception_expires_at)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export function EnforcementCoverageMatrix({ workspaceId }: { workspaceId: string | null }) {
  const { authFetch } = useAuthFetch()
  const [rows, setRows] = useState<GuardEnforcementCoverage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState("")
  const [pack, setPack] = useState("all")
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [expandedRuleIds, setExpandedRuleIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!workspaceId) {
        setRows([])
        setLoading(false)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const data = await guard.policies.coverage(authFetch, workspaceId)
        if (!cancelled) setRows(data)
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load enforcement coverage.")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [authFetch, workspaceId])

  const packs = useMemo(
    () => [...new Set(rows.map(row => row.pack ?? "custom"))].sort(),
    [rows],
  )

  const filteredRows = useMemo(() => {
    const normalisedQuery = query.trim().toLowerCase()
    return rows.filter(row => {
      const rowPack = row.pack ?? "custom"
      if (pack !== "all" && rowPack !== pack) return false
      if (!normalisedQuery) return true
      return [
        row.rule_id,
        row.name,
        row.pack ?? "custom",
        row.guarantee,
        ...row.personas,
      ].some(value => value.toLowerCase().includes(normalisedQuery))
    })
  }, [pack, query, rows])

  const visibleRows = filteredRows.slice(0, visibleCount)

  function updateFilter(update: () => void) {
    update()
    setVisibleCount(PAGE_SIZE)
  }

  function toggleRule(ruleId: string) {
    setExpandedRuleIds(current => {
      const next = new Set(current)
      next.has(ruleId) ? next.delete(ruleId) : next.add(ruleId)
      return next
    })
  }

  if (loading) {
    return (
      <div className="card" style={{ padding: "48px 24px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
        Loading enforcement coverage…
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ borderRadius: 10, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "12px 16px", fontSize: 13, color: "var(--err)" }}>
        {error}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>No enforcement coverage metadata is available for this workspace.</p>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, color: "var(--text)", fontSize: 16, fontWeight: 700 }}>Enforcement coverage</h2>
        <p style={{ margin: "5px 0 0", color: "var(--text-3)", fontSize: 12.5, lineHeight: 1.5 }}>
          Evidence generated from the installed rule metadata. <strong style={{ color: "var(--text-2)" }}>Hard</strong> means prevention once traffic reaches that surface; it does not imply universal coverage.
        </p>
      </div>

      <div className="card" style={{ padding: 12, marginBottom: 12 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          <input
            type="search"
            value={query}
            onChange={event => updateFilter(() => setQuery(event.target.value))}
            placeholder="Search rules, guarantees or personas"
            aria-label="Search enforcement coverage"
            style={{ ...fieldStyle, flex: "1 1 260px" }}
          />
          <select
            value={pack}
            onChange={event => updateFilter(() => setPack(event.target.value))}
            aria-label="Filter by pack"
            style={{ ...fieldStyle, width: "auto", minWidth: 180 }}
          >
            <option value="all">All packs ({rows.length})</option>
            {packs.map(packName => (
              <option key={packName} value={packName}>
                {packName === "custom" ? "Custom" : packName} ({rows.filter(row => (row.pack ?? "custom") === packName).length})
              </option>
            ))}
          </select>
          <span style={{ color: "var(--text-muted)", fontSize: 11.5, whiteSpace: "nowrap" }}>
            {filteredRows.length} {filteredRows.length === 1 ? "rule" : "rules"}
          </span>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
          {(Object.keys(STATUS_META) as EnforcementStatus[]).map(status => (
            <div key={status} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <StatusBadge status={status} />
              <span style={{ color: "var(--text-muted)", fontSize: 10.5 }}>
                {status === "hard" ? "prevents" : status === "conditional" ? "depends on requirements" : status === "advisory" ? "signals only" : "not enforced"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {filteredRows.length === 0 ? (
        <div className="card" style={{ padding: "32px 24px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
          No rules match these filters.
        </div>
      ) : (
        <>
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", minWidth: 880, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                    {["Rule", "Proxy", "Hook", "MCP", "Runtime", "Guarantee"].map((heading, index) => (
                      <th key={heading} style={{
                        padding: "9px 12px",
                        textAlign: index === 0 || index === 5 ? "left" : "center",
                        color: "var(--text-muted)",
                        fontSize: 10.5,
                        fontWeight: 700,
                        letterSpacing: ".05em",
                        textTransform: "uppercase",
                        width: index === 0 ? "25%" : index === 5 ? "31%" : "11%",
                      }}>
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map(row => {
                    const expanded = expandedRuleIds.has(row.rule_id)
                    return (
                      <FragmentRow
                        key={row.rule_id}
                        row={row}
                        expanded={expanded}
                        onToggle={() => toggleRule(row.rule_id)}
                      />
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
          {visibleCount < filteredRows.length && (
            <div style={{ display: "flex", justifyContent: "center", paddingTop: 12 }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setVisibleCount(count => count + PAGE_SIZE)}>
                Show {Math.min(PAGE_SIZE, filteredRows.length - visibleCount)} more
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function FragmentRow({
  row,
  expanded,
  onToggle,
}: {
  row: GuardEnforcementCoverage
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr
        style={{ borderBottom: expanded ? 0 : "1px solid var(--border)", opacity: row.enabled ? 1 : 0.58 }}
      >
        <td style={{ padding: "10px 12px" }}>
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 8,
              width: "100%",
              padding: 0,
              border: 0,
              background: "transparent",
              textAlign: "left",
              cursor: "pointer",
            }}
          >
            <span style={{ color: "var(--text-muted)", fontSize: 11, transform: expanded ? "rotate(90deg)" : "none", transition: "transform .15s", marginTop: 2 }}>›</span>
            <div style={{ minWidth: 0 }}>
              <div className="mono" style={{ color: "var(--text)", fontSize: 11.5, fontWeight: 650 }}>{row.rule_id}</div>
              <div style={{ marginTop: 2, color: "var(--text-3)", fontSize: 11.5, lineHeight: 1.35 }}>{row.name}</div>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 5 }}>
                {!row.enabled && <span className="sbadge">Disabled</span>}
                {row.exception_active && <span className="sbadge warn">Exception active</span>}
                {row.exception_expired && <span className="sbadge err">Exception expired</span>}
              </div>
            </div>
          </button>
        </td>
        <td style={statusCellStyle}><StatusBadge status={row.proxy} /></td>
        <td style={statusCellStyle}><StatusBadge status={row.hook} /></td>
        <td style={statusCellStyle}><StatusBadge status={row.mcp} /></td>
        <td style={statusCellStyle}><StatusBadge status={row.runtime} /></td>
        <td style={{ padding: "10px 12px", color: "var(--text-2)", fontSize: 11.5, lineHeight: 1.45 }}>{row.guarantee}</td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid var(--border)" }}>
          <td colSpan={6} style={{ padding: 0 }}><CoverageDetails row={row} /></td>
        </tr>
      )}
    </>
  )
}

const fieldStyle: React.CSSProperties = {
  borderRadius: 8,
  border: "1px solid var(--border)",
  padding: "7px 10px",
  fontSize: 12.5,
  color: "var(--text)",
  background: "var(--surface)",
  outline: "none",
  boxSizing: "border-box",
}

const statusCellStyle: React.CSSProperties = {
  padding: "10px 8px",
  textAlign: "center",
}
