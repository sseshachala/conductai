"use client"

import type { TokenGuardrails } from "@/hooks/useTokenGuardrails"
import { formatTotalTokensSaved, GuardStatCard, SavingsStatCard, type ToolCoverageRow } from "./widgets"
import type { GuardDashboardState } from "./useGuardDashboard"

export function MetricsSection({ s }: { s: GuardDashboardState }) {
  const {
    savings,
    savingsLoading,
    guardrails,
    stats,
    loading,
    toolCoverage,
    filterDecision,
    setFilterDecision,
    derivedStats,
    tokenEfficiencyWarnings,
    blockedToday,
  } = s
  return (
    <>
      {/* 6 stat cards */}
      {(() => {
        const isCovered = (dev: ToolCoverageRow) => dev.mcp_registered.length > 0 || dev.hook_registered.length > 0
        const coveredCount = toolCoverage.filter(isCovered).length
        const totalDevs = toolCoverage.length
        return (
          <>
            {loading ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 16 }}>
                {[...Array(7)].map((_, i) => (
                  <div key={i} className="card card-pad" style={{ height: 80 }} />
                ))}
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 16 }}>
                <GuardStatCard
                  label="Active developers"
                  value={stats?.active_developers || derivedStats.active_developers}
                  tone="ok"
                  sub="active today"
                />
                <GuardStatCard
                  label="Events today"
                  value={stats?.events_today || derivedStats.events_today}
                  tone="plain"
                  sub="tool calls logged"
                />
                <GuardStatCard
                  label="Blocked today"
                  value={blockedToday}
                  tone={blockedToday > 0 ? "err" : "plain"}
                  onClick={() => setFilterDecision(prev => prev === "blocked" ? "all" : "blocked")}
                  active={filterDecision === "blocked"}
                  sub={blockedToday > 0 ? "click to filter" : "none blocked"}
                />
                <GuardStatCard
                  label="Sessions today"
                  value={(stats?.sessions ?? 0) + (stats?.hook_sessions ?? 0)}
                  tone="plain"
                  sub={`${stats?.sessions ?? 0} gateway · ${stats?.hook_sessions ?? 0} hook`}
                />
                <GuardStatCard
                  label="Tokens saved"
                  value={formatTotalTokensSaved(stats?.tokens_saved_today || derivedStats.tokens_saved_today)}
                  tone="accent"
                  sub="today · vs unguarded calls"
                />
                <SavingsStatCard savings={savings} loading={savingsLoading} />
                <GuardStatCard
                  label="Token efficiency"
                  value={tokenEfficiencyWarnings.count === 0 ? "Clean" : tokenEfficiencyWarnings.count}
                  tone={tokenEfficiencyWarnings.count > 0 ? "warn" : "ok"}
                  sub={tokenEfficiencyWarnings.count > 0
                    ? `${formatTotalTokensSaved(tokenEfficiencyWarnings.tokens)} flagged`
                    : "no waste detected"}
                />
                <GuardStatCard
                  label="Tool coverage"
                  value={totalDevs === 0 ? "—" : `${coveredCount}/${totalDevs}`}
                  tone={totalDevs === 0 ? "plain" : coveredCount === totalDevs ? "ok" : "warn"}
                  sub={totalDevs === 0 ? "no data yet" : (() => {
                    const totalTools = toolCoverage.reduce((s, d) => s + d.detected_tools.length, 0)
                    return coveredCount === totalDevs
                      ? `${totalTools} tool${totalTools !== 1 ? "s" : ""} · all covered`
                      : `${totalDevs - coveredCount} dev${totalDevs - coveredCount !== 1 ? "s" : ""} need sync`
                  })()}
                />
              </div>
            )}

            {/* Tool coverage panel */}
            {!loading && toolCoverage.length > 0 && (() => {
              const TOOL_LABEL: Record<string, string> = {
                "claude-code": "Claude", "claude_chat": "Claude.ai", "claude_desktop": "Claude Desktop", "claude_work": "Claude Work",
                "codex": "Codex", "cursor": "Cursor", "windsurf": "Windsurf", "vscode": "VS Code",
              }
              return (
                <div className="card" style={{ marginBottom: 20, padding: "16px 18px" }}>
                  <div className="eyebrow" style={{ marginBottom: 12 }}>
                    Tool coverage — {new Date().toLocaleDateString()}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {toolCoverage.map(dev => {
                      const allCovered = dev.detected_tools.every(t =>
                        dev.mcp_registered.includes(t) || dev.hook_registered.includes(t)
                      )
                      return (
                        <div key={dev.email} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                          <span className="dot" style={{ background: allCovered ? "var(--ok)" : "var(--warn)", flexShrink: 0 }} />
                          <span style={{ fontSize: 12.5, color: "var(--text-2)", width: 220, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {dev.email}
                          </span>
                          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                            {dev.detected_tools.map(tool => {
                              const covered = dev.mcp_registered.includes(tool) || dev.hook_registered.includes(tool)
                              return (
                                <span key={tool} style={{
                                  display: "inline-flex", alignItems: "center", gap: 3,
                                  fontSize: 10.5, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
                                  background: covered ? "var(--ok-bg)" : "var(--warn-bg)",
                                  color: covered ? "var(--ok)" : "var(--warn)",
                                  border: `1px solid ${covered ? "var(--ok-bd)" : "var(--warn-bd)"}`,
                                }}>
                                  {covered ? "✓" : "!"} {TOOL_LABEL[tool] ?? tool}
                                </span>
                              )
                            })}
                            {dev.detected_tools.length === 0 && (
                              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>no tools detected</span>
                            )}
                          </div>
                          <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: "auto" }}>
                            {new Date(dev.reported_at).toLocaleString()}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                  {coveredCount < totalDevs && (
                    <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 8, background: "var(--warn-bg)", border: "1px solid var(--warn-bd)", fontSize: 12, color: "var(--warn)" }}>
                      {totalDevs - coveredCount} developer{totalDevs - coveredCount > 1 ? "s" : ""} have uncovered tools — ask them to run: <code style={{ fontFamily: "monospace" }}>conduct guard sync</code>
                    </div>
                  )}
                </div>
              )
            })()}
          </>
        )
      })()}

      {/* ── 7 Token Guardrails widget ───────────────────────────────────────── */}
      {!loading && (() => {
        // enforcement: "enforced" = actively blocking/saving | "configured" = stored, partial | "detected" = passive only | "pending" = not yet built
        const guardrailItems = [
          { label: "Prompt caching",        key: "prompt_caching",        enforcement: "enforced",   tip: "Active on all workflow runs. Proxy layer gap tracked in #898." },
          { label: "Model routing",         key: "model_routing",         enforcement: "enforced",   tip: "Always routes tasks to cheapest capable model tier." },
          { label: "Prompt splitting",      key: "prompt_splitting",      enforcement: "pending",    tip: "Not yet implemented — large prompts are not split. Tracked in #900." },
          { label: "Deterministic offload", key: "deterministic_offload", enforcement: "detected",   tip: "Detects whether the rule is active. Actual offloading not yet implemented. Tracked in #901." },
          { label: "Output compression",    key: "output_compression",    enforcement: "detected",   tip: "Detects RTK install. Sandbox output compression not yet implemented. Tracked in #902." },
          { label: "Structured retrieval",  key: "structured_retrieval",  enforcement: "detected",   tip: "Detects Agent Booster install. Smart file reads inside sandboxes not yet implemented. Tracked in #902." },
          { label: "Metrics & budgets",     key: "metrics_budgets",       enforcement: "configured", tip: "Guard spend budgets enforced on proxy traffic. Workflow run enforcement gap tracked in #903." },
        ].map(item => ({
          ...item,
          ok: guardrails ? guardrails[item.key as keyof TokenGuardrails] as boolean : true,
        }))

        const enforcedCount = guardrailItems.filter(g => g.enforcement === "enforced" && g.ok).length
        const configuredCount = guardrailItems.filter(g => g.enforcement === "configured" && g.ok).length

        const badgeStyle = (enforcement: string, ok: boolean) => {
          if (!ok) return { color: "var(--text-muted)", background: "var(--surface-3)" }
          if (enforcement === "enforced")   return { color: "#166534", background: "#dcfce7" }
          if (enforcement === "configured") return { color: "#6366f1", background: "#eef2ff" }
          if (enforcement === "detected")   return { color: "var(--text-muted)", background: "var(--surface-3)" }
          return { color: "#92400e", background: "#fef3c7" } // pending
        }

        return (
          <div className="card" style={{ marginBottom: 20, padding: "16px 20px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div className="eyebrow">Token abuse guardrails</div>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ok)" }}>
                {enforcedCount} enforced · {configuredCount} configured
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 8 }}>
              {guardrailItems.map((g, i) => (
                <div key={i} title={g.tip} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, cursor: "default" }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 10,
                    background: g.ok ? "var(--ok-bg)" : "var(--surface-3)",
                    border: `1px solid ${g.ok ? "var(--ok-bd)" : "var(--border)"}`,
                    display: "grid", placeItems: "center",
                    fontSize: 16,
                  }}>
                    {g.ok ? "✓" : "○"}
                  </div>
                  <span style={{ fontSize: 10, color: g.ok ? "var(--text-2)" : "var(--text-muted)", textAlign: "center", lineHeight: 1.3, fontWeight: g.ok ? 500 : 400 }}>
                    {g.label}
                  </span>
                  <span style={{
                    fontSize: 9, fontWeight: 600, letterSpacing: ".02em",
                    borderRadius: 4, padding: "1px 5px",
                    ...badgeStyle(g.enforcement, g.ok),
                  }}>
                    {g.enforcement}
                  </span>
                </div>
              ))}
            </div>
            {(
              <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-3)" }}>
                <strong>enforced</strong> — active now &nbsp;·&nbsp; <strong>configured</strong> — partial coverage &nbsp;·&nbsp; <strong>detected</strong> — passive only &nbsp;·&nbsp; <strong>pending</strong> — not yet built
              </div>
            )}
          </div>
        )
      })()}
    </>
  )
}
