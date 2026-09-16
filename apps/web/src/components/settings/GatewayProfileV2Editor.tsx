"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { credentials, guard } from "@/lib/api"
import type { GatewayProfileV2Out, GatewayProfileV2Target } from "@/lib/api/guard"
import {
  ALL_OPERATIONS,
  type Operation,
  type Transport,
  validateTargetsAgainstAccepts,
} from "@/lib/gatewayCapabilityCatalog"

// #2007 — Gateway Profile v2 draft editor. Loads a profile's working_copy,
// renders it as a form (name, model_alias, accepts, timeouts, ordered
// target list with add/remove/reorder), and saves back via
// PUT /working_copy. Matches the styling of the sibling GatewayProfileSettings
// (v1) component so both settings pages feel like one product.

const KNOWN_LITELLM_PROVIDERS = ["anthropic", "openai"]
const KNOWN_INTEGRATIONS = [
  "portkey", "openrouter", "helicone_anthropic",
  "helicone_openai", "azure_openai", "custom",
] as const

type EnvironmentRow = { id: string; name: string }
type CredentialRow = { handle: string }

interface DraftTarget {
  id: string
  transport: Transport
  provider: string
  integration: string
  model: string
  credential_env_id: string
  credential_handle: string
  endpoint: string
}

interface EditorState {
  name: string
  model_alias: string
  accepts: Operation[]
  timeout_seconds: number
  max_attempts: number
  targets: DraftTarget[]
}

function nextTargetId(existing: DraftTarget[]): string {
  let i = 1
  const ids = new Set(existing.map(t => t.id))
  while (ids.has(`target-${i}`)) i += 1
  return `target-${i}`
}

function emptyTarget(existing: DraftTarget[]): DraftTarget {
  return {
    id: nextTargetId(existing),
    transport: "litellm_sdk",
    provider: "anthropic",
    integration: "portkey",
    model: "",
    credential_env_id: "",
    credential_handle: "",
    endpoint: "",
  }
}

function parseVaultRef(ref: string | undefined): { env: string; handle: string } {
  const match = String(ref ?? "").match(/^vault:\/\/([0-9a-f-]{36})\/([^/]+)$/i)
  return match ? { env: match[1], handle: match[2] } : { env: "", handle: "" }
}

function stateFromProfile(profile: GatewayProfileV2Out): EditorState {
  const wc = (profile.working_copy as {
    name?: string; model_alias?: string; accepts?: Operation[]
    timeout_seconds?: number; max_attempts?: number
    targets?: Array<Record<string, unknown>>
  } | null) ?? {}
  const targets: DraftTarget[] = (wc.targets ?? []).map((t, i) => {
    const cred = parseVaultRef(t.credential_ref as string | undefined)
    return {
      id: String(t.id ?? `target-${i + 1}`),
      transport: (t.transport as Transport) ?? "litellm_sdk",
      provider: String(t.provider ?? "anthropic"),
      integration: String(t.integration ?? "portkey"),
      model: String(t.model ?? ""),
      credential_env_id: cred.env,
      credential_handle: cred.handle,
      endpoint: String(t.endpoint ?? ""),
    }
  })
  return {
    name: wc.name ?? profile.name,
    model_alias: wc.model_alias ?? profile.model_alias ?? "",
    accepts: wc.accepts ?? ["anthropic_messages"],
    timeout_seconds: wc.timeout_seconds ?? 60,
    max_attempts: wc.max_attempts ?? 2,
    targets: targets.length ? targets : [emptyTarget([])],
  }
}

function stateToWorkingCopy(s: EditorState): Record<string, unknown> {
  const targets: GatewayProfileV2Target[] = s.targets.map(t => {
    const ref = t.credential_env_id && t.credential_handle
      ? `vault://${t.credential_env_id}/${t.credential_handle}`
      : ""
    if (t.transport === "litellm_sdk") {
      return { id: t.id, transport: "litellm_sdk", provider: t.provider, model: t.model, credential_ref: ref }
    }
    return {
      id: t.id, transport: "http_passthrough", integration: t.integration,
      model: t.model, credential_ref: ref, endpoint: t.endpoint || null,
    }
  })
  return {
    name: s.name, model_alias: s.model_alias, accepts: s.accepts,
    timeout_seconds: s.timeout_seconds, max_attempts: s.max_attempts, targets,
  }
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px",
  border: "1px solid var(--border)", borderRadius: 7,
  background: "var(--surface)", color: "var(--text)", fontSize: 13,
}

