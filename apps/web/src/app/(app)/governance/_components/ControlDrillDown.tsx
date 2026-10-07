"use client"

import type { Dispatch, SetStateAction } from "react"
import Link from "next/link"
import type { BonusFrameworkRow, ControlDrillOut, FrameworkRow, FrameworksOut } from "./types"
import { FRAMEWORK_LABEL, formatRuleYaml } from "./ui"

// Per-control drill-down
export function ControlDrillDown({
  activeFwRow, activeControl, setActiveControl, controlDrill, drillLoading, expandedRule, setExpandedRule, frameworks,
}: {
  activeFwRow: FrameworkRow | BonusFrameworkRow
  activeControl: string | null
  setActiveControl: Dispatch<SetStateAction<string | null>>
  controlDrill: ControlDrillOut | null
  drillLoading: boolean
  expandedRule: string | null
  setExpandedRule: Dispatch<SetStateAction<string | null>>
  frameworks: FrameworksOut | null
}) {
  return (
          <section style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 18,
            background: "var(--surface-1)",
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 12 }}>
              {FRAMEWORK_LABEL[activeFwRow.framework] ?? activeFwRow.framework} controls
            </div>
            {activeFwRow.controls.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-3)" }}>
                No specific controls tagged — this framework matches at the pack level only.
              </div>
            ) : (
              <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
                {activeFwRow.controls.map(ctrl => {
                  const isActive = ctrl === activeControl
                  return (
                    <button
                      key={ctrl}
                      onClick={() => setActiveControl(isActive ? null : ctrl)}
                      style={{
                        textAlign: "left",
                        border: `1px solid ${isActive ? "var(--accent-text)" : "var(--border)"}`,
                        borderRadius: 6,
                        padding: "10px 12px",
                        background: isActive ? "var(--accent-weak)" : "var(--surface-2)",
                        color: isActive ? "var(--accent-text)" : "var(--text-1)",
                        cursor: "pointer",
                        fontFamily: "inherit",
                      }}
                    >
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{ctrl}</div>
                      <div style={{ fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)", marginTop: 2 }}>
                        {isActive ? "showing rules ↓" : "covered · click to view rules"}
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Drill-down: rules covering the selected control */}
              {activeControl && (
                <div style={{ marginTop: 16, padding: "14px 16px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)" }}>
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                      Rules covering {activeFwRow.framework}: {activeControl}
                    </div>
                    {controlDrill && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {controlDrill.rules.length} {controlDrill.rules.length === 1 ? "rule" : "rules"}
                      </div>
                    )}
                  </div>
                  {drillLoading && (
                    <div style={{ fontSize: 12, color: "var(--text-3)" }}>Loading rules…</div>
                  )}
                  {!drillLoading && controlDrill && controlDrill.rules.length === 0 && (
                    <div style={{ fontSize: 12, color: "var(--text-3)" }}>No rules cover this control yet.</div>
                  )}
                  {!drillLoading && controlDrill && controlDrill.rules.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {controlDrill.rules.map(r => (
                        <div key={r.rule_id} style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 6, padding: "10px 12px" }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                              <Link href={`/packs/${r.pack_slug}`} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", textDecoration: "none" }}>
                                {r.rule_id}
                              </Link>
                              <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "var(--surface-2)", color: "var(--text-2)", textTransform: "uppercase", fontWeight: 600 }}>
                                {r.action}
                              </span>
                              {r.severity && (
                                <span style={{ fontSize: 10, color: "var(--text-3)" }}>severity: {r.severity}</span>
                              )}
                            </div>
                            <Link
                              href={`/theguard/activity?rule_id=${encodeURIComponent(r.rule_id)}`}
                              style={{ fontSize: 11, color: "var(--accent-text)", whiteSpace: "nowrap" }}
                            >
                              {r.events_30d} {r.events_30d === 1 ? "event" : "events"} · 30d →
                            </Link>
                          </div>
                          {r.description && (
                            <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-2)" }}>{r.description}</div>
                          )}
                          {(r.match_tool || r.match_pattern) && (
                            <div style={{ marginTop: 4, fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono, ui-monospace, monospace)" }}>
                              {r.match_tool && <span>tool: {r.match_tool}</span>}
                              {r.match_tool && r.match_pattern && <span> · </span>}
                              {r.match_pattern && <span style={{ wordBreak: "break-all" }}>{r.match_pattern}</span>}
                            </div>
                          )}
                          <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-muted)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span>from <Link href={`/packs/${r.pack_slug}`} style={{ color: "var(--accent-text)", textDecoration: "none" }}>{r.pack_slug}</Link></span>
                            <button
                              type="button"
                              onClick={() => setExpandedRule(expandedRule === r.rule_id ? null : r.rule_id)}
                              style={{ fontSize: 10, fontWeight: 600, color: "var(--accent-text)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                            >
                              {expandedRule === r.rule_id ? "hide YAML ↑" : "show YAML ↓"}
                            </button>
                          </div>
                          {expandedRule === r.rule_id && (
                            <pre style={{
                              marginTop: 8,
                              padding: "10px 12px",
                              background: "var(--surface-3, #0d0d10)",
                              color: "var(--text-1)",
                              border: "1px solid var(--border)",
                              borderRadius: 6,
                              fontFamily: "ui-monospace, monospace",
                              fontSize: 11,
                              lineHeight: 1.55,
                              overflowX: "auto",
                              whiteSpace: "pre",
                            }}>{formatRuleYaml(r)}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              </>
            )}
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-muted)" }}>
              Source packs: {activeFwRow.packs.join(", ")}
            </div>
            {(() => {
              // Only render CTA when the active framework is a "bonus" one — i.e. its
              // dedicated pack isn't installed. Installed-tier frameworks already get
              // dedicated coverage so no CTA is needed.
              const isBonus = frameworks?.bonus.some(b => b.framework === activeFwRow.framework)
              if (!isBonus) return null
              const rec = (activeFwRow as BonusFrameworkRow).recommended_pack
              const label = FRAMEWORK_LABEL[activeFwRow.framework] ?? activeFwRow.framework
              if (rec) {
                return (
                  <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-2)" }}>
                    Want dedicated {label} controls?{" "}
                    <Link href={`/packs/${rec}`} style={{ color: "var(--accent-text)", textDecoration: "underline" }}>
                      Install {rec}
                    </Link>
                  </div>
                )
              }
              return (
                <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}>
                  Dedicated {label} pack — <em>coming soon</em>. Currently covered via cross-tagged rules from your installed packs.
                </div>
              )
            })()}
          </section>
  )
}
