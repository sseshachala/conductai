"use client"

import { useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

type ToolCoverage = Array<{
  detected_tools: string[]
  mcp_registered: string[]
  hook_registered: string[]
}>

export default function SyncPanel({
  workspaceId,
  isAdmin,
}: {
  workspaceId: string | null
  isAdmin: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [toolCoverage, setToolCoverage] = useState<ToolCoverage | null>(null)
  const [resyncing, setResyncing] = useState(false)
  const [resyncDone, setResyncDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!workspaceId) return
    guard.developerTools.list(authFetch, workspaceId)
      .then(d => { if (d) setToolCoverage(d) })
      .catch(() => {})
  }, [authFetch, workspaceId])

  async function handleResync() {
    if (!workspaceId || resyncing) return
    setResyncing(true)
    setResyncDone(false)
    try {
      const res = await guard.config.resync(authFetch, workspaceId)
      if (!res.ok) throw new Error(`Resync failed (${res.status})`)
      setResyncDone(true)
      setTimeout(() => setResyncDone(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resync failed")
    } finally {
      setResyncing(false)
    }
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
      <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Sync status</div>
        {toolCoverage === null ? (
          <div style={{ height: 40 }} />
        ) : (() => {
          const total = toolCoverage.length
          const synced = toolCoverage.filter(dev =>
            dev.detected_tools.every(t =>
              dev.mcp_registered.includes(t) || dev.hook_registered.includes(t)
            )
          ).length
          const allGood = total === 0 || synced === total
          return (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 26, fontWeight: 700, color: allGood ? "var(--ok)" : "var(--warn)" }}>
                  {total === 0 ? "—" : `${synced}/${total}`}
                </span>
                <span style={{ fontSize: 13, color: "var(--text-3)" }}>machines in sync</span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>
                Policies propagate within <strong style={{ color: "var(--text-2)" }}>60s</strong> of a change.
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 14, fontSize: 12.5, color: allGood ? "var(--ok)" : "var(--warn)" }}>
                <span className="conduct-pulse-dot" style={{ background: allGood ? "var(--ok)" : "var(--warn)" }} />
                {total === 0 ? "No developers connected yet" : allGood ? "All developers up to date" : `${total - synced} developer${total - synced !== 1 ? "s" : ""} need sync — run: conduct guard sync`}
              </div>
            </>
          )
        })()}
      </div>
      <div className="card" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 12 }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M23 4v6h-6M1 20v-6h6" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>Re-sync all machines</div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Force a policy push now</div>
        </div>
        <button
          className="btn btn-ghost btn-sm"
          disabled={!isAdmin || resyncing}
          style={{ opacity: isAdmin ? 1 : 0.5 }}
          onClick={handleResync}
        >
          {resyncing ? "Syncing…" : resyncDone ? "Synced" : "Re-sync"}
        </button>
        {error && (
          <span style={{ fontSize: 11, color: "var(--err)" }}>{error}</span>
        )}
      </div>
    </div>
  )
}
