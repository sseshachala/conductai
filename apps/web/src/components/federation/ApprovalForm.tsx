"use client"
import { useState } from "react"
import { Save as SaveIcon } from "lucide-react"
import { Approval, ApprovalKind, Overview, Save, approvalBody, principalLabel } from "./types"
import s from "./federation.module.css"

export function ApprovalForm({ kind, row, data, workspace, save, busy, close }: {
  kind: ApprovalKind; row?: Approval; data: Overview; workspace: string; save: Save; busy: boolean; close: () => void
}) {
  const [draft, setDraft] = useState<Approval>(row ?? {
    id: crypto.randomUUID(), revision: 0, status: "active", actions: [],
    ...(kind === "principals" ? { issuer: "", subject: "", kind: "human" as const }
      : kind === "bindings" ? { caller_id: "", connection_id: "" }
      : { binding_id: "", principal_id: "", expires_at: "" }),
  })
  const update = (values: Partial<Approval>) => setDraft(d => ({ ...d, ...values }))
  const binding = data.bindings.find(b => b.id === draft.binding_id)
  const connection = data.connections.find(c => c.id === binding?.connection_id)
  const principal = data.principals.find(p => p.id === draft.principal_id)
  const available = kind === "grants" ? data.actions.filter(a => binding?.actions.includes(a) && principal?.actions.includes(a)) : data.actions
  const label = kind === "principals" ? "principal" : kind === "bindings" ? "caller binding" : "grant"
  return <form className={s.form} onSubmit={async e => {
    e.preventDefault()
    if (await save(`/workspaces/${workspace}/federation/${kind}/${draft.id}`, approvalBody(draft))) close()
  }}>
    <fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }}>
      <legend className={s.notice}>{row ? "Edit" : "Approve"} {label}</legend>
      <div className={s.grid}>
        {kind === "principals" && <>
          <label className={s.field}>Name (optional)<input maxLength={200} value={draft.display_name ?? ""} onChange={e => update({ display_name: e.target.value })} /></label>
          <label className={s.field}>Issuer<select required disabled={!!row} value={draft.issuer} onChange={e => update({ issuer: e.target.value })}>
            <option value="">Select issuer</option>
            {[...new Set([...data.connections.map(c => c.config.issuer), ...(row?.issuer ? [row.issuer] : [])])].map(issuer => <option key={issuer}>{issuer}</option>)}
          </select></label>
          <label className={s.field}>Subject<input required maxLength={512} disabled={!!row} value={draft.subject} onChange={e => update({ subject: e.target.value })} /></label>
          <label className={s.field}>Principal type<select disabled={!!row} value={draft.kind} onChange={e => update({ kind: e.target.value as "human" | "workload" })}><option value="human">Human</option><option value="workload">Workload</option></select></label>
        </>}
        {kind === "bindings" && <>
          <label className={s.field}>Service caller<select required disabled={!!row} value={draft.caller_id} onChange={e => update({ caller_id: e.target.value })}>
            <option value="">Select API identity</option>
            {row && !data.callers.some(c => c.id === row.caller_id) && <option value={row.caller_id}>{row.caller_id} (inactive)</option>}
            {data.callers.filter(c => c.id === row?.caller_id || !data.bindings.some(b => b.caller_id === c.id)).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></label>
          <label className={s.field}>OIDC connection<select required disabled={!!row} value={draft.connection_id} onChange={e => update({ connection_id: e.target.value })}>
            <option value="">Select active connection</option>
            {data.connections.filter(c => c.config.status === "active" || c.id === row?.connection_id).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></label>
        </>}
        {kind === "grants" && <>
          <label className={s.field}>Resource scope<input value="Current workspace" readOnly /></label>
          <label className={s.field}>Caller binding<select required disabled={!!row} value={draft.binding_id} onChange={e => update({ binding_id: e.target.value, principal_id: "", actions: [] })}>
            <option value="">Select binding</option>
            {data.bindings.filter(b => b.status === "active" || b.id === row?.binding_id).map(b => <option key={b.id} value={b.id}>{data.callers.find(c => c.id === b.caller_id)?.name ?? b.caller_id} / {data.connections.find(c => c.id === b.connection_id)?.name}</option>)}
          </select></label>
          <label className={s.field}>Principal<select required disabled={!!row} value={draft.principal_id} onChange={e => update({ principal_id: e.target.value, actions: [] })}>
            <option value="">Select principal</option>
            {data.principals.filter(p => p.id === row?.principal_id || (p.status === "active" && p.issuer === connection?.config.issuer)).map(p => <option key={p.id} value={p.id}>{principalLabel(p)}{p.display_name?.trim() ? ` (${p.subject})` : ""}</option>)}
          </select></label>
          <label className={s.field}>Expires at (UTC)<input type="datetime-local" required value={draft.expires_at ? new Date(draft.expires_at).toISOString().slice(0, 16) : ""} onChange={e => update({ expires_at: e.target.value ? new Date(`${e.target.value}Z`).toISOString() : "" })} /></label>
        </>}
      </div>
      <fieldset className={s.checks}><legend>Approved actions</legend>
        {data.actions.map(action => <label key={action}><input type="checkbox" checked={draft.actions.includes(action)} disabled={!available.includes(action) && !draft.actions.includes(action)} onChange={e => update({ actions: e.target.checked ? [...draft.actions, action] : draft.actions.filter(a => a !== action) })} />{action}</label>)}
      </fieldset>
      {kind === "bindings" && <p className={s.notice}>Binding makes subject evidence mandatory for this caller. Disabling the binding will block it, not restore service-only access.</p>}
      <div className={s.actions}>
        <button className="btn btn-primary" type="submit" disabled={!draft.actions.length || draft.actions.some(a => !available.includes(a))}><SaveIcon size={16} /> {busy ? "Saving..." : row ? "Save approval" : `Approve ${label}`}</button>
        <button type="button" className="btn btn-ghost" onClick={close}>Cancel</button>
      </div>
    </fieldset>
  </form>
}
