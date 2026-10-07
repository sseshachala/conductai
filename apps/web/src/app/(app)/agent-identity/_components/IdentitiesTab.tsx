"use client"

import { Activity, KeyRound } from "lucide-react"
import { classifyIdentity, trialCountdown, KIND_SECTIONS, TIER_STYLE, LIFECYCLE_STYLE, type Identity, type IdentityKind } from "./shared"
import type { AgentIdentityState } from "./useAgentIdentity"

export function IdentitiesTab({ s }: { s: AgentIdentityState }) {
  const {
    isAdmin,
    identities,
    identitiesLoading,
    savingIdentity,
    activeTab,
    sourceFilter,
    highlightId,
    selectTab,
    clearSourceFilter,
    patchIdentity,
    certifyIdentity,
  } = s
  return (
    <>
        {/* Agent identities — Phase 3 of #1037 */}
        <div role="tabpanel" id="tabpanel-identities" aria-labelledby="tab-identities" hidden={activeTab !== "identities"} style={{ display: activeTab === "identities" ? "block" : "none" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>Agent identities</div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Every agent has an accountable owner, a risk tier, a lifecycle state, and a certification cadence. Lifecycle is enforced immediately — deactivated or expired identities cannot authenticate. Tier is enforced by Cedar rules referencing <code>context.risk_tier</code> — see <code>docs/guard/examples/</code> for a working sample.
          </p>
          {sourceFilter && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, fontSize: 12, color: "var(--text-2)" }}>
              <span style={{ color: "var(--text-muted)" }}>Filter:</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 8px", borderRadius: 4, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                Source: {sourceFilter}
                <button
                  onClick={clearSourceFilter}
                  aria-label="Clear filter"
                  style={{ background: "none", border: "none", padding: 0, color: "var(--text-muted)", cursor: "pointer", fontSize: 14, lineHeight: 1 }}
                >
                  ×
                </button>
              </span>
              <span style={{ color: "var(--text-muted)" }}>({identities.filter(i => i.source === sourceFilter).length} of {identities.length})</span>
            </div>
          )}
          <div className="card" style={{ overflowX: "auto" }}>
            {identitiesLoading ? (
              <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>Loading identities…</div>
            ) : (() => {
              const visibleIdentities = sourceFilter ? identities.filter(i => i.source === sourceFilter) : identities
              if (visibleIdentities.length === 0) {
                return <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>{sourceFilter ? `No identities with source “${sourceFilter}”.` : "No agent identities yet."}</div>
              }
              // Group by lifecycle. When a source filter is active, skip
              // grouping (user asked for a specific subset — show flat).
              const grouped: Record<IdentityKind, Identity[]> = { trial: [], auto: [], human: [] }
              for (const id of visibleIdentities) grouped[classifyIdentity(id)].push(id)
              grouped.trial.sort((a, b) => (a.expires_at ?? "").localeCompare(b.expires_at ?? ""))
              grouped.auto.sort((a, b)  => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
              grouped.human.sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))

              function renderIdentityRow(id: Identity) {
                const tier = TIER_STYLE[id.risk_tier ?? ""] ?? { bg: "var(--surface-2)", fg: "var(--text-muted)" }
                const lc   = LIFECYCLE_STYLE[id.lifecycle_state ?? ""] ?? { bg: "var(--surface-2)", fg: "var(--text-muted)", label: id.lifecycle_state ?? "—" }
                const busy = savingIdentity === id.id
                const isHighlighted = highlightId === id.id
                // Countdown is a *trial* concept: "N days until the trial ends".
                // Auto-provisioned CLI identities also have expires_at (the
                // rolling session token TTL that refreshes on `conduct login`)
                // but that's not a lifecycle event — the identity itself stays
                // Active. Firing "Expired" for those was misleading, so gate
                // the countdown on the trial classification.
                const countdown = (id.expires_at && classifyIdentity(id) === "trial")
                  ? trialCountdown(id.expires_at)
                  : null
                return (
                  <tr
                    key={id.id}
                    id={`identity-row-${id.id}`}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      background: isHighlighted ? "#fef3c7" : undefined,
                      transition: "background 400ms ease-out",
                    }}
                  >
                    <td style={{ padding: "8px 12px" }} title={id.id}>
                      <div style={{ fontWeight: 500, color: "var(--text)" }}>
                        {(id.name.startsWith("user_") && id.name.includes("(auto)")) ? "Auto-provisioned agent" : id.name}
                      </div>
                      <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--text-muted)" }}>{id.token_prefix?.startsWith("okta_import") ? "external identity" : id.token_prefix}</div>
                      {/* Match the id chip shown in the activity row so a deep-link
                          from ?id=<uuid> can be confirmed visually. Full UUID
                          available in the row title attr for hover-to-copy. */}
                      <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--text-muted)" }} title={id.id}>
                        <span style={{ opacity: 0.7 }}>id: </span>{id.id.slice(0, 8)}<span style={{ opacity: 0.5 }}>…</span>
                      </div>
                      {countdown && (
                        <div style={{ fontSize: 10.5, color: countdown.expired ? "var(--err)" : "var(--warn)", marginTop: 2, fontWeight: 600 }}>
                          {countdown.expired ? "Expired" : `⏱ ${countdown.label}`}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-2)" }}>
                      <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 4, background: "var(--surface-2)", border: "1px solid var(--border)", fontFamily: "monospace", fontSize: 10.5 }}>
                        {id.source ?? "conduct"}
                      </span>
                      {id.platform_of_origin && <span style={{ marginLeft: 6, color: "var(--text-muted)" }}>· {id.platform_of_origin}</span>}
                    </td>
                    <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-2)" }}>
                      {id.owner_user_id ?? <span style={{ color: "var(--text-muted)" }}>unassigned</span>}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <select
                        value={id.risk_tier ?? "tier_1"}
                        disabled={busy || !isAdmin}
                        onChange={e => patchIdentity(id.id, { risk_tier: e.target.value })}
                        style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)", background: tier.bg, color: tier.fg }}
                      >
                        <option value="tier_1">Tier 1</option>
                        <option value="tier_2">Tier 2</option>
                        <option value="tier_3">Tier 3</option>
                      </select>
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <select
                        value={id.lifecycle_state ?? "active"}
                        disabled={busy || !isAdmin}
                        onChange={e => patchIdentity(id.id, { lifecycle_state: e.target.value })}
                        style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)", background: lc.bg, color: lc.fg }}
                      >
                        <option value="active">Active</option>
                        <option value="pending_review">Pending review</option>
                        <option value="deactivated">Deactivated</option>
                        <option value="expired">Expired</option>
                      </select>
                    </td>
                    <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-muted)" }}>
                      {id.last_certified_at
                        ? id.last_certified_at.slice(0, 10)
                        : <span style={{ fontStyle: "italic", opacity: 0.7 }}>not yet</span>}
                    </td>
                    <td style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-muted)" }} title={id.last_used_at ?? undefined}>
                      {id.last_used_at
                        ? id.last_used_at.slice(0, 16).replace("T", " ") + " UTC"
                        : <span style={{ fontStyle: "italic", opacity: 0.7 }}>not yet used</span>}
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "right" }}>
                      <button className="btn btn-sm inline-flex min-w-12 items-center justify-center gap-1.5" title={`${id.recorded_session_count ?? 0} attributed activity sessions`} aria-label={`Recorded sessions for ${id.name}`} onClick={() => selectTab("agent_sessions", { id: id.id })}><Activity size={14} />{id.recorded_session_count || "-"}</button>
                      <button className="btn btn-sm" title="Authentication sessions" aria-label={`Authentication sessions for ${id.name}`} onClick={() => selectTab("agent_sessions", { id: id.id, session_type: "authentication" })}><KeyRound size={14} /></button>
                      {isAdmin && (
                        <button
                          onClick={() => certifyIdentity(id.id)}
                          disabled={busy}
                          style={{ fontSize: 10, padding: "3px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text-2)", cursor: busy ? "not-allowed" : "pointer" }}
                        >
                          {busy ? "…" : "Certify"}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              }

              return (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Name</th>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Source</th>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Owner</th>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Tier</th>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Lifecycle</th>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Last certified</th>
                      <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Last used</th>
                      <th style={{ padding: "8px 12px" }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourceFilter
                      ? visibleIdentities.map(id => renderIdentityRow(id))
                      : KIND_SECTIONS.flatMap(section => {
                          const rows = grouped[section.id]
                          if (rows.length === 0) return []
                          return [
                            <tr key={`section-${section.id}`}>
                              <td colSpan={8} style={{ padding: "10px 12px 6px", background: "var(--surface-2)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
                                <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-2)", letterSpacing: ".04em", textTransform: "uppercase" }}>
                                  {section.label} · {rows.length}
                                </span>
                                <span style={{ marginLeft: 10, fontSize: 11, color: "var(--text-muted)" }}>{section.description}</span>
                              </td>
                            </tr>,
                            ...rows.map(id => renderIdentityRow(id)),
                          ]
                        })}
                  </tbody>
                </table>
              )
            })()}
          </div>
          <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "8px 0 0" }}>
            Tier gates enforcement via Cedar rules like <code>context.risk_tier == &quot;tier_3&quot;</code> — matcher runs at every MCP + LLM proxy call. Full example at <code>docs/guard/examples/tier3-no-shell.json</code>; run <code>bash docs/guard/examples/verify_tier.sh</code> to see it fire end-to-end. Setting Lifecycle to Deactivated or Expired blocks authentication on the next call. Only workspace admins can change tier, lifecycle, or certify.
          </p>
        </div>
    </>
  )
}
