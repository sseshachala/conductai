"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Check, Copy, RefreshCw, Terminal } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API, guard } from "@/lib/api"
import { publicApiUrl } from "@/lib/auth/runtime"
import { discoveryLabel, discoveryTime, type DiscoveryAgent } from "@/lib/discovery"
import styles from "./ToolSetupPanel.module.css"

const TOOLS = ["claude-code", "codex", "copilot-cli"]
type Model = { id: string; operations: string[] }

export function setupCommand(api: string, web: string): string | null {
  if (web === "https://app.conductai.ai" && api === "https://api.conductai.ai") return "conduct login"
  try {
    for (const value of [api, web]) {
      const url = new URL(value)
      if (!["http:", "https:"].includes(url.protocol) || url.origin !== value.replace(/\/$/, "")
          || /[\s'"`$\\]/.test(value)) return null
    }
    return `conduct login --server "${api}" --web-url "${web}"`
  } catch { return null }
}

function Command({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(false)
  return <div className={styles.command}>
    <code>{value}</code>
    <button className="btn btn-ghost btn-sm btn-icon" aria-label={`Copy ${value}`} title={copied ? "Copied" : "Copy command"}
      onClick={async () => {
        try { await navigator.clipboard.writeText(value); setCopied(true); setError(false) }
        catch { setError(true) }
      }}>{copied ? <Check size={16} /> : <Copy size={16} />}</button>
    {error && <span role="alert">Clipboard unavailable</span>}
  </div>
}

export default function ToolSetupPanel({ workspaceId, isAdmin, enabled = true }: {
  workspaceId: string; isAdmin: boolean; enabled?: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [refresh, setRefresh] = useState(0)
  const [data, setData] = useState<{ workspace: string; agents: DiscoveryAgent[]; models: Model[]; modelError: boolean } | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [login, setLogin] = useState<string | null>(null)
  useEffect(() => { setLogin(setupCommand(publicApiUrl(), window.location.origin)) }, [])
  useEffect(() => {
    if (!enabled || !workspaceId) return
    let cancelled = false
    setData(null); setError(""); setLoading(true)
    async function load() {
      try {
        const response = await authFetch(`${API}/guard/discover/agents?inventory=current&limit=500`)
        if (!response.ok) throw new Error(response.status === 403 ? "Tool inventory access denied." : "Tool inventory unavailable.")
        const agents: DiscoveryAgent[] = await response.json()
        let models: Model[] = []
        let modelError = false
        if (isAdmin) {
          try {
            const profiles = await guard.gatewayProfilesV2.list(authFetch, workspaceId)
            models = await Promise.all(profiles.filter(p => p.active_revision_id).map(async p => {
              const snapshot = await guard.gatewayProfilesV2.revisionSnapshot(authFetch, workspaceId, p.id, p.active_revision_id!)
              return { id: `cond-${p.cond_code}-${snapshot.model_alias}`, operations: Array.isArray(snapshot.accepts) ? snapshot.accepts as string[] : [] }
            }))
          } catch { modelError = true }
        }
        if (!cancelled) setData({ workspace: workspaceId, agents, models, modelError })
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : "Tool inventory unavailable.") }
      finally { if (!cancelled) setLoading(false) }
    }
    void load()
    return () => { cancelled = true }
  }, [workspaceId, isAdmin, enabled, refresh, authFetch])
  const current = data?.workspace === workspaceId ? data : null
  return <section className={styles.panel} aria-label="Tool Setup">
    <header className={styles.header}>
      <h2><Terminal size={20} aria-hidden="true" /> Tool Setup</h2>
      <button className="btn btn-ghost btn-sm btn-icon" aria-label="Refresh tool status" title="Refresh tool status"
        disabled={loading || !workspaceId} onClick={() => setRefresh(n => n + 1)}><RefreshCw size={17} /></button>
    </header>
    <div className={styles.commands}>
      {login ? <Command value={login} /> : <p>Console or public API URL is not configured.</p>}
      <Command value="conduct guard sync" />
      <Command value="conduct guard discover --verify-gateway" />
    </div>
    {!workspaceId && <p>Select a workspace.</p>}
    {loading && <p role="status">Loading tool status...</p>}
    {error && <p role="alert">{error}</p>}
    {TOOLS.map(tool => {
      const agents = current?.agents.filter(a => a.framework === tool) ?? []
      const operation = tool === "claude-code" ? "anthropic_messages" : "openai_responses"
      const models = current?.models.filter(m => m.operations.includes(operation)) ?? []
      return <section className={styles.tool} key={tool} aria-label={discoveryLabel(tool)}>
        <h3>{discoveryLabel(tool)}</h3>
        <div className={styles.table}>
          <table><thead><tr><th>Installation</th><th>Hooks</th><th>MCP</th><th>Gateway</th><th>Last scan</th></tr></thead>
            <tbody>{agents.length ? agents.map(agent => <tr key={agent.id}>
              <td title={`Device ${agent.device_id}; installation ${agent.installation_id}`}><code>{agent.device_id?.slice(0, 8)} / {agent.installation_id?.slice(0, 8)}</code></td>
              <td>{discoveryLabel(agent.hooks_status)}</td>
              <td>{agent.freshness === "fresh" ? agent.mcp_configured ? "Configured" : "Not configured" : "Unknown"}</td>
              <td>{discoveryLabel(agent.gateway_status)}</td>
              <td>{agent.freshness !== "fresh" && <span>Stale · </span>}{discoveryTime(agent.last_seen_at)}</td>
            </tr>) : <tr><td colSpan={5}>{current ? "No installations reported" : "Status unavailable"}</td></tr>}</tbody>
          </table>
        </div>
        <div className={styles.models}><strong>Published models</strong>
          {!isAdmin ? <span>Ask a workspace administrator for approved model IDs.</span>
            : current?.modelError ? <span>Model list unavailable</span>
              : !current ? <span>Not loaded</span>
                : models.length ? models.map(m => <code key={m.id}>{m.id}</code>) : <span>No compatible profiles published</span>}
        </div>
      </section>
    })}
    <footer className={styles.footer}>
      <Link href="/settings?tab=llm_primitives">LLM Model Primitives</Link>
      <Link href="/proxy/gateway-profiles">Gateways</Link>
      <Link href="/theguard/discovery">Agent inventory</Link>
    </footer>
  </section>
}
