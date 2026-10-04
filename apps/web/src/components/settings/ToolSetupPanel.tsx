"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Check, Copy, RefreshCw, Terminal } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API, guard } from "@/lib/api"
import { publicApiUrl } from "@/lib/auth/runtime"
import styles from "./ToolSetupPanel.module.css"
import { setupTools } from "@/lib/toolCatalog"

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
  const [data, setData] = useState<{ workspace: string; models: Model[] } | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [login, setLogin] = useState<string | null>(null)
  const [identity, setIdentity] = useState<{ workspace: string; id: string; name: string } | null>(null)
  const [identityError, setIdentityError] = useState(false)
  useEffect(() => { setLogin(setupCommand(publicApiUrl(), window.location.origin)) }, [])
  useEffect(() => {
    let current = true
    setIdentity(null); setIdentityError(false)
    if (!enabled || !workspaceId) return
    authFetch(`${API}/auth/cli-identity?${new URLSearchParams({ workspace_id: workspaceId })}`).then(async response => {
      if (!response.ok) throw new Error("Identity unavailable")
      const result = await response.json()
      if (!current) return
      if (result.workspace_id === workspaceId && result.identity) {
        setIdentity({ workspace: workspaceId, id: result.identity.id, name: result.identity.name })
      }
    }).catch(() => { if (current) setIdentityError(true) })
    return () => { current = false }
  }, [authFetch, workspaceId, enabled, refresh])
  useEffect(() => {
    setData(null); setError(""); setLoading(false)
    if (!enabled || !workspaceId || !isAdmin) return
    let cancelled = false
    setLoading(true)
    async function load() {
      try {
        const profiles = await guard.gatewayProfilesV2.list(authFetch, workspaceId)
        const models = await Promise.all(profiles.filter(p => p.active_revision_id).map(async p => {
          const snapshot = await guard.gatewayProfilesV2.revisionSnapshot(authFetch, workspaceId, p.id, p.active_revision_id!)
          return { id: `cond-${p.cond_code}-${snapshot.model_alias}`, operations: Array.isArray(snapshot.accepts) ? snapshot.accepts as string[] : [] }
        }))
        if (!cancelled) setData({ workspace: workspaceId, models })
      } catch { if (!cancelled) setError("Published models unavailable.") }
      finally { if (!cancelled) setLoading(false) }
    }
    void load()
    return () => { cancelled = true }
  }, [workspaceId, isAdmin, enabled, refresh, authFetch])
  const current = data?.workspace === workspaceId ? data : null
  return <section className={styles.panel} aria-label="Tool Setup">
    <header className={styles.header}>
      <h2><Terminal size={20} aria-hidden="true" /> Tool Setup</h2>
      {isAdmin && <button className="btn btn-ghost btn-sm btn-icon" aria-label="Refresh published models" title="Refresh published models"
        disabled={loading || !workspaceId} onClick={() => setRefresh(n => n + 1)}><RefreshCw size={17} /></button>}
    </header>
    <div className={styles.commands}>
      {login ? <Command value={login} /> : <p>Console or public API URL is not configured.</p>}
      <Command value="conduct guard sync" />
      <Command value="conduct whoami" />
    </div>
    {identity?.workspace === workspaceId ? <div className={styles.models}>
      <strong>Linked CLI identity</strong>
      <Link href={`/agent-identity?tab=identities&id=${encodeURIComponent(identity.id)}`}>{identity.name}</Link>
      <code>{identity.id}</code>
    </div> : <div className={styles.models}><strong>Linked CLI identity</strong>
      <span>{identityError ? "Unavailable" : "None"}</span>
    </div>}
    {!workspaceId && <p>Select a workspace.</p>}
    {loading && <p role="status">Loading published models...</p>}
    {error && <p role="alert">{error}</p>}
    {setupTools.map(descriptor => {
      const tool = descriptor.id
      const operation = descriptor.gateway?.operation
      const models = operation ? current?.models.filter(m => m.operations.includes(operation)) ?? [] : []
      return <section className={styles.tool} key={tool} aria-label={descriptor.label}>
        <h3>{descriptor.label}</h3>
        {!descriptor.gateway ? <div className={styles.models}>Gateway adapter pending</div> : <div className={styles.models}><strong>Published models</strong>
          {!isAdmin ? <span>Ask a workspace administrator for approved model IDs.</span>
            : error ? <span>Model list unavailable</span>
              : !current ? <span>Not loaded</span>
                : models.length ? models.map(m => <code key={m.id}>{m.id}</code>) : <span>No compatible profiles published</span>}
        </div>}
      </section>
    })}
    <footer className={styles.footer}>
      <Link href="/settings?tab=llm_primitives">LLM Model Primitives</Link>
      <Link href="/proxy/gateway-profiles">Gateways</Link>
      <Link href="/theguard/discovery">Agent Discovery</Link>
    </footer>
  </section>
}
