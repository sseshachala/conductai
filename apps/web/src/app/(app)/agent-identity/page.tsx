"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface RunToken {
  id: string
  run_id: string
  token_prefix: string | null
  workflow_id: string | null
  workflow_name: string | null
  created_at: string | null
  first_used_at: string | null
  invalidated_at: string | null
}

export default function AgentIdentityPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <WithAuth />
  return <Inner getToken={null} />
}

function WithAuth() {
  const { getToken } = useAuth()
  return <Inner getToken={getToken} />
}

function Inner({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""
  const apiUrl = process.env.NEXT_PUBLIC_API_URL

  const [tokens, setTokens] = useState<RunToken[]>([])
  const [loading, setLoading] = useState(true)

  const headers = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    if (workspaceId) h["X-Workspace-Id"] = workspaceId
    return h
  }, [getToken, workspaceId])

  const load = useCallback(async () => {
    if (!workspaceId || !apiUrl) return
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/agent-run-tokens`, { headers: h })
      if (r.ok) setTokens(await r.json())
    } catch {}
    setLoading(false)
  }, [workspaceId, apiUrl, headers])

  useEffect(() => { load() }, [load])

  function fmt(d: string | null) {
    if (!d) return "—"
    return new Date(d).toLocaleDateString("en-GB", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: 0 }}>Agent Identity</h1>
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>
            Short-lived tokens minted for each run. Each token is scoped to a single run and invalidated when it ends.
          </p>
        </div>

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

        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Tokens are single-use and workspace-scoped. They are invalidated automatically when their run completes.
        </p>
      </div>
    </AppShell>
  )
}
