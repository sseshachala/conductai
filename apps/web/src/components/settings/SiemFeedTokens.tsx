"use client"

import { useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { workspaces as workspacesApi, type AuditFeedToken } from "@/lib/api/workspaces"

/**
 * Admin-managed, read-only audit-feed tokens (cond_feed_*). Not tied to a
 * person's login, so the SIEM collector keeps working when they leave. The
 * plaintext is shown once at creation.
 */
export default function SiemFeedTokens({ workspaceId }: { workspaceId: string }) {
  const { authFetch } = useAuthFetch()
  const [open, setOpen] = useState(false)
  const [tokens, setTokens] = useState<AuditFeedToken[] | null>(null)
  const [name, setName] = useState("")
  const [fresh, setFresh] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      setTokens(await workspacesApi.auditFeedTokens.list(authFetch, workspaceId))
      setError(null)
    } catch {
      setTokens(null)
      setError("Only workspace admins can manage feed tokens.")
    }
  }

  function toggle() {
    const next = !open
    setOpen(next)
    if (next) void load()
  }

  async function create() {
    if (!name.trim() || busy) return
    setBusy(true)
    try {
      const created = await workspacesApi.auditFeedTokens.create(authFetch, workspaceId, { name: name.trim() })
      setFresh(created.token)
      setName("")
      await load()
    } catch {
      setError("Could not create the token.")
    } finally {
      setBusy(false)
    }
  }

  async function revoke(id: string) {
    if (!window.confirm("Revoke this token? The collector using it stops receiving events immediately.")) return
    const res = await workspacesApi.auditFeedTokens.revoke(authFetch, workspaceId, id)
    if (!res.ok) setError("Could not revoke the token.")
    await load()
  }

  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <button onClick={toggle} className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} aria-expanded={open}>
        {open ? "Hide feed tokens" : "Feed tokens"}
      </button>
      {open && (
        <>
          <p style={{ fontSize: 12, color: "var(--text-3)", margin: 0 }}>
            Read-only tokens that can only read this audit feed. Not tied to a person&apos;s login. Save the token to a file and run
            {" "}<code>conduct audit feed --token-file PATH</code> (or set <code>CONDUCT_FEED_TOKEN</code>).
          </p>
          {error && <p role="alert" style={{ fontSize: 12, color: "var(--warn)", margin: 0 }}>{error}</p>}
          {fresh && (
            <div data-testid="feed-token-once" style={{ fontSize: 12, padding: 8, borderRadius: 6, background: "var(--surface-3)" }}>
              <div style={{ color: "var(--text-2)", marginBottom: 4 }}>Copy this token now. It will not be shown again.</div>
              <code style={{ wordBreak: "break-all", color: "var(--text)" }}>{fresh}</code>
              <div style={{ marginTop: 6 }}>
                <button className="btn btn-ghost btn-sm" onClick={() => setFresh(null)}>Done</button>
              </div>
            </div>
          )}
          {tokens && (
            <>
              {tokens.length > 0 && (
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                  <tbody>
                    {tokens.map(t => (
                      <tr key={t.id} style={{ color: "var(--text-2)", borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "6px 0" }}>{t.name}</td>
                        <td><code>{t.token_prefix}…</code></td>
                        <td>{t.status}</td>
                        <td style={{ textAlign: "right" }}>
                          {t.status === "active" && (
                            <button className="btn btn-ghost btn-sm" onClick={() => revoke(t.id)} aria-label={`Revoke ${t.name}`}>
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={name} onChange={e => setName(e.target.value)} placeholder="Token name (e.g. splunk-prod)"
                  aria-label="Feed token name" maxLength={80}
                  style={{ flex: 1, fontSize: 12, padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
                />
                <button onClick={create} disabled={!name.trim() || busy} className="btn btn-sm">Create token</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
