"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { credentials, guard } from "@/lib/api"
import type { GatewayProfileV2Out, GatewayProfileV2Target } from "@/lib/api/guard"
import {
  type Operation,
  type Transport,
  validateTargetsAgainstAccepts,
} from "@/lib/gatewayCapabilityCatalog"

// #2007 — Gateway Profile v2 draft editor. Loads a profile's working_copy,
// renders it as a form (name, model_alias, accepts, timeouts, ordered
// target list with add/remove/reorder), and saves back via
// PUT /working_copy. Matches the styling of the sibling GatewayProfileSettings
// (v1) component so both settings pages feel like one product.

const KNOWN_LITELLM_PROVIDERS = ["anthropic", "openai"] as const

// Pinned model catalog per provider. Real IDs the runtime accepts today
// so the editor is a dropdown, not free text. Extend here when the
// upstream catalog moves — the capability catalog on the server is the
// authoritative filter, but this list makes the picker useful.
const MODELS_BY_PROVIDER: Record<string, Array<{ id: string; label: string }>> = {
  anthropic: [
    { id: "claude-opus-4-7",              label: "Claude Opus 4.7 (most capable)" },
    { id: "claude-sonnet-4-6",            label: "Claude Sonnet 4.6 (balanced)" },
    { id: "claude-haiku-4-5-20251001",    label: "Claude Haiku 4.5 (fast + cheap)" },
    { id: "claude-sonnet-4-5-20250529",   label: "Claude Sonnet 4.5 (previous)" },
  ],
  openai: [
    { id: "gpt-4o",       label: "GPT-4o (flagship)" },
    { id: "gpt-4o-mini",  label: "GPT-4o mini (cheap)" },
    { id: "o1",           label: "o1 (reasoning)" },
    { id: "o1-mini",      label: "o1 mini (reasoning, cheaper)" },
  ],
}