export default function GatewayProfileV2Editor({
  workspaceId, profile, envs, isAdmin, onSaved,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  isAdmin: boolean
  onSaved: () => void
}) {
  const { authFetch } = useAuthFetch()
  const [state, setState] = useState<EditorState>(() => stateFromProfile(profile))
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")
  const [err, setErr] = useState("")
  const [credsByEnv, setCredsByEnv] = useState<Record<string, CredentialRow[]>>({})

  useEffect(() => {
    setState(stateFromProfile(profile))
    setMsg(""); setErr("")
  }, [profile])

  const loadCreds = useCallback(async (envId: string) => {
    if (!envId || credsByEnv[envId]) return
    try {
      const rows = await credentials.byEnvironment(authFetch, envId)
      setCredsByEnv(prev => ({ ...prev, [envId]: rows as CredentialRow[] }))
    } catch {
      setCredsByEnv(prev => ({ ...prev, [envId]: [] }))
    }
  }, [authFetch, credsByEnv])

  const catalogErrors = useMemo(() => validateTargetsAgainstAccepts({
    accepts: state.accepts,
    targets: state.targets.map(t => t.transport === "litellm_sdk"
      ? { id: t.id, transport: "litellm_sdk", provider: t.provider }
      : { id: t.id, transport: "http_passthrough", integration: t.integration as any }),
  }), [state])

  async function save() {
    if (!isAdmin) return
    setSaving(true); setErr(""); setMsg("")
    try {
      await guard.gatewayProfilesV2.updateWorkingCopy(
        authFetch, workspaceId, profile.id, stateToWorkingCopy(state),
      )
      setMsg("Working copy saved")
      onSaved()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed")
    } finally { setSaving(false) }
  }

  function patch(u: Partial<EditorState>) { setState(s => ({ ...s, ...u })); setMsg("") }
  function patchTarget(i: number, u: Partial<DraftTarget>) {
    setState(s => ({ ...s, targets: s.targets.map((t, j) => j === i ? { ...t, ...u } : t) }))
    setMsg("")
  }
  function removeTarget(i: number) {
    setState(s => ({ ...s, targets: s.targets.filter((_, j) => j !== i) }))
    setMsg("")
  }
  function addTarget() {
    setState(s => ({ ...s, targets: [...s.targets, emptyTarget(s.targets)] }))
  }
  function move(i: number, dir: -1 | 1) {
    setState(s => {
      const next = [...s.targets]
      const j = i + dir
      if (j < 0 || j >= next.length) return s
      ;[next[i], next[j]] = [next[j], next[i]]
      return { ...s, targets: next }
    })
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12 }}>
        <label style={{ fontSize: 12 }}>Name
          <input value={state.name} disabled={!isAdmin}
            onChange={e => patch({ name: e.target.value })} style={inputStyle} />
        </label>
        <label style={{ fontSize: 12 }}>Model alias
          <input value={state.model_alias} disabled={!isAdmin}
            onChange={e => patch({ model_alias: e.target.value })}
            placeholder="e.g. coding" style={inputStyle} />
        </label>
        <label style={{ fontSize: 12 }}>Timeout (seconds)
          <input type="number" min={1} value={state.timeout_seconds} disabled={!isAdmin}
            onChange={e => patch({ timeout_seconds: Math.max(1, Number(e.target.value) || 1) })}
            style={inputStyle} />
        </label>
        <label style={{ fontSize: 12 }}>Max attempts
          <input type="number" min={1} max={10} value={state.max_attempts} disabled={!isAdmin}
            onChange={e => patch({ max_attempts: Math.max(1, Number(e.target.value) || 1) })}
            style={inputStyle} />
        </label>
      </div>

      <div>
        <label style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
          Accepts (operations this alias serves)
        </label>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          {ALL_OPERATIONS.map(op => (
            <label key={op} style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 12.5 }}>
              <input type="checkbox" disabled={!isAdmin}
                checked={state.accepts.includes(op)}
                onChange={() => patch({
                  accepts: state.accepts.includes(op)
                    ? state.accepts.filter(o => o !== op)
                    : [...state.accepts, op],
                })} />
              <span className="mono" style={{ fontSize: 12 }}>{op}</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-2)" }}>
            Targets ({state.targets.length}) — list order is priority
          </span>
          {isAdmin && (
            <button onClick={addTarget} className="btn btn-ghost btn-sm">+ Add target</button>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {state.targets.map((t, i) => (
            <TargetRow key={i} index={i} target={t} envs={envs} isAdmin={isAdmin}
              credentialsByEnv={credsByEnv} onLoadCredsFor={loadCreds}
              onChange={u => patchTarget(i, u)}
              onRemove={() => removeTarget(i)}
              onMoveUp={() => move(i, -1)} onMoveDown={() => move(i, 1)}
              isFirst={i === 0} isLast={i === state.targets.length - 1} />
          ))}
        </div>
      </div>

      {catalogErrors.length > 0 && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>Capability catalog: {catalogErrors.length} issue(s)</strong>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            {catalogErrors.map((e, i) => (
              <li key={i} style={{ fontSize: 12, fontWeight: 400 }}>
                <span className="mono">{e.target_id}</span> ({e.where}) can't serve{" "}
                <span className="mono">{e.missing.join(", ")}</span>. {e.hint}
              </li>
            ))}
          </ul>
        </div>
      )}

      {err && <p style={{ margin: 0, color: "var(--err)", fontSize: 12 }}>{err}</p>}
      {msg && <p style={{ margin: 0, color: "var(--ok)", fontSize: 12 }}>{msg}</p>}

      {isAdmin && (
        <div>
          <button onClick={save} disabled={saving} className="btn btn-primary btn-sm">
            {saving ? "Saving…" : "Save working copy"}
          </button>
        </div>
      )}
    </div>
  )
}


