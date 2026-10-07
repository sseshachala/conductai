"use client"

import type { AgentIdentityState } from "./useAgentIdentity"

export function TokenTabs({ s }: { s: AgentIdentityState }) {
  const {
    tokens,
    loading,
    cliToken,
    revealed,
    setRevealed,
    copied,
    apiTokens,
    apiLoading,
    showCreateForm,
    setShowCreateForm,
    newTokenName,
    setNewTokenName,
    newTokenExpiry,
    setNewTokenExpiry,
    creating,
    createdToken,
    setCreatedToken,
    createdCopied,
    setCreatedCopied,
    revokeId,
    setRevokeId,
    revoking,
    isAdmin,
    activeTab,
    fmt,
    maskToken,
    copyToken,
    handleCreateToken,
    handleRevoke,
  } = s
  return (
    <>
        {/* CLI Developer Token */}
        <div role="tabpanel" id="tabpanel-tokens" aria-labelledby="tab-tokens" hidden={activeTab !== "tokens"} style={{ display: activeTab === "tokens" ? "flex" : "none", flexDirection: "column", gap: 20 }}>
        <div className="card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginBottom: 10 }}>CLI Token</div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Your personal agent token. Set by <code>conduct login</code>. Valid for 8 hours — re-run to rotate.
          </p>
          {loading ? (
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading…</span>
          ) : cliToken ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <code style={{
                fontFamily: "monospace", fontSize: 12,
                background: "var(--bg)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "4px 10px", color: "var(--text-3)",
                letterSpacing: revealed ? "normal" : "0.05em",
                userSelect: revealed ? "text" : "none",
              }}>
                {revealed ? cliToken : maskToken(cliToken)}
              </code>
              <button
                onClick={() => setRevealed(r => !r)}
                style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-muted)", cursor: "pointer" }}
              >
                {revealed ? "Hide" : "Reveal"}
              </button>
              {revealed && (
                <button
                  onClick={copyToken}
                  style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: copied ? "var(--ok)" : "var(--text-muted)", cursor: "pointer" }}
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
              )}
            </div>
          ) : (
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              No CLI token found. Run <code>conduct login</code> to authenticate.
            </span>
          )}
        </div>

        {/* API Tokens */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>API Tokens</div>
            {isAdmin && !showCreateForm && (
              <button onClick={() => setShowCreateForm(true)} className="btn btn-sm btn-primary">+ Create token</button>
            )}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
            Long-lived tokens for external apps and agents calling Guard via MCP. Admin-managed.
          </p>

          {/* One-time reveal after creation */}
          {createdToken && (
            <div className="card" style={{ padding: "12px 16px", marginBottom: 12, background: "var(--ok-bg)", border: "1px solid var(--ok-bd)" }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)", margin: "0 0 8px" }}>Token created — copy it now. It won&apos;t be shown again.</p>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <code style={{ fontFamily: "monospace", fontSize: 12, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 10px", flex: 1 }}>
                  {createdToken}
                </code>
                <button
                  onClick={() => { navigator.clipboard.writeText(createdToken); setCreatedCopied(true); setTimeout(() => setCreatedCopied(false), 2000) }}
                  style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: createdCopied ? "var(--ok)" : "var(--text-muted)", cursor: "pointer" }}
                >{createdCopied ? "Copied!" : "Copy"}</button>
                <button onClick={() => setCreatedToken(null)} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-muted)", cursor: "pointer" }}>Dismiss</button>
              </div>
            </div>
          )}

          {/* Create form */}
          {showCreateForm && (
            <div className="card" style={{ padding: "12px 16px", marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Token name</label>
                  <input
                    type="text" value={newTokenName} onChange={e => setNewTokenName(e.target.value)}
                    placeholder="e.g. fraud-detection-agent"
                    style={{ width: "100%", height: 32, border: "1px solid var(--border)", borderRadius: 6, padding: "0 10px", fontSize: 12, background: "var(--surface)", color: "var(--text)" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Expires</label>
                  <select value={newTokenExpiry} onChange={e => setNewTokenExpiry(e.target.value)}
                    style={{ height: 32, border: "1px solid var(--border)", borderRadius: 6, padding: "0 8px", fontSize: 12, background: "var(--surface)", color: "var(--text)" }}>
                    <option value="never">Never</option>
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="365">1 year</option>
                  </select>
                </div>
                <button onClick={handleCreateToken} disabled={!newTokenName.trim() || creating} className="btn btn-sm btn-primary">
                  {creating ? "Creating\u2026" : "Create"}
                </button>
                <button onClick={() => setShowCreateForm(false)} className="btn btn-sm btn-ghost">Cancel</button>
              </div>
            </div>
          )}

          {/* Token list */}
          <div className="card" style={{ overflow: "hidden" }}>
            {apiLoading ? (
              <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading\u2026</div>
            ) : apiTokens.length === 0 ? (
              <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                No API tokens yet.{isAdmin ? " Create one to let external apps call Guard." : " Ask an admin to create one."}
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Name</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Prefix</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Expires</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Last used</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Status</th>
                    {isAdmin && <th style={{ padding: "9px 16px" }} />}
                  </tr>
                </thead>
                <tbody>
                  {apiTokens.map(t => {
                    const expired = t.expires_at ? new Date(t.expires_at) < new Date() : false
                    return (
                      <tr key={t.id} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 16px", fontWeight: 500 }}>{t.token_name ?? "\u2014"}</td>
                        <td style={{ padding: "8px 16px" }}>
                          <code style={{ fontSize: 11.5, color: "var(--text-3)", background: "var(--bg)", padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)" }}>
                            {t.token_prefix ? `${t.token_prefix}...` : "\u2014"}
                          </code>
                        </td>
                        <td style={{ padding: "8px 16px", color: expired ? "var(--err)" : "var(--text-muted)" }} suppressHydrationWarning>
                          {t.expires_at ? fmt(t.expires_at) : "Never"}
                        </td>
                        <td style={{ padding: "8px 16px", color: "var(--text-muted)" }}>{fmt(t.last_used_at)}</td>
                        <td style={{ padding: "8px 16px" }} suppressHydrationWarning>
                          {expired
                            ? <span style={{ color: "var(--err)", fontSize: 11.5 }}>Expired</span>
                            : <span style={{ color: "var(--ok)", fontWeight: 600, fontSize: 11.5 }}>Active</span>
                          }
                        </td>
                        {isAdmin && (
                          <td style={{ padding: "8px 16px", textAlign: "right" }}>
                            {revokeId === t.id ? (
                              <span style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                                <button onClick={() => handleRevoke(t.id)} disabled={revoking === t.id}
                                  style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid var(--err)", background: "var(--err)", color: "#fff", cursor: "pointer" }}>
                                  {revoking === t.id ? "\u2026" : "Confirm"}
                                </button>
                                <button onClick={() => setRevokeId(null)} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-muted)", cursor: "pointer" }}>Cancel</button>
                              </span>
                            ) : (
                              <button onClick={() => setRevokeId(t.id)}
                                style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--err)", cursor: "pointer" }}>
                                Revoke
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        </div>{/* end tabpanel tokens */}

        {/* Run Tokens */}
        <div role="tabpanel" id="tabpanel-run_tokens" aria-labelledby="tab-run_tokens" hidden={activeTab !== "run_tokens"} style={{ display: activeTab === "run_tokens" ? "block" : "none" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>Run Tokens</div>
          <div className="card" style={{ overflow: "hidden" }}>
            {loading ? (
              <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>Loading...</div>
            ) : tokens.length === 0 ? (
              <div style={{ padding: "32px 20px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                No run tokens yet. Trigger a workflow to see tokens here.
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Token</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Workflow</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Run</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Minted</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>First used</th>
                    <th style={{ textAlign: "left", padding: "9px 16px", fontWeight: 500, color: "var(--text-muted)", fontSize: 11.5 }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.map(rt => (
                    <tr key={rt.id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 16px" }}>
                        <code className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", background: "var(--bg)", padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)" }}>
                          {rt.token_prefix ? `${rt.token_prefix}...` : "—"}
                        </code>
                      </td>
                      <td style={{ padding: "8px 16px" }}>
                        {rt.workflow_id
                          ? <a href={`/workflows/${rt.workflow_id}`} style={{ color: "var(--text)", textDecoration: "none" }} onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")} onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}>{rt.workflow_name ?? "—"}</a>
                          : <span style={{ color: "var(--text)" }}>{rt.workflow_name ?? "—"}</span>
                        }
                      </td>
                      <td style={{ padding: "8px 16px" }}>
                        <a href={rt.workflow_id ? `/workflows/${rt.workflow_id}/runs/${rt.run_id}` : `/runs/${rt.run_id}`} style={{ color: "var(--accent)", textDecoration: "none", fontFamily: "monospace", fontSize: 11.5 }}>
                          {rt.run_id.slice(0, 8)}
                        </a>
                      </td>
                      <td style={{ padding: "8px 16px", color: "var(--text-muted)" }}>{fmt(rt.created_at)}</td>
                      <td style={{ padding: "8px 16px", color: rt.first_used_at ? "var(--ok)" : "var(--text-muted)" }}>
                        {rt.first_used_at ? fmt(rt.first_used_at) : "—"}
                      </td>
                      <td style={{ padding: "8px 16px" }}>
                        {rt.invalidated_at
                          ? <span style={{ color: "var(--text-muted)", fontSize: 11.5 }}>Invalidated</span>
                          : <span style={{ color: "var(--ok)", fontWeight: 600, fontSize: 11.5 }}>Active</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
            Run tokens are single-use and workspace-scoped. They are invalidated automatically when their run completes. Every run mints fresh credentials — authority validation happens at the execution boundary on every action.
          </p>
        </div>

    </>
  )
}
