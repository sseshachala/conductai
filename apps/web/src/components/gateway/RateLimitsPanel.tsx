"use client"

import { useEffect, useRef, useState } from "react"
import { Clock, Pencil, Plus, RotateCw, Save, Trash2, X } from "lucide-react"
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

function agentOptions(agents: GatewayProfileRateLimits["available_agents"]) {
  const unique = Array.from(new Map(agents.map(agent => [agent.id, agent])).values()).map(agent => ({
    ...agent,
    name: /^(?:user_|oidc_)\S+ \(auto\)$/.test(agent.name.trim()) ? "Auto-provisioned agent" : agent.name,
  }))
  return unique.map(agent => {
    const peers = unique.filter(other => other.name === agent.name && other.id !== agent.id)
    if (!peers.length && agent.name !== "Auto-provisioned agent") return { ...agent, label: agent.name }
    let length = 8
    while (length < agent.id.length && peers.some(other => other.id.startsWith(agent.id.slice(0, length)))) length++
    return { ...agent, label: `${agent.name} (${agent.id.slice(0, length)})` }
  })
}

function CapInputs({ value, onChange, disabled, readOnly, label = "" }: {
  value: CapFields; onChange: (value: CapFields) => void; disabled: boolean; readOnly: boolean; label?: string
}) {
  return <div className={styles.inputs}>
    {(["rpm", "tpm"] as const).map(metric => <label key={metric}>
      <span>{metric === "rpm" ? "Requests / min (RPM)" : "Tokens / min (TPM)"}</span>
      <input type="number" min={1} max={MAX_CAP} step={1} placeholder="unlimited"
        aria-label={`${label}${metric === "rpm" ? "Requests / min (RPM)" : "Tokens / min (TPM)"}`}
        value={value[metric]} disabled={disabled} readOnly={readOnly} aria-invalid={!valid(value[metric])}
        onChange={e => onChange({ ...value, [metric]: e.target.value })} />
    </label>)}
  </div>
}

export default function RateLimitsPanel({ isAdmin, workspaceId, profileId, agentOnly = false }: {
  isAdmin: boolean; workspaceId: string; profileId: string; agentOnly?: boolean
}) {
  const { authFetch } = useAuthFetch()
  const generation = useRef(0)
  const stored = useRef<{ cap: CapFields; agentCaps: AgentFields[] }>({ cap: { rpm: "", tpm: "" }, agentCaps: [] })
  const [cap, setCap] = useState<CapFields>({ rpm: "", tpm: "" })
  const [agents, setAgents] = useState<GatewayProfileRateLimits["available_agents"]>([])
  const [agentCaps, setAgentCaps] = useState<AgentFields[]>([])
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [selectedAgent, setSelectedAgent] = useState("")

  useEffect(() => {
    const current = ++generation.current
    setLoaded(false); setSaving(false); setSaved(false); setEditing(false); setErr(null)
    setCap({ rpm: "", tpm: "" }); setAgentCaps([]); setAgents([]); setSelectedAgent("")
    if (!isAdmin || !workspaceId || !profileId) return
    guard.gatewayProfilesV2.rateLimits.get(authFetch, workspaceId, profileId).then(data => {
      if (generation.current !== current) return
      stored.current = { cap: fields(data),
        agentCaps: data.agent_limits.map(a => ({ ...fields(a), agent_identity_id: a.agent_identity_id })) }
      setCap(stored.current.cap)
      setAgentCaps(stored.current.agentCaps)
      setAgents(data.available_agents)
      setLoaded(true)
    }).catch(error => {
      if (generation.current === current) setErr(error instanceof Error ? error.message : "Could not load rate limits.")
    })
    return () => { generation.current++ }
  }, [authFetch, workspaceId, profileId, isAdmin, agentOnly, reload])

  if (!isAdmin) return null
  const invalid = [cap, ...agentCaps].some(c => !valid(c.rpm) || !valid(c.tpm))
  const disabled = !loaded || saving
  const options = agentOptions(agents)
  const available = options.filter(a => !agentCaps.some(c => c.agent_identity_id === a.id))

  async function save() {
    if (disabled || invalid || !editing) return
    const current = generation.current
    setSaving(true); setErr(null); setSaved(false)
    try {
      const agent_limits = agentCaps.map(c => ({ agent_identity_id: c.agent_identity_id, rpm: number(c.rpm), tpm: number(c.tpm) }))
      const result = await guard.gatewayProfilesV2.rateLimits.set(authFetch, workspaceId, profileId,
        agentOnly ? { agent_limits } : { rpm: number(cap.rpm), tpm: number(cap.tpm), agent_limits })
      if (generation.current === current) {
        const savedCap = agentOnly ? fields(result) : cap
        stored.current = { cap: savedCap, agentCaps }
        setCap(savedCap)
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
    setCap(stored.current.cap); setAgentCaps(stored.current.agentCaps)
    setSelectedAgent(""); setEditing(false); setErr(null); setSaved(false)
  }

  return <section aria-label="Profile rate limits" className={styles.panel}>
    <div className={styles.heading}>
      <Clock size={16} aria-hidden="true" />
      <h3>Rate limits</h3>
      {saved && <span className={styles.saved} role="status">Saved</span>}
      {!editing && <button type="button" className={`btn btn-ghost btn-sm ${styles.edit}`}
        title="Edit limits" disabled={disabled} onClick={() => { setEditing(true); setSaved(false) }}>
        <Pencil size={14} aria-hidden="true" /> Edit limits
      </button>}
    </div>
    <div className={styles.body}>
      {agentOnly && <h4 className={styles.subheading}>Profile limit</h4>}
      <CapInputs value={cap} onChange={change} disabled={disabled} readOnly={!editing || agentOnly} />
      {editing && !agentOnly && <div className={styles.presets}>
        <span>Presets</span>
        {[{ label: "Smoke test", rpm: 2, tpm: 500 }, { label: "Small team", rpm: 60, tpm: 100000 },
          { label: "Larger team", rpm: 300, tpm: 500000 }].map(p => <button key={p.label}
            type="button" className="btn btn-ghost btn-sm" disabled={disabled}
            onClick={() => change({ rpm: String(p.rpm), tpm: String(p.tpm) })}>{p.label}</button>)}
      </div>}
      {(agentCaps.length > 0 || available.length > 0) && <div className={styles.agents}>
        <h4>Additional agent limits</h4>
        {!editing && agentCaps.length === 0 && <span className={styles.empty}>No agent limits set.</span>}
        {agentCaps.map((value, index) => {
          const name = options.find(a => a.id === value.agent_identity_id)?.label || value.agent_identity_id
          return <div key={value.agent_identity_id} className={styles.agent}>
            <div className={styles.agentHeading}><span>{name}</span>
              {editing && <button type="button" className="btn btn-ghost btn-sm" title={`Remove ${name} limit`}
                aria-label={`Remove ${name} limit`} disabled={disabled}
                onClick={() => { setAgentCaps(agentCaps.filter((_, i) => i !== index)); setSaved(false) }}>
                <Trash2 size={14} />
              </button>}
            </div>
            <CapInputs value={value} label={`${name} `} disabled={disabled} readOnly={!editing}
              onChange={next => { setAgentCaps(agentCaps.map((c, i) => i === index ? { ...c, ...next } : c)); setSaved(false) }} />
          </div>
        })}
        {editing && available.length > 0 && agentCaps.length < 200 && <div className={styles.add}>
          <select aria-label="Agent identity" value={selectedAgent} disabled={disabled}
            onChange={e => setSelectedAgent(e.target.value)}>
            <option value="">Select agent</option>
            {available.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
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
