"use client"

import { useEffect, useState } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { workspaces as workspacesApi, type AuditFeedStatus } from "@/lib/api/workspaces"

const SETUP_CMD = "conduct audit feed --follow --output /var/log/conduct/audit.ndjson"
const DOCS_URL = "https://github.com/sseshachala/conductai/blob/main/docs/reference/siem-feed.md"
const REFRESH_MS = 60_000

export function ago(seconds: number): string {
  if (seconds < 90) return `${Math.max(0, Math.round(seconds))}s`
  if (seconds < 90 * 60) return `${Math.round(seconds / 60)}m`
  if (seconds < 48 * 3600) return `${Math.round(seconds / 3600)}h`
  return `${Math.round(seconds / 86400)}d`
}

function sinceIso(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 1000
}

export default function SiemFeedCard({ workspaceId }: { workspaceId?: string }) {
  const { activeWorkspace } = useWorkspace()
  const { authFetch } = useAuthFetch()
  const [status, setStatus] = useState<AuditFeedStatus | null>(null)
  const [hidden, setHidden] = useState(false)
  const [copied, setCopied] = useState(false)
  const ws = workspaceId || activeWorkspace?.id || ""

  useEffect(() => {
    if (!ws) return
    let alive = true
    const load = () =>
      workspacesApi.auditFeedStatus(authFetch, ws)
        .then(s => { if (alive) setStatus(s) })
        .catch(() => { if (alive) setHidden(true) })  // no permission or API down: hide the card
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => { alive = false; clearInterval(t) }
  }, [ws])

  if (hidden || !status) return null

  const collectors = status.collectors
  const anyLive = collectors.some(c => !c.stale)
  const badge = !status.available
    ? { text: "Status unavailable", color: "var(--text-3)", bg: "var(--surface-3)", bd: "var(--border)" }
    : collectors.length === 0
      ? { text: "Not connected", color: "var(--text-3)", bg: "var(--surface-3)", bd: "var(--border)" }
      : anyLive
        ? { text: "Receiving", color: "var(--ok)", bg: "var(--ok-bg)", bd: "var(--ok-bd)" }
        : { text: "Stale", color: "var(--warn)", bg: "var(--warn-bg)", bd: "var(--warn-bd)" }

  async function copy() {
    try { await navigator.clipboard.writeText(SETUP_CMD); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* ignore */ }
  }

  return (
    <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }} aria-label="SIEM feed">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", margin: 0 }}>SIEM feed</h3>
          <p style={{ fontSize: 12, color: "var(--text-3)", margin: "2px 0 0" }}>
            Guard audit events pulled by your SIEM collector (Splunk, Sentinel, Falcon LogScale).
          </p>
        </div>
        <span
          data-testid="siem-feed-badge"
          style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, color: badge.color, background: badge.bg, border: `1px solid ${badge.bd}`, whiteSpace: "nowrap" }}
        >
          {badge.text}
        </span>
      </div>

      {status.chain_complete_from !== undefined && (
        <p data-testid="chain-complete-from" style={{ fontSize: 12, color: "var(--text-2)", margin: 0 }}>
          {status.chain_complete_from
            ? <>Hash chain complete from <time dateTime={status.chain_complete_from} title={status.chain_complete_from}>{new Date(status.chain_complete_from).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</time>. Earlier gateway events predate chaining and cannot be verified.</>
            : "No hash-chained events yet."}
        </p>
      )}

      {collectors.length > 0 && (
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ color: "var(--text-3)", textAlign: "left" }}>
              <th style={{ fontWeight: 500, padding: "4px 0" }}>Collector</th>
              <th style={{ fontWeight: 500 }}>Last pull</th>
              <th style={{ fontWeight: 500 }}>Behind</th>
              <th style={{ fontWeight: 500 }}>Last page</th>
            </tr>
          </thead>
          <tbody>
            {collectors.map(c => (
              <tr key={c.actor_id} style={{ color: "var(--text-2)", borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 0" }}>{c.actor_email ?? c.actor_id}</td>
                <td style={{ color: c.stale ? "var(--warn)" : undefined }}>
                  {ago(sinceIso(c.last_pull_at))} ago{c.stale ? " (stale)" : ""}
                </td>
                <td>{ago(c.lag_seconds)}</td>
                <td>{c.last_page_events} events</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(collectors.length === 0 || !anyLive) && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <p style={{ fontSize: 12, color: "var(--text-2)", margin: 0 }}>
            {collectors.length === 0
              ? "Run the collector on a host your SIEM agent reads from:"
              : `No pull in the last ${Math.round(status.stale_after_seconds / 60)} minutes. Check the collector is running:`}
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <code style={{ flex: 1, fontSize: 12, padding: "6px 8px", borderRadius: 6, background: "var(--surface-3)", color: "var(--text)", overflowX: "auto", whiteSpace: "nowrap" }}>
              {SETUP_CMD}
            </code>
            <button onClick={copy} className="btn btn-ghost btn-sm" aria-label="Copy collector command">
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <a href={DOCS_URL} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>
            SIEM feed setup guide
          </a>
        </div>
      )}
    </div>
  )
}