// Auto-derive `accepts` from the target providers. Every Anthropic
// target contributes anthropic_messages; every OpenAI target
// contributes openai_chat_completions and openai_responses. This
// replaces the previous checkbox UI — those labels
// (anthropic_messages, openai_chat_completions, ...) were technical
// noise for admins who just want to pick "route via Claude".
function deriveAccepts(targets: DraftTarget[]): Operation[] {
  const seen = new Set<Operation>()
  for (const t of targets) {
    if (t.transport !== "litellm_sdk") continue
    if (t.provider === "anthropic") {
      seen.add("anthropic_messages")
      // count_tokens is safe to always include when Anthropic is a target
      seen.add("anthropic_count_tokens")
    }
    if (t.provider === "openai") {
      seen.add("openai_chat_completions")
      seen.add("openai_responses")
    }
  }
  return [...seen]
}

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
  // accepts is derived from target providers at save time — no UI to
  // maintain. See `deriveAccepts` above.
  return {
    name: s.name, model_alias: s.model_alias,
    accepts: deriveAccepts(s.targets),
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
        <FieldLabel label="Name" hint="Display name for this profile.">
          <input value={state.name} disabled={!isAdmin}
            placeholder="e.g. coding-prod"
            onChange={e => patch({ name: e.target.value })} style={inputStyle} />
        </FieldLabel>
        <FieldLabel label="Alias" hint="What clients send as `model:` in their request.">
          <input value={state.model_alias} disabled={!isAdmin}
            onChange={e => patch({ model_alias: e.target.value })}
            placeholder="e.g. coding" style={inputStyle} />
        </FieldLabel>
        <FieldLabel label="Timeout (s)" hint="End-to-end deadline across every fallback attempt.">
          <input type="number" min={1} value={state.timeout_seconds} disabled={!isAdmin}
            onChange={e => patch({ timeout_seconds: Math.max(1, Number(e.target.value) || 1) })}
            style={inputStyle} />
        </FieldLabel>
        <FieldLabel label="Max attempts" hint="Cap on target retries (primary + fallbacks).">
          <input type="number" min={1} max={10} value={state.max_attempts} disabled={!isAdmin}
            onChange={e => patch({ max_attempts: Math.max(1, Number(e.target.value) || 1) })}
            style={inputStyle} />
        </FieldLabel>
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
    <div className="card" style={{ padding: 12, display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr auto", gap: 10, alignItems: "end" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "center" }}>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={onMoveUp} disabled={!isAdmin || isFirst}
          style={{ height: 24, width: 24, opacity: isFirst ? 0.35 : 1 }} title="Move up">↑</button>
        <span style={{ fontSize: 11, color: "var(--text-3)" }}>#{index + 1}</span>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={onMoveDown} disabled={!isAdmin || isLast}
          style={{ height: 24, width: 24, opacity: isLast ? 0.35 : 1 }} title="Move down">↓</button>
      </div>

      <FieldLabel label="Role" hint="First target = primary; the rest are fallbacks in order.">
        <input value={target.id} disabled={!isAdmin}
          placeholder={index === 0 ? "primary" : "fallback"}
          onChange={e => onChange({ id: e.target.value })} style={inputStyle} />
      </FieldLabel>

      <FieldLabel label="Provider" hint="Upstream provider — routes through the LiteLLM SDK.">
        <select value={target.provider} disabled={!isAdmin}
          onChange={e => {
            const provider = e.target.value
            // If the current model doesn't belong to the new provider,
            // reset to the provider's first model — no in-between state
            // where "openai/claude-sonnet-4-6" briefly exists.
            const models = MODELS_BY_PROVIDER[provider] ?? []
            const modelStillValid = models.some(m => m.id === target.model)
            onChange({
              provider,
              model: modelStillValid ? target.model : (models[0]?.id ?? ""),
            })
          }} style={inputStyle}>
          {KNOWN_LITELLM_PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </FieldLabel>

      <FieldLabel label="Model" hint="Real upstream model ID the request goes to.">
        <select value={target.model} disabled={!isAdmin}
          onChange={e => onChange({ model: e.target.value })} style={inputStyle}>
          {(MODELS_BY_PROVIDER[target.provider] ?? []).map(m => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      </FieldLabel>

      {isAdmin ? (
        <button onClick={onRemove} className="btn btn-ghost btn-sm btn-icon"
          style={{ color: "var(--err)", borderColor: "var(--err-bd)" }} title="Remove target">×</button>
      ) : <div />}

      <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <FieldLabel label="Credential vault" hint="Which environment holds the upstream API key.">
          <select value={target.credential_env_id} disabled={!isAdmin}
            onChange={e => {
              const envId = e.target.value
              onChange({ credential_env_id: envId, credential_handle: "" })
              onLoadCredsFor(envId)
            }} style={inputStyle}>
            <option value="">— pick vault —</option>
            {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </FieldLabel>
        <FieldLabel label="Credential handle" hint="The named credential inside that vault (e.g. `anthropic`).">
          {creds.length > 0 ? (
            <select value={target.credential_handle} disabled={!isAdmin}
              onChange={e => onChange({ credential_handle: e.target.value })} style={inputStyle}>
              <option value="">— pick handle —</option>
              {creds.map(c => <option key={c.handle} value={c.handle}>{c.handle}</option>)}
            </select>
          ) : (
            <input value={target.credential_handle} disabled={!isAdmin}
              placeholder={target.credential_env_id ? "no credentials in this vault yet" : "pick a vault first"}
              onChange={e => onChange({ credential_handle: e.target.value })} style={inputStyle} />
          )}
        </FieldLabel>
      </div>
    </div>
  )
}


function FieldLabel({
  label, hint, children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {label}
        {hint ? <HintIcon text={hint} /> : null}
      </span>
      {children}
    </label>
  )
}


function HintIcon({ text }: { text: string }) {
  // Native `title` attribute has a ~700ms browser delay and doesn't
  // work on touch; custom hover popover renders instantly and is
  // reliable across desktops.
  const [show, setShow] = useState(false)
  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      <span
        role="img"
        aria-label={text}
        tabIndex={0}
        style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 14, height: 14, borderRadius: "50%",
          border: "1px solid var(--border)",
          fontSize: 10, fontWeight: 600, color: "var(--text-3)",
          cursor: "help", userSelect: "none",
        }}
      >i</span>
      {show ? (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: "50%",
            transform: "translateX(-50%)",
            padding: "6px 8px",
            background: "var(--text)",
            color: "var(--surface)",
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 400,
            lineHeight: 1.4,
            maxWidth: 240,
            width: "max-content",
            whiteSpace: "normal",
            textAlign: "left",
            zIndex: 1000,
            pointerEvents: "none",
            boxShadow: "0 4px 12px rgba(0,0,0,.15)",
          }}
        >
          {text}
        </span>
      ) : null}
    </span>
  )
}
