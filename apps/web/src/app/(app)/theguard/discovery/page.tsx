"use client"

import { useEffect, useRef, useState } from "react"
import { Copy, RefreshCw, Search, X } from "lucide-react"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { GuardPageHeader } from "@/components/guard/common"
import { AskLensLink } from "@/components/glens/AskLensLink"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import { discoveryLabel, discoveryTime, type DiscoveryAgent, type DiscoverySummary } from "@/lib/discovery"

type Scan = { id: string; status: string; triggered_by: string; started_at: string; agents_found: number; errors: string[] }
const cell = "px-3 py-3 text-left align-top border-b border-stone-200 text-sm"

function Evidence({ agent, workspaceId, close }: { agent: DiscoveryAgent; workspaceId: string; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [copyState, setCopyState] = useState("")
  useEffect(() => { dialog.current?.showModal() }, [])
  async function copy() {
    try { await navigator.clipboard.writeText(agent.remediation.command!); setCopyState("Copied") }
    catch { setCopyState("Unable to copy") }
  }
  return <dialog ref={dialog} onClose={close} aria-labelledby="discovery-evidence-title"
    className="m-0 ml-auto h-full max-h-full w-full max-w-lg border-l border-stone-200 p-6 backdrop:bg-black/30"
    style={{ background: "var(--surface)", color: "var(--text)" }}>
    <div className="flex items-center justify-between gap-4">
      <h2 id="discovery-evidence-title" className="text-lg font-semibold">{discoveryLabel(agent.framework)}</h2>
      <button className="btn btn-ghost btn-icon btn-sm" aria-label="Close evidence" title="Close evidence" onClick={() => dialog.current?.close()}><X size={18}/></button>
    </div>
    <dl className="my-6 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-3 text-sm">
      <dt>Device</dt><dd className="break-all font-mono">{agent.device_id ?? "Not recorded"}</dd>
      <dt>Detection</dt><dd>{discoveryLabel(agent.detection)}</dd>
      <dt>Last scan / detection</dt><dd>{discoveryTime(agent.last_seen_at)}</dd>
      <dt>Hook activity</dt><dd>{discoveryTime(agent.hook_observed_at)}</dd>
      <dt>Hooks</dt><dd>{discoveryLabel(agent.hooks_status)}</dd>
      <dt>Gateway</dt><dd>{discoveryLabel(agent.gateway_status)}</dd>
      {agent.gateway_checked_at && <><dt>Connection checked</dt><dd>{discoveryTime(agent.gateway_checked_at)}</dd></>}
      <dt>MCP</dt><dd>{agent.mcp_configured ? "Configured" : "Unverified"}</dd>
    </dl>
    <h3 className="font-semibold text-sm">Evidence</h3>
    <ul className="my-3 list-disc pl-5 text-sm">{(agent.evidence.signals ?? []).map(s => <li key={s}>{discoveryLabel(s)}</li>)}</ul>
    {agent.evidence.config_unreadable && <p className="text-sm text-amber-700">Configuration could not be read.</p>}
    <p className="text-sm text-stone-500">{agent.evidence_note}</p>
    <section className="mt-6 border-t border-stone-200 pt-4">
      <h3 className="font-semibold text-sm">{agent.remediation.label}</h3>
      <p className="my-3 text-sm">{agent.remediation.detail}</p>
      {agent.remediation.command && <div className="flex items-center justify-between gap-3 bg-stone-100 p-3">
        <code className="break-all text-sm">{agent.remediation.command}</code>
        <button className="btn btn-ghost btn-icon btn-sm shrink-0" title="Copy command" aria-label="Copy command" onClick={copy}><Copy size={16}/></button>
      </div>}
      <p role="status" className="text-sm">{copyState}</p>
    </section>
    {agent.gateway_remediation && <section className="mt-6 border-t border-stone-200 pt-4">
      <h3 className="text-sm font-semibold">{agent.gateway_remediation.label}</h3>
      <p className="my-3 text-sm">{agent.gateway_remediation.detail}</p>
      {agent.gateway_status !== "connection_verified" && <code className="block break-all bg-stone-100 p-3 text-sm">{agent.gateway_remediation.command}</code>}
    </section>}
    {agent.hook_event_id && <div className="mt-5 flex flex-wrap gap-3" onClick={() => dialog.current?.close()}>
      <a className="btn btn-ghost btn-sm" href={`/logs/guard?id=${encodeURIComponent(agent.hook_event_id)}`}>Flight Recorder</a>
      <AskLensLink kind="event" resourceId={agent.hook_event_id} workspaceId={workspaceId}/>
    </div>}
  </dialog>
}

export default function DiscoveryPage() {
  const { workspaceId } = useAuthFetch()
  return <AppShell><GuardShell>{workspaceId
    ? <WorkspaceDiscovery key={workspaceId} workspaceId={workspaceId}/>
    : <p className="p-6">Select a workspace.</p>
  }</GuardShell></AppShell>
}

function WorkspaceDiscovery({ workspaceId }: { workspaceId: string }) {
  const { authFetch } = useAuthFetch()
  const [summary, setSummary] = useState<DiscoverySummary | null>(null)
  const [agents, setAgents] = useState<DiscoveryAgent[]>([])
  const [scans, setScans] = useState<Scan[]>([])
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [limit, setLimit] = useState(100)
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState("current")
  const inventory = filter === "legacy_unverified" ? "legacy" : filter === "all" ? "all" : "current"
  const [selected, setSelected] = useState<DiscoveryAgent | null>(null)
  useEffect(() => {
    let active = true
    setLoading(true); setError("")
    const pages = Promise.all(Array.from({ length: Math.ceil(limit / 100) }, (_, page) =>
      guard.discover.agents(authFetch, page * 100, 100, inventory))).then(results => results.flat())
    Promise.all([guard.discover.summary(authFetch), pages, guard.discover.scans(authFetch)])
      .then(([sum, rows, history]) => { if (active) { setSummary(sum); setAgents(rows); setScans(history) } })
      .catch(() => { if (active) setError("Unable to load discovery. Try again.") })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [authFetch, workspaceId, revision, limit, inventory])
  const visible = agents.filter(a => (!query || `${a.framework} ${a.device_id ?? ""}`.toLowerCase().includes(query.toLowerCase())) &&
    (filter === "all" || filter === "current" && a.detection !== "legacy_unverified" || (filter === "attention" ? a.hooks_status !== "observed" || a.freshness !== "fresh" : a.detection === filter)))
  const total = summary ? inventory === "legacy" ? summary.legacy_unverified : inventory === "current" ? summary.total - (summary.legacy_unverified ?? 0) : summary.total : agents.length
  return <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
    <div className="flex items-start justify-between gap-3">
      <GuardPageHeader title="Agent Discovery"/>
      <button className="btn btn-ghost btn-icon btn-sm shrink-0" aria-label="Refresh discovery" title="Refresh discovery" disabled={loading}
        onClick={() => { setSelected(null); setRevision(r => r + 1) }}><RefreshCw size={18}/></button>
    </div>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {loading && <p role="status">Loading discovery...</p>}
    {summary && <dl className="grid grid-cols-2 gap-5 border-y border-stone-200 py-5 md:grid-cols-4">
      {[["Tool installations", summary.confirmed], ["Possible integrations", summary.possible_integrations],
        ["Recent hook activity", summary.recent_hook_evidence], ["Needs review", summary.needs_attention]].map(([label, count]) =>
        <div key={label}><dt className="text-xs text-stone-500">{label}</dt><dd className="mt-1 text-2xl font-semibold">{count}</dd></div>)}
    </dl>}
    {!loading && !error && summary?.total === 0 && <div className="py-8"><p>No discovery findings.</p><code className="text-sm">conduct guard discover</code></div>}
    {!!summary?.total && <>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2"><Search size={16}/><input aria-label="Search tool or device" placeholder="Tool or device" value={query}
          onChange={e => setQuery(e.target.value)} className="min-w-0 rounded border border-stone-300 px-3 py-2 text-sm"/></label>
        <select aria-label="Filter findings" value={filter} onChange={e => { setFilter(e.target.value); setLimit(100) }} className="rounded border border-stone-300 px-3 py-2 text-sm">
          <option value="current">Current findings</option><option value="all">All including legacy</option><option value="attention">Needs review</option><option value="installed">Installed</option>
          <option value="running">Running at scan</option><option value="possible_integration">Possible integrations</option><option value="legacy_unverified">Legacy / unverified</option>
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[800px] border-collapse"><thead><tr>{["Tool / device", "Detection", "Hooks", "Gateway", "Last scan / detection", ""].map(h =>
          <th key={h} className={cell + " font-medium text-stone-500"}>{h}</th>)}</tr></thead>
          <tbody>{visible.map(a => <tr key={a.id}>
            <td className={cell}><strong>{discoveryLabel(a.framework)}</strong><div className="font-mono text-xs text-stone-500">{a.device_id?.slice(0, 8) ?? "Legacy device"}</div></td>
            <td className={cell}>{discoveryLabel(a.detection)}</td><td className={cell}>{discoveryLabel(a.hooks_status)}</td>
            <td className={cell}>{discoveryLabel(a.gateway_status)}</td>
            <td className={cell}>{discoveryTime(a.last_seen_at)}<div className="text-xs text-stone-500">{discoveryLabel(a.freshness)}</div></td>
            <td className={cell}><button className="btn btn-ghost btn-sm" onClick={() => setSelected(a)}>Evidence</button></td>
          </tr>)}</tbody>
        </table>
      </div>
      {!visible.length && <p>No findings match these filters.</p>}
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-stone-500">
        <p>{visible.length} shown from {agents.length} loaded / {total} findings</p>
        {summary && agents.length < total && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => setLimit(n => n + 100)}>Load more</button>}
      </div>
    </>}
    {scans.length > 0 && <section className="border-t border-stone-200 pt-5">
      <h2 className="mb-3 text-base font-semibold">Recent scans</h2>
      <div className="overflow-x-auto"><table className="w-full min-w-[600px]"><thead><tr>{["Started (UTC)", "Source", "Findings", "Status"].map(h => <th key={h} className={cell}>{h}</th>)}</tr></thead>
        <tbody>{scans.map(s => <tr key={s.id}><td className={cell}>{discoveryTime(s.started_at)}</td><td className={cell}>{s.triggered_by}</td><td className={cell}>{s.agents_found}</td>
          <td className={cell}>{s.status}{s.errors?.length > 0 && <div className="text-xs text-amber-700">{s.errors.join(", ")}</div>}</td></tr>)}</tbody>
      </table></div>
    </section>}
    {selected && <Evidence agent={selected} workspaceId={workspaceId} close={() => setSelected(null)}/>}
  </div>
}
