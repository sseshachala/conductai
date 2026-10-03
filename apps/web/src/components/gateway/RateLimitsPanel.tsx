"use client"

import { useEffect, useRef, useState } from "react"
import { Clock, Plus, RotateCw, Trash2 } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileRateLimits } from "@/lib/api/guard"
import styles from "./RateLimitsPanel.module.css"

type CapFields = { rpm: string; tpm: string }
type AgentFields = CapFields & { agent_identity_id: string }
const MAX_CAP = 2147483647
const valid = (value: string) => value.trim() === "" || (/^\d+$/.test(value) && Number(value) > 0 && Number(value) <= MAX_CAP)
const number = (value: string) => value.trim() === "" ? null : Number(value)
const fields = (cap: { rpm: number | null; tpm: number | null }): CapFields => ({
  rpm: cap.rpm == null ? "" : String(cap.rpm), tpm: cap.tpm == null ? "" : String(cap.tpm),
})

function CapInputs({ value, onChange, disabled, label = "" }: {
  value: CapFields; onChange: (value: CapFields) => void; disabled: boolean; label?: string
}) {
  return <div className={styles.inputs}>
    {(["rpm", "tpm"] as const).map(metric => <label key={metric}>
      <span>{metric === "rpm" ? "Requests / min (RPM)" : "Tokens / min (TPM)"}</span>
      <input type="number" min={1} max={MAX_CAP} step={1} placeholder="unlimited"
        aria-label={`${label}${metric === "rpm" ? "Requests / min (RPM)" : "Tokens / min (TPM)"}`}
        value={value[metric]} disabled={disabled} aria-invalid={!valid(value[metric])}
        onChange={e => onChange({ ...value, [metric]: e.target.value })} />
    </label>)}
  </div>
}

export default function RateLimitsPanel({ isAdmin, workspaceId, profileId }: {
  isAdmin: boolean; workspaceId: string; profileId: string
}) {
  const { authFetch } = useAuthFetch()
  const generation = useRef(0)
  const [cap, setCap] = useState<CapFields>({ rpm: "", tpm: "" })
  const [agents, setAgents] = useState<GatewayProfileRateLimits["available_agents"]>([])
  const [agentCaps, setAgentCaps] = useState<AgentFields[]>([])
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [selectedAgent, setSelectedAgent] = useState("")

  useEffect(() => {
    const current = ++generation.current
    setLoaded(false); setSaving(false); setSaved(false); setErr(null)
    setCap({ rpm: "", tpm: "" }); setAgentCaps([]); setAgents([]); setSelectedAgent("")
    if (!isAdmin || !workspaceId || !profileId) return
    guard.gatewayProfilesV2.rateLimits.get(authFetch, workspaceId, profileId).then(data => {
      if (generation.current !== current) return
      setCap(fields(data))
      setAgentCaps(data.agent_limits.map(a => ({ ...fields(a), agent_identity_id: a.agent_identity_id })))
      setAgents(data.available_agents)
      setLoaded(true)
    }).catch(error => {
      if (generation.current === current) setErr(error instanceof Error ? error.message : "Could not load rate limits.")
    })
    return () => { generation.current++ }
  }, [authFetch, workspaceId, profileId, isAdmin, reload])

  if (!isAdmin) return null
  const invalid = [cap, ...agentCaps].some(c => !valid(c.rpm) || !valid(c.tpm))
  const disabled = !loaded || saving
  const available = agents.filter(a => !agentCaps.some(c => c.agent_identity_id === a.id))

  async function save() {
    if (disabled || invalid) return
    const current = generation.current
    setSaving(true); setErr(null); setSaved(false)
    try {
      await guard.gatewayProfilesV2.rateLimits.set(authFetch, workspaceId, profileId, {
        rpm: number(cap.rpm), tpm: number(cap.tpm),
        agent_limits: agentCaps.map(c => ({ agent_identity_id: c.agent_identity_id, rpm: number(c.rpm), tpm: number(c.tpm) })),
      })
      if (generation.current === current) setSaved(true)
    } catch (error) {
      if (generation.current === current) setErr(error instanceof Error ? error.message : "Could not save rate limits.")
    } finally {
      if (generation.current === current) setSaving(false)
    }
  }

  function change(next: CapFields) { setCap(next); setSaved(false) }

  return <section aria-label="Profile rate limits" className={styles.panel}>
    <div className={styles.heading}>
      <Clock size={16} aria-hidden="true" />
      <h3>Rate limits</h3>
      {saved && <span className={styles.saved} role="status">Saved</span>}
    </div>
    <div className={styles.body}>
      <CapInputs value={cap} onChange={change} disabled={disabled} />
      <div className={styles.presets}>
        <span>Presets</span>
        {[{ label: "Smoke test", rpm: 2, tpm: 500 }, { label: "Small team", rpm: 60, tpm: 100000 },
          { label: "Larger team", rpm: 300, tpm: 500000 }].map(p => <button key={p.label}
            type="button" className="btn btn-ghost btn-sm" disabled={disabled}
            onClick={() => change({ rpm: String(p.rpm), tpm: String(p.tpm) })}>{p.label}</button>)}
      </div>
      {(agentCaps.length > 0 || available.length > 0) && <div className={styles.agents}>
        <h4>Additional agent limits</h4>
        {agentCaps.map((value, index) => {
          const name = agents.find(a => a.id === value.agent_identity_id)?.name || value.agent_identity_id
          return <div key={value.agent_identity_id} className={styles.agent}>
            <div className={styles.agentHeading}><span>{name}</span>
              <button type="button" className="btn btn-ghost btn-sm" title={`Remove ${name} limit`}
                aria-label={`Remove ${name} limit`} disabled={disabled}
                onClick={() => { setAgentCaps(agentCaps.filter((_, i) => i !== index)); setSaved(false) }}>
                <Trash2 size={14} />
              </button>
            </div>
            <CapInputs value={value} label={`${name} `} disabled={disabled}
              onChange={next => { setAgentCaps(agentCaps.map((c, i) => i === index ? { ...c, ...next } : c)); setSaved(false) }} />
          </div>
        })}
        {available.length > 0 && agentCaps.length < 200 && <div className={styles.add}>
          <select aria-label="Agent identity" value={selectedAgent} disabled={disabled}
            onChange={e => setSelectedAgent(e.target.value)}>
            <option value="">Select agent</option>
            {available.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <button type="button" className="btn btn-ghost btn-sm" title="Add agent limit" aria-label="Add agent limit"
            disabled={disabled || !selectedAgent} onClick={() => {
              setAgentCaps([...agentCaps, { agent_identity_id: selectedAgent, rpm: "", tpm: "" }])
              setSelectedAgent(""); setSaved(false)
            }}><Plus size={16} /></button>
        </div>}
      </div>}
      {invalid && <div role="alert" className={styles.error}>Enter a positive whole number, or leave the field blank.</div>}
      {err && <div role="alert" className={styles.error}>{err}
        {!loaded && <button type="button" className="btn btn-ghost btn-sm" title="Retry loading limits"
          aria-label="Retry loading limits" onClick={() => setReload(reload + 1)}><RotateCw size={14} /></button>}
      </div>}
      <div><button type="button" onClick={save} disabled={disabled || invalid} className="btn btn-primary btn-sm">
        {saving ? "Saving..." : "Save limits"}
      </button></div>
    </div>
  </section>
}
