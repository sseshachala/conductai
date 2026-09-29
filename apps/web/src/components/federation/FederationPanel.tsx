"use client"
import { useEffect, useRef, useState } from "react"
import { Pencil, Plus, RefreshCw, ShieldCheck } from "lucide-react"
import { TabBar } from "@/components/TabBar"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { ApprovalForm } from "./ApprovalForm"
import { ConnectionForm } from "./ConnectionForm"
import { Approval, ApprovalKind, Connection, Overview, Save, apiError, approvalBody, connectionPath } from "./types"
import s from "./federation.module.css"

const labels: Record<ApprovalKind, string> = { principals: "Principals", bindings: "Caller bindings", grants: "Grants" }

export function FederationPanel({ workspace, mode }: { workspace: string; mode: "connections" | "delegation" }) {
  const { authFetch } = useAuthFetch()
  const fetchRef = useRef(authFetch)
  fetchRef.current = authFetch
  const alive = useRef(true)
  const [data, setData] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [tab, setTab] = useState<ApprovalKind>("principals")
  const [edit, setEdit] = useState<string | null>(null)
  const [pending, setPending] = useState<{ message: string; path: string; body: unknown } | null>(null)
  const base = `/workspaces/${workspace}/federation`

  async function request(path: string, options?: RequestInit) {
    const response = await fetchRef.current(`${API}${path}`, options)
    const result = await response.json()
    if (response.status === 403 && alive.current) setData(null)
    if (!response.ok) throw new Error(apiError(response.status, result.detail))
    return result
  }
  async function load() {
    const result = await request(`${base}/overview`)
    if (alive.current) setData(result)
  }
  useEffect(() => {
    alive.current = true
    if (workspace) void load().catch(e => { if (alive.current) setError(e.message) }).finally(() => { if (alive.current) setLoading(false) })
    else setLoading(false)
    return () => { alive.current = false }
    // Parent keys this component by workspace; authFetch is read through its latest ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace])

  const save: Save = async (path, body, method = "PUT") => {
    setBusy(true); setError(""); setNotice("")
    try {
      await request(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      await load()
      if (alive.current) { setNotice("Saved."); setPending(null) }
      return true
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : "Save failed.")
      return false
    } finally { if (alive.current) setBusy(false) }
  }
  async function refresh() {
    setLoading(true); setError(""); setEdit(null); setPending(null)
    try { await load() } catch (e) { setData(null); setError(e instanceof Error ? e.message : "Refresh failed.") }
    finally { setLoading(false) }
  }
  async function validate(row: Connection) {
    setBusy(true); setError(""); setNotice("")
    try {
      const result = await request(`${connectionPath(workspace, row)}/validate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: row.revision, config: row.config }),
      })
      if (alive.current) setNotice(`Metadata and ${result.signing_keys} signing key(s) validated at ${new Date(result.validated_at).toLocaleString()}. User authentication and grants are not verified by this check.`)
    } catch (e) { if (alive.current) setError(e instanceof Error ? e.message : "Validation failed.") }
    finally { if (alive.current) setBusy(false) }
  }
  function changeConnection(row: Connection) {
    const status = row.config.status === "active" ? "disabled" : "active"
    setPending({ message: status === "active" ? `Enable trust for ${row.name}? Principals and grants still require separate approval.`
      : `Disable ${row.name}? Bound callers and pending delegated workflows will be denied.`,
    path: connectionPath(workspace, row), body: { expected_revision: row.revision, config: { ...row.config, status } } })
  }
  function changeApproval(row: Approval) {
    const status = row.status === "active" ? "disabled" : "active"
    setPending({ message: `${status === "disabled" ? "Revoke" : "Enable"} this ${tab === "bindings" ? "caller binding" : tab.slice(0, -1)}? Dependent calls and workflows are rechecked at execution.`,
      path: `${base}/${tab}/${row.id}`, body: { ...approvalBody(row), status } })
  }
  const callerName = (id?: string) => data?.callers.find(c => c.id === id)?.name ?? id
  const bindingName = (id?: string) => callerName(data?.bindings.find(b => b.id === id)?.caller_id) ?? id
  return <section className={s.root} aria-label={mode === "connections" ? "OIDC connections" : "Federation delegation"}>
    <div className={s.head}>
      <h2>{mode === "connections" ? "OIDC connections" : "External identity and delegation"}</h2>
      <div className={s.actions}>
        <button className="btn btn-ghost btn-icon" title="Refresh" aria-label="Refresh federation" disabled={busy || loading} onClick={() => void refresh()}><RefreshCw size={16} /></button>
        {data && !(mode === "connections" && edit) && <button className="btn btn-primary" disabled={busy || loading} onClick={() => { setEdit("new"); setPending(null); setNotice("") }}><Plus size={16} />{mode === "connections" ? "New connection" : `Add ${tab === "bindings" ? "binding" : tab.slice(0, -1)}`}</button>}
      </div>
    </div>
    {error && <div role="alert" className={s.error}>{error}</div>}
    {notice && <div role="status" className={s.notice}>{notice}</div>}
    {loading ? <p role="status">Loading federation...</p> : data && <>
      {mode === "delegation" && <TabBar tabs={["principals", "bindings", "grants"] as const} labels={labels} activeTab={tab} idPrefix="federation" onSelect={value => { setTab(value); setEdit(null); setPending(null) }} />}
      {pending && <div role="alertdialog" aria-label="Confirm authorization change" className={s.confirm}>
        <p>{pending.message}</p><div className={s.actions}>
          <button className="btn btn-primary" disabled={busy} onClick={() => void save(pending.path, pending.body)}>Confirm</button>
          <button className="btn btn-ghost" disabled={busy} onClick={() => setPending(null)}>Cancel</button>
        </div>
      </div>}
      {edit && (mode === "connections"
        ? <ConnectionForm key={edit} row={data.connections.find(c => c.id === edit)} workspace={workspace} save={save} busy={busy} close={() => setEdit(null)} />
        : <ApprovalForm key={`${tab}:${edit}`} kind={tab} row={data[tab].find(r => r.id === edit)} data={data} workspace={workspace} save={save} busy={busy} close={() => setEdit(null)} />)}
      {mode === "connections" ? !edit && <>
        {!data.connections.length ? <p className={s.notice}>No OIDC connections configured.</p> : <div className={s.tableWrap}><table className={s.table}>
          <thead><tr><th>Connection</th><th>Issuer</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>{data.connections.map(row => <tr key={row.id}>
            <td>{row.name}<div className={s.muted}>Revision {row.revision}</div><div className={s.muted}>{row.id}</div></td>
            <td>{row.config.issuer}<div className={s.muted}>Audience: {row.config.audience}</div></td><td>{row.config.status}</td>
            <td><div className={s.actions}>
              <button className="btn btn-ghost btn-icon" title={`Edit ${row.name}`} aria-label={`Edit ${row.name}`} disabled={busy} onClick={() => setEdit(row.id)}><Pencil size={16} /></button>
              <button className="btn btn-ghost btn-icon" title={`Validate ${row.name}`} aria-label={`Validate ${row.name}`} disabled={busy} onClick={() => void validate(row)}><ShieldCheck size={16} /></button>
              <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => changeConnection(row)}>{row.config.status === "active" ? "Disable" : "Enable"}</button>
            </div></td>
          </tr>)}</tbody>
        </table></div>}
        <p><a href="/agent-identity?tab=delegation">Manage principals and delegation</a></p>
      </> : <div id={`tabpanel-${tab}`} role="tabpanel" aria-labelledby={`federation-${tab}`}>
        {!data[tab].length ? <p className={s.notice}>No {labels[tab].toLowerCase()} configured.</p> : <div className={s.tableWrap}><table className={s.table}>
          <thead><tr><th>{tab === "principals" ? "Principal" : tab === "bindings" ? "Service caller" : "Delegation"}</th><th>Approved actions</th><th>Status / expiry</th><th>Actions</th></tr></thead>
          <tbody>{data[tab].map(row => <tr key={row.id}>
            <td>{tab === "principals" ? <>{row.subject}<div className={s.muted}>{row.kind} / {row.issuer}</div></> : tab === "bindings" ? <>{callerName(row.caller_id)}<div className={s.muted}>{data.connections.find(c => c.id === row.connection_id)?.name}</div></> : <>{bindingName(row.binding_id)}<div className={s.muted}>{data.principals.find(p => p.id === row.principal_id)?.subject ?? row.principal_id}</div></>}<div className={s.muted}>Revision {row.revision}</div></td>
            <td>{row.actions.map(a => <div key={a}>{a}</div>)}</td>
            <td>{row.expires_at && Date.parse(row.expires_at) <= Date.now() ? "expired" : row.status}{row.expires_at && <div className={s.muted}>{new Date(row.expires_at).toLocaleString()} ({Intl.DateTimeFormat().resolvedOptions().timeZone})</div>}</td>
            <td><div className={s.actions}>
              <button className="btn btn-ghost btn-icon" title="Edit approval" aria-label={`Edit ${row.subject ?? row.id}`} disabled={busy} onClick={() => setEdit(row.id)}><Pencil size={16} /></button>
              <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => changeApproval(row)}>{row.status === "active" ? "Revoke" : "Enable"}</button>
            </div></td>
          </tr>)}</tbody>
        </table></div>}
        <p><a href="/agent-identity?tab=integrations&integration=oidc">Manage OIDC connections</a></p>
      </div>}
    </>}
  </section>
}
