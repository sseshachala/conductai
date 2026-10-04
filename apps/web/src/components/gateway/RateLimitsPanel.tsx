"use client"

import { useEffect, useRef, useState } from "react"
import { Clock, Pencil, RotateCw, Save, X } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import styles from "./RateLimitsPanel.module.css"

type CapFields = { rpm: string; tpm: string }
const MAX_CAP = 2147483647
const valid = (value: string) => value.trim() === "" || (/^\d+$/.test(value) && Number(value) > 0 && Number(value) <= MAX_CAP)
const number = (value: string) => value.trim() === "" ? null : Number(value)
const fields = (cap: { rpm: number | null; tpm: number | null }): CapFields => ({
  rpm: cap.rpm == null ? "" : String(cap.rpm), tpm: cap.tpm == null ? "" : String(cap.tpm),
})

type Props = { isAdmin: boolean; workspaceId: string } & (
  { profileId: string; agentId?: never } | { agentId: string; profileId?: never }
)

export default function RateLimitsPanel({ isAdmin, workspaceId, profileId, agentId }: Props) {
  const { authFetch } = useAuthFetch()
  const generation = useRef(0)
  const stored = useRef<CapFields>({ rpm: "", tpm: "" })
  const [cap, setCap] = useState<CapFields>({ rpm: "", tpm: "" })
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const current = ++generation.current
    setLoaded(false); setSaving(false); setSaved(false); setEditing(false); setErr(null)
    setCap({ rpm: "", tpm: "" })
    if (!isAdmin || !workspaceId || !(profileId || agentId)) return
    const request = agentId
      ? guard.rateLimits.list(authFetch, workspaceId).then(rows => rows.find(row => row.agent_identity_id === agentId) ?? { rpm: null, tpm: null })
      : guard.gatewayProfilesV2.rateLimits.get(authFetch, workspaceId, profileId!)
    request.then(data => {
      if (generation.current !== current) return
      stored.current = fields(data); setCap(stored.current); setLoaded(true)
    }).catch(error => {
      if (generation.current === current) setErr(error instanceof Error ? error.message : "Could not load rate limits.")
    })
    return () => { generation.current++ }
  }, [authFetch, workspaceId, profileId, agentId, isAdmin, reload])

  if (!isAdmin) return null
  const invalid = !valid(cap.rpm) || !valid(cap.tpm)
  const disabled = !loaded || saving

  async function save() {
    if (disabled || invalid || !editing) return
    const current = generation.current
    setSaving(true); setErr(null); setSaved(false)
    try {
      const limits = { rpm: number(cap.rpm), tpm: number(cap.tpm) }
      const result = agentId
        ? await guard.rateLimits.upsert(authFetch, { ...limits, agent_identity_id: agentId }, workspaceId)
        : await guard.gatewayProfilesV2.rateLimits.set(authFetch, workspaceId, profileId!, limits)
      if (generation.current === current) {
        stored.current = fields(result); setCap(stored.current)
        setSaved(true); setEditing(false)
      }
    } catch (error) {
      if (generation.current === current) setErr(error instanceof Error ? error.message : "Could not save rate limits.")
    } finally {
      if (generation.current === current) setSaving(false)
    }
  }

  function change(next: CapFields) { setCap(next); setSaved(false) }
  function cancel() {
    if (saving) return
    setCap(stored.current); setEditing(false); setErr(null); setSaved(false)
  }

  return <section aria-label={agentId ? "Agent rate limits" : "Profile rate limits"} className={styles.panel}>
    <div className={styles.heading}>
      <Clock size={16} aria-hidden="true" /><h3>Rate limits</h3>
      {saved && <span className={styles.saved} role="status">Saved</span>}
      {!editing && <button type="button" className={`btn btn-ghost btn-sm ${styles.edit}`}
        title="Edit limits" disabled={disabled} onClick={() => { setEditing(true); setSaved(false) }}>
        <Pencil size={14} aria-hidden="true" /> Edit limits
      </button>}
    </div>
    <div className={styles.body}>
      <div className={styles.inputs}>
        {(["rpm", "tpm"] as const).map(metric => <label key={metric}>
          <span>{metric === "rpm" ? "Requests / min (RPM)" : "Tokens / min (TPM)"}</span>
          <input type="number" min={1} max={MAX_CAP} step={1} placeholder="unlimited"
            aria-label={metric === "rpm" ? "Requests / min (RPM)" : "Tokens / min (TPM)"}
            value={cap[metric]} disabled={disabled} readOnly={!editing} aria-invalid={!valid(cap[metric])}
            onChange={e => change({ ...cap, [metric]: e.target.value })} />
        </label>)}
      </div>
      {editing && <div className={styles.presets}>
        <span>Presets</span>
        {[{ label: "Smoke test", rpm: 2, tpm: 500 }, { label: "Small team", rpm: 60, tpm: 100000 },
          { label: "Larger team", rpm: 300, tpm: 500000 }].map(p => <button key={p.label}
            type="button" className="btn btn-ghost btn-sm" disabled={disabled}
            onClick={() => change({ rpm: String(p.rpm), tpm: String(p.tpm) })}>{p.label}</button>)}
      </div>}
      {invalid && <div role="alert" className={styles.error}>Enter a positive whole number, or leave the field blank.</div>}
      {err && <div role="alert" className={styles.error}>{err}
        {!loaded && <button type="button" className="btn btn-ghost btn-sm" title="Retry loading limits"
          aria-label="Retry loading limits" onClick={() => setReload(reload + 1)}><RotateCw size={14} /></button>}
      </div>}
      {editing && <div className={styles.actions}>
        <button type="button" onClick={save} disabled={disabled || invalid} className="btn btn-primary btn-sm">
          <Save size={14} aria-hidden="true" /> {saving ? "Saving..." : "Save limits"}
        </button>
        <button type="button" onClick={cancel} disabled={saving} className="btn btn-ghost btn-sm">
          <X size={14} aria-hidden="true" /> Cancel
        </button>
      </div>}
    </div>
  </section>
}
