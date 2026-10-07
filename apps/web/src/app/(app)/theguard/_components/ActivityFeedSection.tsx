"use client"

import { timeAgo } from "@/lib/runUtils"
import { formatTokensUsed } from "@/components/guard/common/formatTokens"
import { formatToolCall } from "@/components/guard/ActivityRow"
import { DecisionBadge } from "@/components/guard/DecisionBadge"
import { AI_TOOL_BADGES, ALL_DECISIONS, AiToolBadge, formatTokensSaved, selectStyle } from "./widgets"
import type { GuardDashboardState } from "./useGuardDashboard"

const displayEmail = (v: string | null | undefined): string => {
  if (!v) return "—"
  if (v.startsWith("user_")) return "unknown user"
  return v
}

export function ActivityFeedSection({ s }: { s: GuardDashboardState }) {
  const {
    loading,
    filterTool,
    setFilterTool,
    filterDecision,
    setFilterDecision,
    filterDev,
    setFilterDev,
    filterDateRange,
    setFilterDateRange,
    filterSearch,
    setFilterSearch,
    developerEmails,
    toolsInData,
    filteredEvents,
    exportCSV,
  } = s
  return (
    <>
      {/* Filter bar */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <select
          value={filterDateRange}
          onChange={e => setFilterDateRange(e.target.value)}
          style={selectStyle}
        >
          <option value="today">Today</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="all">All time</option>
        </select>

        <select
          value={filterTool}
          onChange={e => setFilterTool(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All tools</option>
          {toolsInData.map(t => (
            <option key={t} value={t}>{AI_TOOL_BADGES[t]?.label ?? t}</option>
          ))}
        </select>

        <select
          value={filterDecision}
          onChange={e => setFilterDecision(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All decisions</option>
          {ALL_DECISIONS.map(d => (
            <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
          ))}
        </select>

        <select
          value={filterDev}
          onChange={e => setFilterDev(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All developers</option>
          {developerEmails.map(email => (
            <option key={email} value={email}>{email}</option>
          ))}
        </select>

        <div style={{ position: "relative" }}>
          <input
            type="text"
            value={filterSearch}
            onChange={e => setFilterSearch(e.target.value)}
            placeholder="Search rule or email…"
            style={{
              ...selectStyle,
              paddingRight: 28,
              width: 192,
            }}
          />
          {filterSearch && (
            <button
              onClick={() => setFilterSearch("")}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                color: "var(--text-muted)",
                fontSize: 12,
                cursor: "pointer",
                padding: 0,
                lineHeight: 1,
              }}
            >✕</button>
          )}
        </div>

        {(filterTool !== "all" || filterDecision !== "all" || filterDev !== "all" || filterSearch) && (
          <button
            onClick={() => { setFilterTool("all"); setFilterDecision("all"); setFilterDev("all"); setFilterSearch("") }}
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "6px 12px",
              background: "var(--surface)",
              cursor: "pointer",
            }}
          >
            Clear filters
          </button>
        )}

        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
          {filteredEvents.length} event{filteredEvents.length !== 1 ? "s" : ""}
        </span>

        {filteredEvents.length > 0 && (
          <button
            onClick={exportCSV}
            style={{
              fontSize: 12,
              color: "var(--text-2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "6px 12px",
              background: "var(--surface)",
              cursor: "pointer",
            }}
          >
            Export CSV
          </button>
        )}
      </div>

      {/* Activity feed */}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{ background: "var(--surface-3)", borderRadius: 12, height: 48 }} />
          ))}
        </div>
      ) : filteredEvents.length === 0 ? (
        <div style={{
          borderRadius: 12,
          border: "1px solid var(--border)",
          background: "var(--surface)",
          padding: "40px 24px",
          textAlign: "center",
          fontSize: 13,
          color: "var(--text-muted)",
        }}>
          No events match the current filters.
        </div>
      ) : (
        <>
          <div style={{ background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)", overflow: "hidden" }}>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {[
                    { label: "Time",     w: 80,   align: "left"  as const },
                    { label: "User",     w: undefined, align: "left"  as const },
                    { label: "AI tool",  w: undefined, align: "left"  as const },
                    { label: "Call",     w: undefined, align: "left"  as const },
                    { label: "Input",    w: undefined, align: "left"  as const },
                    { label: "Decision", w: undefined, align: "left"  as const },
                    { label: "Tokens",   w: undefined, align: "right" as const },
                  ].map(col => (
                    <th
                      key={col.label}
                      style={{
                        padding: "12px 16px",
                        textAlign: col.align,
                        fontWeight: 500,
                        fontSize: 11,
                        color: "var(--text-muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        width: col.w,
                      }}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredEvents.slice(0, 5).map((ev, idx) => (
                  <tr
                    key={ev.id}
                    style={{
                      borderBottom: idx < Math.min(filteredEvents.length, 5) - 1 ? "1px solid var(--border)" : undefined,
                      background: ev.decision === "blocked" ? "var(--err-bg)" : undefined,
                    }}
                  >
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)", fontSize: 12, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                      {timeAgo(ev.ts)}
                    </td>
                    <td style={{ padding: "12px 16px", maxWidth: 160 }}>
                      {ev.user_email ? (
                        <>
                          <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {displayEmail(ev.user_email).split("@")[0]}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={displayEmail(ev.user_email)}>
                            {displayEmail(ev.user_email)}
                          </div>
                        </>
                      ) : (
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <AiToolBadge tool={ev.ai_tool} />
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono, monospace)", fontSize: 12, color: "var(--text-2)", whiteSpace: "nowrap" }}>
                      {formatToolCall(ev.tool_call)}
                    </td>
                    <td
                      style={{ padding: "12px 16px", fontSize: 12, color: "var(--text-3)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "copy", userSelect: "none" }}
                      title={ev.input_summary ? "Double-click to copy" : undefined}
                      onDoubleClick={() => {
                        if (!ev.input_summary) return
                        navigator.clipboard.writeText(ev.input_summary).catch(() => {})
                      }}
                    >
                      {ev.input_summary ?? "—"}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <DecisionBadge decision={ev.decision} />
                      {ev.rule_message && ev.decision !== "allowed" && (
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 120 }} title={ev.rule_message}>
                          {ev.rule_message}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", fontSize: 12, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                      {(() => {
                        const used = formatTokensUsed(ev.tokens_before, ev.tokens_after)
                        if (used) return <span style={{ color: "var(--text-2)" }}>{used}</span>
                        if (ev.tokens_saved && ev.tokens_saved > 0)
                          return <span style={{ color: "var(--ok)" }}>{formatTokensSaved(ev.tokens_saved)} saved</span>
                        return <span style={{ color: "var(--border)" }}>—</span>
                      })()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredEvents.length > 5 && (
            <div style={{ display: "flex", justifyContent: "center", paddingTop: 14, paddingBottom: 6 }}>
              <a
                href="/theguard/activity"
                style={{ fontSize: 13, fontWeight: 500, color: "var(--accent-text)", textDecoration: "none" }}
              >
                View all {filteredEvents.length} events →
              </a>
            </div>
          )}
        </>
      )}
    </>
  )
}
