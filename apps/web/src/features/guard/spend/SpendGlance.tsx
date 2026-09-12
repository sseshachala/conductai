"use client"

// Spend at a glance — the metric surface (currency + month picker,
// stat cards, RTK + Booster savings, By-developer table, By-AI-tool
// table). Rendered in-page on /theguard as the "Spend at a glance"
// view; also composable anywhere else that needs the same numbers.
//
// Owns nothing — pulls everything from useSpendState() so /theguard
// (glance view) and any future callers stay in sync.

import { ByAiToolTable } from "@/components/guard/ByAiToolTable"
import { GuardSectionHeader } from "@/components/guard/common"
import {
  BudgetBar,
  BudgetInput,
  MonthPicker,
} from "./components"
import {
  CURRENCY_SYMBOLS,
  TOOL_LABELS,
  formatTokens,
  fromUsd,
  type Currency,
} from "./shared"
import { useSpendState } from "./useSpendState"

export function SpendGlance() {
  const s = useSpendState()

  if (!s.roleLoading && !s.canViewSpend) {
    return (
      <div className="card" style={{ padding: "64px 24px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
        You don&apos;t have access to spend data. Contact your admin.
      </div>
    )
  }

  return (
    <>
      {/* Currency + month picker */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, marginBottom: 20 }}>
        <select
          value={s.currency}
          onChange={e => s.setCurrency(e.target.value as Currency)}
          style={{
            fontSize: 12,
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "5px 10px",
            color: "var(--text-3)",
            background: "var(--surface)",
            outline: "none",
            cursor: "pointer",
          }}
        >
          <option value="USD">$ USD</option>
          <option value="EUR">€ EUR</option>
          <option value="INR">₹ INR</option>
        </select>
        <MonthPicker value={s.month} onChange={s.setMonth} />
      </div>

      {s.error && (
        <div style={{
          borderRadius: 8,
          background: "var(--err-bg)",
          border: "1px solid var(--err-bd)",
          padding: "10px 16px",
          fontSize: 13,
          color: "var(--err)",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}>
          <span style={{ flex: 1 }}>{s.error}</span>
          <button
            onClick={s.load}
            style={{ fontSize: 12, fontWeight: 600, background: "var(--err)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 12px", cursor: "pointer", flexShrink: 0 }}
          >
            Retry
          </button>
        </div>
      )}

      {s.loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card" style={{ height: 80, opacity: 0.5 }} />
          ))}
        </div>
      ) : s.data ? (
        <>
          <GuardSectionHeader title={`Spend for ${s.monthLabel}`} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
            {([
              [`${CURRENCY_SYMBOLS[s.currency]}${fromUsd(s.data.total_cost_usd, s.currency).toFixed(2)}`, "Est. cost this month", "plain"],
              [formatTokens(s.data.total_tokens_after), "Tokens used", "ok"],
              [`${CURRENCY_SYMBOLS[s.currency]}${fromUsd(s.data.total_cost_usd + s.data.total_saved_usd, s.currency).toFixed(0)}`, "Est. cost without Guard", "plain"],
              [`${CURRENCY_SYMBOLS[s.currency]}${fromUsd(s.data.total_saved_usd, s.currency).toFixed(0)}`, "Est. savings", "accent"],
            ] as const).map(([v, k, tone], i) => (
              <div key={i} className="card" style={{ padding: "16px 20px" }}>
                <div style={{
                  fontSize: 24,
                  fontWeight: 700,
                  letterSpacing: "-.02em",
                  color: tone === "ok" ? "var(--ok)" : tone === "accent" ? "var(--accent-text)" : "var(--text)",
                }}>
                  {v}
                </div>
                <div className="eyebrow" style={{ marginTop: 7, fontSize: 9.5 }}>{k}</div>
              </div>
            ))}
          </div>

          {/* Team token savings — RTK + Agent Booster */}
          {!s.savingsLoading && s.savings &&
            (s.savings.team_total.rtk_saved_tokens > 0 || s.savings.team_total.booster_saved_tokens > 0) && (() => {
            const totalTok = s.savings.team_total.rtk_saved_tokens + s.savings.team_total.booster_saved_tokens
            const totalUsd = s.savings.team_total.rtk_saved_usd + s.savings.team_total.booster_saved_usd
            return (
              <div className="card" style={{ marginBottom: 22, overflow: "hidden" }}>
                <div style={{ padding: "14px 20px 8px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 650, fontSize: 14 }}>Team token savings</span>
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      · {formatTokens(totalTok)} tokens · ${totalUsd.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)" }}>
                  {[
                    { v: formatTokens(s.savings.team_total.rtk_saved_tokens), k: "RTK tokens saved" },
                    { v: `${CURRENCY_SYMBOLS[s.currency]}${fromUsd(s.savings.team_total.rtk_saved_usd, s.currency).toFixed(2)}`, k: "RTK cost saved" },
                    { v: formatTokens(s.savings.team_total.booster_saved_tokens), k: "Booster tokens saved" },
                    { v: `${CURRENCY_SYMBOLS[s.currency]}${fromUsd(s.savings.team_total.booster_saved_usd, s.currency).toFixed(2)}`, k: "Booster cost saved" },
                  ].map(({ v, k }, i) => (
                    <div key={i} style={{ padding: "14px 20px", borderRight: i < 3 ? "1px solid var(--border)" : undefined }}>
                      <div style={{ fontSize: 20, fontWeight: 700, color: "var(--ok)" }}>{v}</div>
                      <div className="eyebrow" style={{ marginTop: 5, fontSize: 10, color: "var(--text-3)" }}>{k}</div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })()}
        </>
      ) : null}

      {/* By developer table */}
      <div className="card" style={{ overflow: "hidden", marginBottom: 24 }}>
        <div style={{ padding: "15px 20px 13px", borderBottom: "1px solid var(--border)", fontWeight: 650, fontSize: 14.5 }}>
          By developer
        </div>
        {/* Header row */}
        <div style={{ display: "grid", gridTemplateColumns: "1.8fr 0.8fr 0.9fr 0.9fr 0.9fr 1.4fr 1.3fr", gap: 14, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          {["Actor", "Sessions", "Tokens", "Est. cost", "Saved", "Coverage", "Budget"].map((h, i) => (
            <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
          ))}
        </div>

        {s.loading ? (
          <div style={{ padding: 20 }}>
            {[...Array(3)].map((_, i) => (
              <div key={i} style={{ height: 40, background: "var(--surface-2)", borderRadius: 6, marginBottom: 8, opacity: 0.6 }} />
            ))}
          </div>
        ) : !s.data || s.data.by_developer.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
            No developer spend data for this period.
          </div>
        ) : (
          s.data.by_developer.map(dev => {
            const budgetLimit = s.budgets[dev.email] ?? null
            return (
              <div key={dev.email} style={{ display: "grid", gridTemplateColumns: "1.8fr 0.8fr 0.9fr 0.9fr 0.9fr 1.4fr 1.3fr", gap: 14, padding: "12px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 550, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dev.email}</span>
                  <a
                    href={`/theguard/activity?dev=${encodeURIComponent(dev.email)}`}
                    style={{ fontSize: 11, color: "var(--accent-text)", textDecoration: "none", flexShrink: 0 }}
                    aria-label={`View activity for ${dev.email}`}
                  >
                    →
                  </a>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span className="mono" style={{ fontSize: 12, color: "var(--text-2)" }}>{dev.sessions} <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "inherit" }}>proxy</span></span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{dev.hook_sessions ?? 0} <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "inherit" }}>direct</span></span>
                </div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>{formatTokens(dev.tokens_after)}</div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--text-2)" }}>
                  {CURRENCY_SYMBOLS[s.currency]}{fromUsd(dev.cost_usd, s.currency).toFixed(2)}
                </div>
                <div className="mono" style={{ fontSize: 12.5, color: "var(--ok)" }}>
                  {CURRENCY_SYMBOLS[s.currency]}{fromUsd(dev.saved_usd, s.currency).toFixed(2)}
                </div>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  {(dev.detected_tools ?? []).map(tool => {
                    const covered = (dev.mcp_registered ?? []).includes(tool) || (dev.hook_registered ?? []).includes(tool)
                    return (
                      <span
                        key={tool}
                        aria-label={`${TOOL_LABELS[tool] ?? tool}: ${covered ? "covered" : "not covered"}`}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 3,
                          fontSize: 10.5, fontWeight: 600, padding: "2px 7px",
                          borderRadius: 20,
                          background: covered ? "var(--ok-bg)" : "var(--warn-bg)",
                          color: covered ? "var(--ok)" : "var(--warn)",
                          border: `1px solid ${covered ? "var(--ok-bd)" : "var(--warn-bd)"}`,
                        }}
                      >
                        <span aria-hidden="true">{covered ? "✓" : "!"}</span> {TOOL_LABELS[tool] ?? tool}
                      </span>
                    )
                  })}
                  {(dev.detected_tools ?? []).length === 0 && (
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <BudgetBar used={dev.cost_usd} limit={budgetLimit} warnAt={s.teamSettings.alert_threshold_pct ?? 80} />
                  {s.hardLimits[dev.email] != null && dev.cost_usd >= (s.hardLimits[dev.email] ?? Infinity) && (
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        padding: "2px 7px",
                        borderRadius: 9999,
                        background: "var(--err-bg)",
                        color: "var(--err)",
                        border: "1px solid var(--err-bd)",
                        textTransform: "uppercase",
                        letterSpacing: ".04em",
                        whiteSpace: "nowrap",
                      }}
                      title={`Hard cap reached: $${s.hardLimits[dev.email]} — tool calls are blocked`}
                    >
                      Hard cap
                    </span>
                  )}
                  {s.isAdmin && (
                    <BudgetInput email={dev.email} current={budgetLimit} currentHard={s.hardLimits[dev.email] ?? null} onSave={s.saveBudget} />
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* By AI tool table */}
      {s.data && s.data.by_ai_tool.length > 0 && (() => {
        const totalAfter = s.data.total_tokens_after
        return (
          <ByAiToolTable
            rows={s.data.by_ai_tool.map(t => ({
              tool: t.ai_tool,
              tokens: t.tokens_after,
              costLabel: `${CURRENCY_SYMBOLS[s.currency]}${fromUsd(t.cost_usd, s.currency).toFixed(2)}`,
              saved: t.tokens_saved,
              savedCostLabel: t.cost_saved > 0
                ? `${CURRENCY_SYMBOLS[s.currency]}${fromUsd(t.cost_saved, s.currency).toFixed(2)}`
                : undefined,
              pct: totalAfter > 0
                ? Math.round((t.tokens_after / totalAfter) * 100)
                : 0,
            }))}
          />
        )
      })()}
    </>
  )
}