function TargetRow({
  index, target, envs, isAdmin, credentialsByEnv, onLoadCredsFor,
  onChange, onRemove, onMoveUp, onMoveDown, isFirst, isLast,
}: {
  index: number
  target: DraftTarget
  envs: EnvironmentRow[]
  isAdmin: boolean
  credentialsByEnv: Record<string, CredentialRow[]>
  onLoadCredsFor: (envId: string) => void
  onChange: (u: Partial<DraftTarget>) => void
  onRemove: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  isFirst: boolean
  isLast: boolean
}) {
  const creds = target.credential_env_id ? credentialsByEnv[target.credential_env_id] ?? [] : []
  return (
    <div className="card" style={{ padding: 12, display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr 1fr auto", gap: 10, alignItems: "end" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "center" }}>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={onMoveUp} disabled={!isAdmin || isFirst}
          style={{ height: 24, width: 24, opacity: isFirst ? 0.35 : 1 }} title="Move up">↑</button>
        <span style={{ fontSize: 11, color: "var(--text-3)" }}>#{index + 1}</span>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={onMoveDown} disabled={!isAdmin || isLast}
          style={{ height: 24, width: 24, opacity: isLast ? 0.35 : 1 }} title="Move down">↓</button>
      </div>

      <label style={{ fontSize: 12 }}>ID
        <input value={target.id} disabled={!isAdmin}
          onChange={e => onChange({ id: e.target.value })} style={inputStyle} />
      </label>

      <label style={{ fontSize: 12 }}>Transport
        <select value={target.transport} disabled={!isAdmin}
          onChange={e => onChange({ transport: e.target.value as Transport })} style={inputStyle}>
          <option value="litellm_sdk">litellm_sdk</option>
          <option value="http_passthrough">http_passthrough</option>
        </select>
      </label>

      {target.transport === "litellm_sdk" ? (
        <label style={{ fontSize: 12 }}>Provider
          <select value={target.provider} disabled={!isAdmin}
            onChange={e => onChange({ provider: e.target.value })} style={inputStyle}>
            {KNOWN_LITELLM_PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      ) : (
        <label style={{ fontSize: 12 }}>Integration
          <select value={target.integration} disabled={!isAdmin}
            onChange={e => onChange({ integration: e.target.value })} style={inputStyle}>
            {KNOWN_INTEGRATIONS.map(i => <option key={i} value={i}>{i}</option>)}
          </select>
        </label>
      )}

      <label style={{ fontSize: 12 }}>Model
        <input value={target.model} disabled={!isAdmin} placeholder="claude-sonnet-4-6"
          onChange={e => onChange({ model: e.target.value })} style={inputStyle} />
      </label>

      {isAdmin ? (
        <button onClick={onRemove} className="btn btn-ghost btn-sm btn-icon"
          style={{ color: "var(--err)", borderColor: "var(--err-bd)" }} title="Remove target">×</button>
      ) : <div />}

      <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
        <label style={{ fontSize: 12 }}>Credential vault
          <select value={target.credential_env_id} disabled={!isAdmin}
            onChange={e => {
              const envId = e.target.value
              onChange({ credential_env_id: envId, credential_handle: "" })
              onLoadCredsFor(envId)
            }} style={inputStyle}>
            <option value="">— pick vault —</option>
            {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 12 }}>Credential handle
          {creds.length > 0 ? (
            <select value={target.credential_handle} disabled={!isAdmin}
              onChange={e => onChange({ credential_handle: e.target.value })} style={inputStyle}>
              <option value="">— pick —</option>
              {creds.map(c => <option key={c.handle} value={c.handle}>{c.handle}</option>)}
            </select>
          ) : (
            <input value={target.credential_handle} disabled={!isAdmin} placeholder="anthropic"
              onChange={e => onChange({ credential_handle: e.target.value })} style={inputStyle} />
          )}
        </label>
        {target.transport === "http_passthrough" ? (
          <label style={{ fontSize: 12 }}>Endpoint (optional)
            <input value={target.endpoint} disabled={!isAdmin} placeholder="https://…"
              onChange={e => onChange({ endpoint: e.target.value })} style={inputStyle} />
          </label>
        ) : <div />}
      </div>
    </div>
  )
}
