"use client"
import { useState } from "react"
import { Plus, Save as SaveIcon, Trash2 } from "lucide-react"
import { Connection, Save, TrustConfig, connectionPath } from "./types"
import s from "./federation.module.css"

const initial: TrustConfig = {
  status: "draft", integration_type: "generic", method: "oauth_access_token",
  issuer: "", audience: "", jwks_uri: "", discovery_uri: null,
  token_profile: "at+jwt", algorithms: ["RS256"], claim_mappings: [],
}

export function ConnectionForm({ row, workspace, save, busy, close }: {
  row?: Connection; workspace: string; save: Save; busy: boolean; close: () => void
}) {
  const [name, setName] = useState(row?.name ?? "")
  const [config, setConfig] = useState<TrustConfig>(row?.config ?? initial)
  const [confirm, setConfirm] = useState(false)
  const update = (values: Partial<TrustConfig>) => { setConfig(c => ({ ...c, ...values })); setConfirm(false) }
  async function submit() {
    const body = row ? { expected_revision: row.revision, config } : { name: name.trim(), config }
    if (await save(row ? connectionPath(workspace, row) : `/workspaces/${workspace}/federation/connections`, body, row ? "PUT" : "POST")) close()
  }
  return <form className={s.form} onSubmit={e => {
    e.preventDefault()
    if (row?.config.status === "active" && !confirm) setConfirm(true)
    else void submit()
  }}>
    <fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }}>
      <legend className={s.notice}>{row ? `Edit ${row.name}` : "New OIDC connection"}</legend>
      <div className={s.grid}>
        {!row && <label className={s.field}>Connection name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>}
        <label className={s.field}>Issuer URL<input type="url" required value={config.issuer} onChange={e => update({ issuer: e.target.value })} /></label>
        <label className={s.field}>Audience<input required maxLength={512} value={config.audience} onChange={e => update({ audience: e.target.value })} /></label>
        <label className={s.field}>JWKS URL<input type="url" required value={config.jwks_uri} onChange={e => update({ jwks_uri: e.target.value })} /></label>
        <label className={s.field}>Discovery URL (optional)<input type="url" value={config.discovery_uri ?? ""} onChange={e => update({ discovery_uri: e.target.value || null })} /></label>
        <label className={s.field}>Access token profile<select value={config.token_profile} onChange={e => update({ token_profile: e.target.value as TrustConfig["token_profile"] })}>
          <option value="at+jwt">JWT header: at+jwt</option><option value="token_use_access">Claim: token_use=access</option>
        </select></label>
        <label className={s.field}>Signing algorithm<input value="RS256" readOnly /></label>
      </div>
      <div className={s.mappings}>
        <strong>Claim mappings</strong>
        {config.claim_mappings.map((mapping, i) => <div className={s.mapping} key={i}>
          <label className={s.field}>Attribute {i + 1}<input required value={mapping.name} onChange={e => update({ claim_mappings: config.claim_mappings.map((m, j) => j === i ? { ...m, name: e.target.value } : m) })} /></label>
          <label className={s.field}>Source claim {i + 1}<input required value={mapping.source_claim} onChange={e => update({ claim_mappings: config.claim_mappings.map((m, j) => j === i ? { ...m, source_claim: e.target.value } : m) })} /></label>
          <button type="button" className="btn btn-ghost btn-icon" title="Remove mapping" aria-label={`Remove mapping ${i + 1}`} onClick={() => update({ claim_mappings: config.claim_mappings.filter((_, j) => j !== i) })}><Trash2 size={16} /></button>
        </div>)}
        <div><button type="button" className="btn btn-ghost btn-sm" disabled={config.claim_mappings.length >= 32} onClick={() => update({ claim_mappings: [...config.claim_mappings, { name: "", source_claim: "" }] })}><Plus size={14} /> Add mapping</button></div>
      </div>
      {confirm && <p role="alert" className={s.confirm}>Changing active trust invalidates existing delegated evidence, including pending workflows. Save these changes?</p>}
      <div className={s.actions}>
        <button className="btn btn-primary" type="submit"><SaveIcon size={16} /> {busy ? "Saving..." : confirm ? "Confirm changes" : row ? "Save changes" : "Save draft"}</button>
        <button type="button" className="btn btn-ghost" onClick={close}>Cancel</button>
      </div>
    </fieldset>
  </form>
}
