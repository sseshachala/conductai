"use client"

import { TabBar } from "@/components/TabBar"
import { AgentSessions } from "@/components/AgentSessions"
import { AgentActivitySessions } from "@/components/AgentActivitySessions"
import { FederationPanel } from "@/components/federation/FederationPanel"
import AgentRateLimitsPanel from "@/components/gateway/AgentRateLimitsPanel"
import type { AgentIdentityState } from "./useAgentIdentity"

export function SessionAndIntegrationTabs({ s }: { s: AgentIdentityState }) {
  const {
    workspaceId,
    isAdmin,
    identitiesLoading,
    identitiesWorkspace,
    lensSessions,
    lensSessionsLoading,
    lensIncludeExpired,
    setLensIncludeExpired,
    revokingLensSessionId,
    activeTab,
    integrationTab,
    setIntegrationTab,
    highlightId,
    multipleSessions,
    setMultipleSessions,
    authenticationView,
    sessionIdentity,
    sessionOptions,
    selectTab,
    okta,
    oktaLoading,
    oktaDomainInput,
    setOktaDomainInput,
    oktaTokenInput,
    setOktaTokenInput,
    oktaSaving,
    oktaSyncing,
    oktaFeedback,
    oktaIssuerInput,
    setOktaIssuerInput,
    oktaAudienceInput,
    setOktaAudienceInput,
    oktaJwtEnabled,
    setOktaJwtEnabled,
    oktaJwtSaving,
    revokeLensSession,
    fmt,
    saveOktaConfig,
    saveOktaJwt,
    syncOktaNow,
    disconnectOkta,
  } = s
  return (
    <>
        {/* Okta integration — #1036 Phase 2 */}
        {/* Lens sessions — #1218 Step 3b.6 */}
        <div role="tabpanel" id="tabpanel-lens_sessions" aria-labelledby="tab-lens_sessions" hidden={activeTab !== "lens_sessions"} style={{ display: activeTab === "lens_sessions" ? "block" : "none" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>Lens sessions</div>
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-2)" }}>
              <input
                type="checkbox"
                checked={lensIncludeExpired}
                onChange={e => setLensIncludeExpired(e.target.checked)}
              />
              Include expired / revoked
            </label>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Short-lived tokens (cond_lens_*) minted per chat session. Every Lens LLM call is Guard-enforced through the same policy engine as external agents. Revoke a session to kill its token immediately — the next call fails auth.
          </p>
          <div className="card" style={{ overflowX: "auto" }}>
            {lensSessionsLoading ? (
              <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>Loading sessions…</div>
            ) : lensSessions.length === 0 ? (
              <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>
                {lensIncludeExpired ? "No Lens sessions yet." : "No active Lens sessions in the last 24h. Toggle \"Include expired / revoked\" to see history."}
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Session</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Started</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Last activity</th>
                    <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Turns</th>
                    <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Spend</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Agent identity</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, color: "var(--text-muted)" }}>Status</th>
                    <th style={{ padding: "8px 12px" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {lensSessions.map(s => {
                    const status = s.token_revoked_at ? "Revoked" : s.is_idle ? "Idle" : s.is_active ? "Active" : "Inactive"
                    const statusColor = s.token_revoked_at ? "#991b1b" : s.is_idle ? "#92400e" : s.is_active ? "#166534" : "var(--text-muted)"
                    const statusBg    = s.token_revoked_at ? "#fee2e2" : s.is_idle ? "#fef3c7" : s.is_active ? "#dcfce7" : "var(--surface-2)"
                    const canRevoke   = !s.token_revoked_at
                    const busy = revokingLensSessionId === s.id
                    return (
                      <tr key={s.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 12px" }}>
                          <div style={{ fontWeight: 500, color: "var(--text)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>{s.id.slice(0, 8)}…</div>
                        </td>
                        <td style={{ padding: "8px 12px", color: "var(--text-2)" }}>{fmt(s.created_at)}</td>
                        <td style={{ padding: "8px 12px", color: "var(--text-2)" }}>{fmt(s.updated_at)}</td>
                        <td style={{ padding: "8px 12px", textAlign: "right", color: "var(--text-2)" }}>{s.turns}</td>
                        <td style={{ padding: "8px 12px", textAlign: "right", color: "var(--text-2)", fontFamily: "monospace" }}>${s.spend_usd.toFixed(4)}</td>
                        <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 11, color: "var(--text-2)" }}>
                          {s.agent_identity_token_prefix ? (
                            <button
                              onClick={() => selectTab("identities", { id: s.agent_identity_id! })}
                              title={s.agent_identity_name ?? "View agent identity"}
                              style={{ background: "none", border: "none", padding: 0, color: "var(--accent-text)", fontFamily: "monospace", fontSize: 11, cursor: "pointer", textDecoration: "underline" }}
                            >
                              {s.agent_identity_token_prefix}
                            </button>
                          ) : (
                            <span style={{ color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600, background: statusBg, color: statusColor }}>{status}</span>
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "right" }}>
                          {canRevoke && (
                            <button
                              onClick={() => revokeLensSession(s.id)}
                              disabled={busy}
                              className="btn btn-ghost btn-sm"
                              style={{ color: "var(--err)" }}
                            >
                              {busy ? "Revoking…" : "Revoke"}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {activeTab === "rate_limits" && <div role="tabpanel" id="tabpanel-rate_limits" aria-labelledby="tab-rate_limits">
          <AgentRateLimitsPanel key={workspaceId} workspaceId={workspaceId} isAdmin={isAdmin} />
        </div>}

        <div role="tabpanel" id="tabpanel-integrations" aria-labelledby="tab-integrations" hidden={activeTab !== "integrations"} style={{ display: activeTab === "integrations" ? "block" : "none" }}>
          <TabBar tabs={["okta", "oidc"] as const} labels={{ okta: "Okta", oidc: "OIDC" }} activeTab={integrationTab} onSelect={value => { setIntegrationTab(value); selectTab("integrations", { integration: value }) }} idPrefix="integration" />
          {activeTab === "integrations" && integrationTab === "oidc" && <div id="tabpanel-oidc" role="tabpanel" aria-labelledby="integration-oidc"><FederationPanel key={`${workspaceId}:connections`} workspace={workspaceId} mode="connections" /></div>}
          <div id="tabpanel-okta" role="tabpanel" aria-labelledby="integration-okta" hidden={integrationTab !== "okta"} style={{ paddingTop: 18 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>Okta integration</div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Pull agent identities from your Okta tenant into Conduct as Guard principals. Okta owns auth; Conduct governs what each identity is allowed to do.
          </p>
          <div className="card" style={{ padding: "16px 20px" }}>
            {oktaLoading ? (
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading…</div>
            ) : okta.configured ? (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
                  <div style={{ fontSize: 12, color: "var(--text-2)" }}>
                    <div><span style={{ color: "var(--text-muted)" }}>Domain:</span> <code>{okta.domain}</code></div>
                    <div style={{ marginTop: 2 }}><span style={{ color: "var(--text-muted)" }}>Token:</span> <code>{okta.token_prefix}</code> (stored encrypted)</div>
                    {okta.last_synced_at ? (
                      <div style={{ marginTop: 6, fontSize: 11 }}>
                        <span style={{ color: "var(--text-muted)" }}>Last sync:</span> {okta.last_synced_at?.slice(0, 16).replace("T", " ")} UTC ·{" "}
                        <button
                          onClick={() => selectTab("identities", { source: "okta" })}
                          title="View Okta-sourced identities"
                          style={{ background: "none", border: "none", padding: 0, color: "var(--accent-text)", fontSize: 11, cursor: "pointer", textDecoration: "underline" }}
                        >
                          imported {okta.last_import ?? 0}
                        </button>
                        {" · "}
                        <button
                          onClick={() => selectTab("identities", { source: "okta" })}
                          title="View Okta-sourced identities"
                          style={{ background: "none", border: "none", padding: 0, color: "var(--accent-text)", fontSize: 11, cursor: "pointer", textDecoration: "underline" }}
                        >
                          updated {okta.last_update ?? 0}
                        </button>
                      </div>
                    ) : (
                      <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>Never synced.</div>
                    )}
                    {okta.last_error && (
                      <div style={{ marginTop: 6, fontSize: 11, color: "var(--err)" }}>Last error: {okta.last_error}</div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={syncOktaNow}
                      disabled={oktaSyncing || oktaSaving}
                      className="btn btn-primary btn-sm"
                    >
                      {oktaSyncing ? "Syncing…" : "Sync now"}
                    </button>
                    <button
                      onClick={disconnectOkta}
                      disabled={oktaSyncing || oktaSaving}
                      style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 12, cursor: "pointer" }}
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>Update stored credentials:</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      type="text"
                      value={oktaDomainInput}
                      onChange={e => setOktaDomainInput(e.target.value)}
                      placeholder="dev-XXXXXX.okta.com"
                      style={{ flex: "1 1 220px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <input
                      type="password"
                      value={oktaTokenInput}
                      onChange={e => setOktaTokenInput(e.target.value)}
                      placeholder="New Okta API token (SSWS)"
                      style={{ flex: "2 1 260px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <button
                      onClick={saveOktaConfig}
                      disabled={oktaSaving || !oktaDomainInput.trim() || !oktaTokenInput.trim()}
                      className="btn btn-sm"
                      style={{ padding: "6px 12px", fontSize: 12 }}
                    >
                      {oktaSaving ? "Saving…" : "Save"}
                    </button>
                  </div>
                </div>
                {/* JWT authentication (#1056) — Phase 3b runtime enforcement */}
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      JWT authentication — accept Okta-signed tokens as Guard principals
                    </div>
                    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-2)", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={oktaJwtEnabled}
                        onChange={e => setOktaJwtEnabled(e.target.checked)}
                        disabled={oktaJwtSaving}
                      />
                      Enabled
                    </label>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      type="text"
                      value={oktaIssuerInput}
                      onChange={e => setOktaIssuerInput(e.target.value)}
                      placeholder={okta.domain ? `https://${okta.domain}/oauth2/default` : "https://{domain}/oauth2/default"}
                      style={{ flex: "1 1 260px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <input
                      type="text"
                      value={oktaAudienceInput}
                      onChange={e => setOktaAudienceInput(e.target.value)}
                      placeholder="api://default"
                      style={{ flex: "1 1 160px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                    />
                    <button
                      onClick={saveOktaJwt}
                      disabled={oktaJwtSaving}
                      className="btn btn-sm"
                      style={{ padding: "6px 12px", fontSize: 12 }}
                    >
                      {oktaJwtSaving ? "Saving…" : "Save JWT config"}
                    </button>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>
                    Configure the OAuth authorization server in your Okta admin, then set the issuer + audience here and toggle Enabled.
                  </div>
                </div>
              </>
            ) : (
              <div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 10 }}>
                  Not configured. Enter your Okta domain and an admin API token to start pulling apps into Guard as agent identities.
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input
                    type="text"
                    value={oktaDomainInput}
                    onChange={e => setOktaDomainInput(e.target.value)}
                    placeholder="dev-XXXXXX.okta.com"
                    style={{ flex: "1 1 220px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                  />
                  <input
                    type="password"
                    value={oktaTokenInput}
                    onChange={e => setOktaTokenInput(e.target.value)}
                    placeholder="Okta API token (SSWS)"
                    style={{ flex: "2 1 260px", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}
                  />
                  <button
                    onClick={saveOktaConfig}
                    disabled={oktaSaving || !oktaDomainInput.trim() || !oktaTokenInput.trim()}
                    className="btn btn-primary btn-sm"
                    style={{ padding: "6px 12px", fontSize: 12 }}
                  >
                    {oktaSaving ? "Saving…" : "Save & Connect"}
                  </button>
                </div>
                <p style={{ fontSize: 10.5, color: "var(--text-muted)", margin: "8px 0 0" }}>
                  Create a token in Okta admin: Security → API → Tokens → Create Token. The token is stored encrypted and never returned by the API.
                </p>
              </div>
            )}
            {oktaFeedback && (
              <div style={{ marginTop: 10, fontSize: 11, color: oktaFeedback.toLowerCase().includes("fail") ? "var(--err)" : "var(--ok)" }}>
                {oktaFeedback}
              </div>
            )}
          </div>
        </div>

          </div>
        {activeTab === "delegation" && <div role="tabpanel" id="tabpanel-delegation" aria-labelledby="tab-delegation"><FederationPanel key={`${workspaceId}:delegation`} workspace={workspaceId} mode="delegation" /></div>}
        {activeTab === "agent_sessions" && <div role="tabpanel" id="tabpanel-agent_sessions" aria-labelledby="tab-agent_sessions">
          <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Agent sessions</h2>
          <div className="mb-5 flex flex-wrap items-center gap-4">
            <div role="radiogroup" aria-label="Session type" className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="radio" name="session-type" checked={!authenticationView} onChange={() => selectTab("agent_sessions")} />Recorded activity</label>
              <label className="flex items-center gap-2"><input type="radio" name="session-type" checked={authenticationView} onChange={() => selectTab("agent_sessions", { session_type: "authentication" })} />Authentication</label>
            </div>
            {!authenticationView && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={multipleSessions} onChange={e => { setMultipleSessions(e.target.checked); selectTab("agent_sessions") }} />2+ recorded sessions</label>}
          </div>
          {identitiesLoading || identitiesWorkspace !== workspaceId ? <p role="status">Loading agents...</p> : <>
            <label htmlFor="session-agent" style={{ display: "block", fontSize: 12, marginBottom: 6 }}>Agent identity</label>
            <select id="session-agent" value={sessionIdentity?.id ?? ""} onChange={e => selectTab("agent_sessions", { id: e.target.value, session_type: authenticationView ? "authentication" : "activity" })} style={{ width: "100%", maxWidth: 480, padding: "8px 12px", marginBottom: 20, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--text)", fontSize: 13 }}>
              {!sessionIdentity && <option value="">Select an agent</option>}
              {sessionOptions.map(identity => <option key={identity.id} value={identity.id}>{identity.name} ({identity.id.slice(0, 8)}){!authenticationView ? ` - ${identity.recorded_session_count ?? 0} recorded` : ""}</option>)}
            </select>
            {sessionIdentity ? authenticationView
              ? <AgentSessions key={`${workspaceId}:${sessionIdentity.id}`} workspaceId={workspaceId} identityId={sessionIdentity.id} />
              : <AgentActivitySessions key={`${workspaceId}:${sessionIdentity.id}`} workspaceId={workspaceId} identityId={sessionIdentity.id} />
              : <p className="py-4 text-sm text-[var(--text-muted)]">{highlightId ? "Agent identity not found." : authenticationView ? "No agent identities available." : "No agents with matching attributed activity sessions."}</p>}
          </>}
        </div>}

    </>
  )
}
