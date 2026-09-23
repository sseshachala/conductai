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

// LLM Model Primitives is the single source of truth for the model
// catalog. No hardcoded fallback — if the fetch fails the editor
// surfaces the error and the dropdown stays empty until the operator
// fixes primitives. Preserves the "one source of truth" invariant even
// when the API is down (better a visible empty state than a stale
// hardcoded list that lies about which models the workspace approved).

// Turn a workspace tier_map slice ({ cheap: "id", balanced: "id", smart: "id" })
// into the dropdown option shape. Preserves tier order (cheap → balanced
// → smart) so the UI is stable across renders. Empty slice → [] so the
// caller can fall back to the hardcoded ``MODELS_BY_PROVIDER`` list.
const TIER_ORDER = ["cheap", "balanced", "smart"] as const
function modelsFromTierMap(slice: Record<string, string> | undefined): Array<{ id: string; label: string }> {
  if (!slice) return []
  const seen = new Set<string>()
  const options: Array<{ id: string; label: string }> = []
  for (const tier of TIER_ORDER) {
    const id = slice[tier]
    if (id && !seen.has(id)) {
      options.push({ id, label: `${id} (${tier})` })
      seen.add(id)
    }
  }
  // Any custom tier keys the admin added beyond the three standard
  // ones — surface them too so the dropdown reflects the primitives
  // state exactly. Alpha-sorted for determinism.
  for (const tier of Object.keys(slice).sort()) {
    if ((TIER_ORDER as readonly string[]).includes(tier)) continue
    const id = slice[tier]
    if (id && !seen.has(id)) {
      options.push({ id, label: `${id} (${tier})` })
      seen.add(id)
    }
  }
  return options
}

// Per-integration operations for http_passthrough targets. Mirrors
// the backend's ``_INTEGRATION_ENDPOINTS`` matrix in
// ``app/runtime/http_passthrough_transport.py`` — keep in sync (there
// is no build-time enforcement; the server is authoritative on
// publish, but a mismatch here silently drops accepts and produces
// an empty operation list that fails validation server-side).
const PASSTHROUGH_INTEGRATION_OPERATIONS: Record<string, Operation[]> = {
  openrouter:         ["openai_chat_completions"],
  portkey:            ["openai_chat_completions"],
  helicone_openai:    ["openai_chat_completions"],
  helicone_anthropic: ["anthropic_messages"],
  azure_openai:       ["openai_chat_completions"],
  // PR 7 — Custom transport can serve every launch operation; the
  // capability catalog narrows the per-target set by
  // ``provider_options.protocol`` at publish time.
  custom: [
    "openai_chat_completions",
    "openai_responses",
    "anthropic_messages",
    "anthropic_count_tokens",
  ],
}

// Expected vault key name per passthrough integration. Mirrors
// ``INTEGRATION_KEY_ALIASES`` in
// ``apps/api/app/modules/guard/gateway_credentials.py`` — first tuple
// entry is the canonical name shown to users.
const INTEGRATION_KEY_HINTS: Record<string, string> = {
  openrouter:         "OPENROUTER_API_KEY",
  portkey:            "PORTKEY_API_KEY",
  helicone_anthropic: "HELICONE_API_KEY",
  helicone_openai:    "HELICONE_API_KEY",
  azure_openai:       "AZUREAI_API_KEY",
  // Custom has no preset. The transport falls back to the generic
  // ladder in ``resolve_gateway_key``: LLM_UPSTREAM_API_KEY → api_key
  // → CUSTOM_API_KEY. First name is the recommended one because it's
  // integration-agnostic (users often reuse the same handle for
  // multiple proxy targets).
  custom:             "LLM_UPSTREAM_API_KEY",
}

// Compute the operations ONE target can serve. Anthropic native /
// litellm → anthropic_messages + count_tokens. OpenAI native / litellm
// → chat_completions + responses. Passthrough looks up the per-
// integration matrix (OpenRouter: chat_completions only).
function _capabilitiesOf(t: DraftTarget): Operation[] {
  if (t.transport === "native_http" || t.transport === "litellm_sdk") {
    if (t.provider === "anthropic") {
      return ["anthropic_messages", "anthropic_count_tokens"]
    }
    if (t.provider === "openai") {
      return ["openai_chat_completions", "openai_responses"]
    }
    return []
  }
  if (t.transport === "http_passthrough") {
    return PASSTHROUGH_INTEGRATION_OPERATIONS[t.integration] ?? []
  }
  return []
}

// Auto-derive `accepts` from the target list using the INTERSECTION of
// each target's certified operations.
//
// Why intersection (Z3 fix): the backend requires every target to
// serve every accepted operation — see
// ``validate_targets_against_accepts`` in
// ``apps/api/app/modules/guard/capability_catalog.py``. The old code
// used the union, which meant a mixed fallback profile (e.g. native
// OpenAI primary + OpenRouter fallback) advertised
// ``openai_responses`` — OpenRouter can't serve that operation, so
// publish rejected the profile.
//
// With intersection, the profile advertises only what BOTH targets
// can serve. In the OpenAI + OpenRouter example that's just
// ``openai_chat_completions``, which is what OpenRouter supports and
// what the client actually uses. If two targets have no operations in
// common (e.g. Anthropic + OpenAI) the derived accepts is empty and
// publish rejects — which is correct: those targets can't share a
// profile without a translation layer.
function deriveAccepts(targets: DraftTarget[]): Operation[] {
  if (targets.length === 0) return []

  // Start with the first target's capabilities, then narrow to the
  // shared subset with each subsequent target.
  const first = new Set<Operation>(_capabilitiesOf(targets[0]))
  for (let i = 1; i < targets.length; i += 1) {
    const cap = new Set<Operation>(_capabilitiesOf(targets[i]))
    for (const op of first) {
      if (!cap.has(op)) first.delete(op)
    }
  }
  return [...first]
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
  /**
   * Opaque provider-specific tuning bag (temperature caps, timeouts,
   * region hints, etc.). The editor doesn't render fields for this —
   * admins set it via ``conduct import --gateway-config`` or direct
   * API PUT — but the editor MUST preserve it round-trip so the Save
   * button doesn't silently strip it. R2 fix.
   */
  provider_options?: Record<string, unknown>
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
    // Default new targets to native HTTP — vendor's protocol end-to-end,
    // no SDK translation. Admins can switch to litellm_sdk on the row
    // when they explicitly want translation.
    transport: "native_http",
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
    // Preserve provider_options as-is — the editor has no UI to
    // author it, but round-tripping strips it means importing a
    // tuned profile silently drops the tuning. R2 fix.
    const providerOptions =
      t.provider_options && typeof t.provider_options === "object" && !Array.isArray(t.provider_options)
        ? (t.provider_options as Record<string, unknown>)
        : undefined
    return {
      id: String(t.id ?? `target-${i + 1}`),
      transport: (t.transport as Transport) ?? "native_http",
      provider: String(t.provider ?? "anthropic"),
      integration: String(t.integration ?? "portkey"),
      model: String(t.model ?? ""),
      credential_env_id: cred.env,
      credential_handle: cred.handle,
      endpoint: String(t.endpoint ?? ""),
      provider_options: providerOptions,
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
    // Only surface provider_options in the emitted target when the
    // source actually had it — an empty ``{}`` isn't semantically
    // equivalent to "absent" for the schema, so we skip when unset.
    // R2 fix.
    const opts = t.provider_options
    const hasOpts = opts && typeof opts === "object" && Object.keys(opts).length > 0
    const commonWithOpts = hasOpts ? { provider_options: opts } : {}
    if (t.transport === "native_http") {
      return {
        id: t.id, transport: "native_http", provider: t.provider,
        model: t.model, credential_ref: ref, ...commonWithOpts,
      }
    }
    if (t.transport === "litellm_sdk") {
      return {
        id: t.id, transport: "litellm_sdk", provider: t.provider,
        model: t.model, credential_ref: ref, ...commonWithOpts,
      }
    }
    return {
      id: t.id, transport: "http_passthrough", integration: t.integration,
      model: t.model, credential_ref: ref, endpoint: t.endpoint || null,
      ...commonWithOpts,
    }
  })
  // R2 fix: use ``s.accepts`` verbatim rather than re-deriving from
  // target providers. Imported profiles with explicit accepts (e.g.
  // ``[anthropic_messages]`` even though targets could serve
  // ``anthropic_count_tokens`` too) must round-trip through Save
  // without silently widening or narrowing. When the admin edits a
  // target's transport/provider/integration, ``patchTarget`` below
  // re-derives accepts explicitly — those are the only mutations
  // that should invalidate imported accepts.
  return {
    name: s.name, model_alias: s.model_alias,
    accepts: s.accepts,
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
  // Workspace-scoped LLM Model Primitives — the SINGLE source of truth
  // for which model IDs a workspace has decided to use per (provider,
  // tier). Fetched once on mount. Error state is loud (banner) so the
  // operator can go fix primitives instead of seeing a stale hardcoded
  // list masquerading as truth.
  const [tierMap, setTierMap] = useState<Record<string, Record<string, string>>>({})
  const [primitivesLoading, setPrimitivesLoading] = useState(true)
  const [primitivesError, setPrimitivesError] = useState("")
  const providerKeys = useMemo(() => Object.keys(tierMap).sort(), [tierMap])

  useEffect(() => {
    setState(stateFromProfile(profile))
    setMsg(""); setErr("")
  }, [profile])

  useEffect(() => {
    if (!workspaceId) return
    setPrimitivesLoading(true)
    setPrimitivesError("")
    ;(async () => {
      try {
        const API = process.env.NEXT_PUBLIC_API_BASE ?? ""
        const res = await authFetch(`${API}/workspaces/${workspaceId}/llm-primitives`)
        if (!res.ok) {
          throw new Error(`LLM Model Primitives fetch failed (${res.status})`)
        }
        const data = await res.json() as { tier_map?: Record<string, Record<string, string>> }
        setTierMap(data.tier_map ?? {})
      } catch (e) {
        setPrimitivesError(e instanceof Error ? e.message : "LLM Model Primitives fetch failed")
        setTierMap({})
      } finally {
        setPrimitivesLoading(false)
      }
    })()
  }, [authFetch, workspaceId])

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
    targets: state.targets.map(t => {
      if (t.transport === "native_http") {
        return { id: t.id, transport: "native_http" as const, provider: t.provider }
      }
      if (t.transport === "litellm_sdk") {
        return { id: t.id, transport: "litellm_sdk" as const, provider: t.provider }
      }
      return { id: t.id, transport: "http_passthrough" as const, integration: t.integration as any }
    }),
  }), [state])

  // Client-side Save gate (self-review layer 2): server rejects a save
  // with empty ``credential_ref`` fields as a 14-error blob (three
  // discriminated-union variants × N missing fields). Catch it here so
  // Save is blocked with a readable inline hint instead. Mirrors the
  // server's field-level requirements: id, provider, model, and a full
  // vault:// reference are required per target.
  const targetIssues = useMemo(() => {
    return state.targets.map((t, i) => {
      const issues: string[] = []
      if (!t.id.trim()) issues.push("id is required")
      if (!t.provider.trim() && t.transport !== "http_passthrough") {
        issues.push("provider is required")
      }
      if (!t.model.trim()) issues.push("model is required")
      if (!t.credential_env_id) issues.push("pick a credential vault")
      if (!t.credential_handle) issues.push("pick a credential handle")
      return { index: i, targetId: t.id || `#${i + 1}`, issues }
    }).filter(x => x.issues.length > 0)
  }, [state])

  const canSave = isAdmin && targetIssues.length === 0

  async function save() {
    if (!isAdmin) return
    if (targetIssues.length > 0) {
      // Belt-and-braces — the button is disabled when this holds, but
      // if a keyboard-driven save slips past the disabled state, catch
      // it here and surface the same message the banner shows.
      setErr(
        `Fix ${targetIssues.length} target issue(s) before saving — ` +
        targetIssues.map(t => `${t.targetId}: ${t.issues[0]}`).join("; "),
      )
      return
    }
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
    setState(s => {
      const nextTargets = s.targets.map((t, j) => j === i ? { ...t, ...u } : t)
      // R2: only re-derive accepts when a change actually affects
      // the certified-capabilities calculation. Editing ``model`` or
      // ``credential_handle`` must NOT clobber imported accepts.
      const affectsAccepts =
        u.transport !== undefined || u.provider !== undefined || u.integration !== undefined
      const nextAccepts = affectsAccepts ? deriveAccepts(nextTargets) : s.accepts
      return { ...s, targets: nextTargets, accepts: nextAccepts }
    })
    setMsg("")
  }
  function removeTarget(i: number) {
    setState(s => {
      const nextTargets = s.targets.filter((_, j) => j !== i)
      return { ...s, targets: nextTargets, accepts: deriveAccepts(nextTargets) }
    })
    setMsg("")
  }
  function addTarget() {
    setState(s => {
      const nextTargets = [...s.targets, emptyTarget(s.targets)]
      return { ...s, targets: nextTargets, accepts: deriveAccepts(nextTargets) }
    })
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
              tierMap={tierMap}
              onChange={u => patchTarget(i, u)}
              onRemove={() => removeTarget(i)}
              onMoveUp={() => move(i, -1)} onMoveDown={() => move(i, 1)}
              isFirst={i === 0} isLast={i === state.targets.length - 1} />
          ))}
        </div>
      </div>

      {primitivesError && (
        <div className="sbadge err" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>LLM Model Primitives unreachable</strong>
          <div style={{ fontSize: 12, fontWeight: 400, marginTop: 4 }}>
            {primitivesError}. Provider + Model dropdowns are empty until
            this loads. Fix under Settings → LLM Model Primitives, then
            reload this page.
          </div>
        </div>
      )}

      {!primitivesLoading && !primitivesError && providerKeys.length === 0 && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>No providers configured</strong>
          <div style={{ fontSize: 12, fontWeight: 400, marginTop: 4 }}>
            The workspace's LLM Model Primitives has no providers. Add
            at least one under Settings → LLM Model Primitives before
            saving this profile.
          </div>
        </div>
      )}

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

      {/* Client-side Save gate (self-review layer 2). Blocks Save with
          an inline banner so the admin never hits the server-side
          discriminated-union noise blob. */}
      {targetIssues.length > 0 && isAdmin && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>{targetIssues.length} target(s) need attention before Save</strong>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            {targetIssues.map(t => (
              <li key={t.index} style={{ fontSize: 12, fontWeight: 400 }}>
                <span className="mono">#{t.index + 1} {t.targetId}</span>:{" "}
                {t.issues.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}

      {err && <p style={{ margin: 0, color: "var(--err)", fontSize: 12 }}>{err}</p>}
      {msg && <p style={{ margin: 0, color: "var(--ok)", fontSize: 12 }}>{msg}</p>}

      {isAdmin && (
        <div>
          <button
            onClick={save}
            disabled={saving || !canSave}
            className="btn btn-primary btn-sm"
            title={
              !canSave && targetIssues.length > 0
                ? `Fix ${targetIssues.length} target issue(s) before saving`
                : undefined
            }
          >
            {saving ? "Saving…" : "Save working copy"}
          </button>
        </div>
      )}
    </div>
  )
}


function TargetRow({
  index, target, envs, isAdmin, credentialsByEnv, onLoadCredsFor,
  tierMap, onChange, onRemove, onMoveUp, onMoveDown, isFirst, isLast,
}: {
  index: number
  target: DraftTarget
  envs: EnvironmentRow[]
  isAdmin: boolean
  credentialsByEnv: Record<string, CredentialRow[]>
  onLoadCredsFor: (envId: string) => void
  tierMap: Record<string, Record<string, string>>
  onChange: (u: Partial<DraftTarget>) => void
  onRemove: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  isFirst: boolean
  isLast: boolean
}) {
  const creds = target.credential_env_id ? credentialsByEnv[target.credential_env_id] ?? [] : []
  // Prefer the workspace's LLM Model Primitives tier_map for this
  // provider; fall back to the hardcoded catalog if the workspace
  // hasn't customized (or if the primitives fetch failed).
  const modelsForProvider = (provider: string): Array<{ id: string; label: string }> => {
    // No fallback — primitives is authoritative. Empty list surfaces
    // the empty-state hint that points at Settings.
    return modelsFromTierMap(tierMap[provider])
  }
  const modelsForCurrent = modelsForProvider(target.provider)
  // Provider list = keys the workspace declared in primitives.
  // Sorted for stable render. Empty state handled in the render below.
  const providers = Object.keys(tierMap).sort()
  return (
    <div className="card" style={{ padding: 12, display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr 1fr auto", gap: 10, alignItems: "end" }}>
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

      <FieldLabel
        label="Transport"
        hint="Native HTTPS = direct to vendor (Anthropic / OpenAI, preferred). LiteLLM SDK = LiteLLM translates operations across providers. HTTPS Passthrough = external gateway (OpenRouter today; Portkey / Helicone / Azure / Custom ship in follow-ups)."
      >
        <select value={target.transport} disabled={!isAdmin}
          onChange={e => onChange({ transport: e.target.value as Transport })}
          style={inputStyle}>
          <option value="native_http">Native HTTPS (recommended)</option>
          <option value="litellm_sdk">LiteLLM SDK</option>
          <option value="http_passthrough">HTTPS Passthrough</option>
        </select>
      </FieldLabel>

      {target.transport === "http_passthrough" ? (
        <FieldLabel
          label="Integration"
          hint="External gateway routing traffic on our behalf. All six integrations certified: OpenRouter, Portkey, Helicone (OpenAI + Anthropic), Azure OpenAI, and Custom. Portkey needs virtual_key/provider/config. Helicone vault holds two keys (HELICONE_API_KEY + vendor). Azure needs Resource endpoint + deployment name + api-version. Custom is a template — you pick protocol + endpoint + auth shape."
        >
          <select value={target.integration} disabled={!isAdmin}
            onChange={e => onChange({ integration: e.target.value })}
            style={inputStyle}>
            <option value="openrouter">openrouter (certified)</option>
            <option value="portkey">portkey (certified)</option>
            <option value="helicone_anthropic">helicone_anthropic (certified)</option>
            <option value="helicone_openai">helicone_openai (certified)</option>
            <option value="azure_openai">azure_openai (certified)</option>
            <option value="custom">custom (certified)</option>
          </select>
        </FieldLabel>
      ) : (
        <FieldLabel label="Provider" hint="Upstream provider — sourced from workspace LLM Model Primitives. Add providers under Settings → LLM Model Primitives. Only anthropic + openai + LiteLLM-compat (perplexity/together) are catalog-certified for native_http / litellm_sdk today; others surface a publish-time capability error.">
          <select value={target.provider} disabled={!isAdmin || providers.length === 0}
            onChange={e => {
              const provider = e.target.value
              const models = modelsForProvider(provider)
              const modelStillValid = models.some(m => m.id === target.model)
              onChange({
                provider,
                model: modelStillValid ? target.model : (models[0]?.id ?? ""),
              })
            }} style={inputStyle}>
            {providers.length === 0 ? (
              <option value="">— no providers in primitives — configure Settings → LLM Model Primitives —</option>
            ) : null}
            {providers.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </FieldLabel>
      )}

      <FieldLabel
        label={target.transport === "http_passthrough" && target.integration === "azure_openai" ? "Deployment name" : "Model"}
        hint={
          target.transport === "http_passthrough"
            ? (target.integration === "azure_openai"
                ? "Azure OpenAI deployment name — the URL becomes /openai/deployments/{deployment}/... Not a model id."
                : target.integration === "custom"
                    ? "Model id the request body carries — whatever your proxy expects (e.g. gpt-4o or claude-sonnet-4-6)."
                    : "Upstream model id in the integration's format (OpenRouter: `anthropic/claude-3.5-sonnet`, Portkey: `gpt-4o` or vendor-prefixed via virtual key).")
            : "Real upstream model ID the request goes to."
        }
      >
        {target.transport === "http_passthrough" ? (
          <input value={target.model} disabled={!isAdmin}
            placeholder={
              target.integration === "azure_openai" ? "gpt-4o-prod-deploy"
              : target.integration === "portkey" ? "gpt-4o"
              : target.integration === "custom" ? "gpt-4o"
              : "anthropic/claude-3.5-sonnet"
            }
            onChange={e => onChange({ model: e.target.value })}
            style={inputStyle} />
        ) : (
          <select value={target.model} disabled={!isAdmin}
            onChange={e => onChange({ model: e.target.value })} style={inputStyle}>
            {modelsForCurrent.length === 0 ? (
              <option value="">— no models for {target.provider} — configure Settings → LLM Model Primitives —</option>
            ) : null}
            {modelsForCurrent.map(m => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        )}
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
          {target.transport === "http_passthrough" && INTEGRATION_KEY_HINTS[target.integration] ? (
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>
              Expected key in vault: <code>{INTEGRATION_KEY_HINTS[target.integration]}</code>
              {target.integration === "custom" ? (
                <> (or <code>api_key</code> / <code>CUSTOM_API_KEY</code>)</>
              ) : null}
            </span>
          ) : null}
        </FieldLabel>
      </div>

      {/* PR 4 — Portkey needs an upstream selector alongside the
          gateway key. Any one of virtual_key / provider / config
          satisfies the required-selector check server-side. */}
      {target.transport === "http_passthrough" && target.integration === "portkey" ? (
        <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
          <FieldLabel label="Virtual key" hint="Portkey virtual key ID (recommended — carries provider config). Sent as x-portkey-virtual-key.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.virtual_key ?? "")}
              disabled={!isAdmin}
              placeholder="vk-openai-prod"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  virtual_key: e.target.value || undefined,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
          <FieldLabel label="Provider" hint="Portkey provider slug (openai / anthropic / etc.). Sent as x-portkey-provider.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.provider ?? "")}
              disabled={!isAdmin}
              placeholder="openai"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  provider: e.target.value || undefined,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
          <FieldLabel label="Config ID" hint="Portkey saved config ID. Sent as x-portkey-config.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.config ?? "")}
              disabled={!isAdmin}
              placeholder="cfg_abc"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  config: e.target.value || undefined,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
        </div>
      ) : null}

      {/* PR 6 — Azure OpenAI needs per-tenant endpoint + api-version.
          Endpoint reuses the existing `endpoint` field; api-version
          lives in `provider_options` and is opaque to the schema. */}
      {target.transport === "http_passthrough" && target.integration === "azure_openai" ? (
        <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <FieldLabel label="Resource endpoint" hint="Your Azure OpenAI resource URL, e.g. https://my-resource.openai.azure.com (no trailing path).">
            <input value={target.endpoint} disabled={!isAdmin}
              placeholder="https://my-resource.openai.azure.com"
              onChange={e => onChange({ endpoint: e.target.value })}
              style={inputStyle} />
          </FieldLabel>
          <FieldLabel label="api-version" hint="Azure OpenAI API version, e.g. 2024-06-01. Added as a URL query parameter.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.api_version ?? "")}
              disabled={!isAdmin}
              placeholder="2024-06-01"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  api_version: e.target.value,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
        </div>
      ) : null}

      {/* PR 7 — Custom integration exposes protocol + auth-header shape
          + extra headers JSON on the target itself. Endpoint reuses
          the existing `endpoint` field. All live in provider_options. */}
      {target.transport === "http_passthrough" && target.integration === "custom" ? (
        <>
          <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 10 }}>
            <FieldLabel label="Endpoint URL" hint="Full base URL up to /v1 (e.g. https://my-llm-proxy.example.com/v1). Suffixes like /chat/completions or /messages are added per operation.">
              <input value={target.endpoint} disabled={!isAdmin}
                placeholder="https://my-llm-proxy.example.com/v1"
                onChange={e => onChange({ endpoint: e.target.value })}
                style={inputStyle} />
            </FieldLabel>
            <FieldLabel label="Protocol" hint="Which wire shape your upstream speaks. Determines which operations publish will certify (openai_* vs anthropic_*).">
              <select
                value={String((target.provider_options as Record<string, unknown> | undefined)?.protocol ?? "")}
                disabled={!isAdmin}
                onChange={e => onChange({
                  provider_options: {
                    ...(target.provider_options ?? {}),
                    protocol: e.target.value || undefined,
                  },
                })}
                style={inputStyle}>
                <option value="">— pick protocol —</option>
                <option value="openai">OpenAI-shape</option>
                <option value="anthropic">Anthropic-shape</option>
              </select>
            </FieldLabel>
            <FieldLabel label="Bearer prefix" hint="Prepend `Bearer ` to the key value. Turn off if your proxy expects the raw key.">
              <select
                value={((target.provider_options as Record<string, unknown> | undefined)?.bearer_prefix ?? true) ? "yes" : "no"}
                disabled={!isAdmin}
                onChange={e => onChange({
                  provider_options: {
                    ...(target.provider_options ?? {}),
                    bearer_prefix: e.target.value === "yes",
                  },
                })}
                style={inputStyle}>
                <option value="yes">Bearer</option>
                <option value="no">Raw</option>
              </select>
            </FieldLabel>
          </div>
          <div style={{ gridColumn: "2 / -1", display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
            <FieldLabel label="Auth header" hint="Name of the header carrying the API key (default: authorization). Reserved names (cookie / host / content-* / *-api-key etc.) are refused.">
              <input
                value={String((target.provider_options as Record<string, unknown> | undefined)?.auth_header ?? "")}
                disabled={!isAdmin}
                placeholder="authorization"
                onChange={e => onChange({
                  provider_options: {
                    ...(target.provider_options ?? {}),
                    auth_header: e.target.value,
                  },
                })}
                style={inputStyle} />
            </FieldLabel>
          </div>
          <div style={{ gridColumn: "2 / -1" }}>
            <CustomExtraHeadersField
              value={target.provider_options as Record<string, unknown> | undefined}
              disabled={!isAdmin}
              onChange={next => onChange({ provider_options: next })}
            />
          </div>
        </>
      ) : null}
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


// PR 7 review finding 7 — the previous inline textarea bound its
// ``value`` to the last-valid parsed ``extra_headers`` object. Typing
// the first ``{`` produced invalid JSON, wrote to ``extra_headers_raw``,
// and the next render resets the visible text to whatever was last
// parseable — so users literally couldn't type. This component keeps
// a local raw string state, seeded from either ``extra_headers_raw``
// or a pretty-printed ``extra_headers``, parses on every keystroke,
// and surfaces the error inline without wiping input.
function CustomExtraHeadersField({
  value, disabled, onChange,
}: {
  value: Record<string, unknown> | undefined
  disabled: boolean
  onChange: (next: Record<string, unknown>) => void
}) {
  const seed = (() => {
    if (value && typeof value.extra_headers_raw === "string") return value.extra_headers_raw
    const eh = value?.extra_headers
    return eh && typeof eh === "object" ? JSON.stringify(eh, null, 2) : ""
  })()
  const [raw, setRaw] = useState(seed)
  const [error, setError] = useState<string | null>(null)

  return (
    <FieldLabel
      label="Extra headers (JSON)"
      hint='Optional static headers to send on every request. Must parse as a flat JSON object of strings, e.g. {"X-Team":"platform"}. Reserved names (authorization / cookie / content-* / any *api-key*) are refused.'
    >
      <textarea
        value={raw}
        disabled={disabled}
        placeholder='{"X-Team": "platform"}'
        onChange={e => {
          const text = e.target.value
          setRaw(text)
          const trimmed = text.trim()
          const next: Record<string, unknown> = { ...(value ?? {}) }
          if (!trimmed) {
            delete next.extra_headers
            delete next.extra_headers_raw
            setError(null)
            onChange(next)
            return
          }
          try {
            const parsed = JSON.parse(trimmed)
            if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
              throw new Error("must be a JSON object")
            }
            for (const [k, v] of Object.entries(parsed)) {
              if (typeof v !== "string") {
                throw new Error(`value for "${k}" must be a string`)
              }
            }
            next.extra_headers = parsed as Record<string, string>
            delete next.extra_headers_raw
            setError(null)
          } catch (err) {
            // Keep the raw text alongside a validation error so the
            // admin can fix without losing keystrokes. Publish still
            // sees ``extra_headers_raw`` — the server refuses that
            // key at the schema level, so a broken draft can't ship.
            delete next.extra_headers
            next.extra_headers_raw = text
            setError((err as Error).message || "invalid JSON")
          }
          onChange(next)
        }}
        style={{
          padding: 6,
          borderRadius: 4,
          border: `1px solid var(${error ? "--err-bd" : "--border"})`,
          background: "var(--surface)",
          color: "var(--text)",
          minHeight: 72,
          fontFamily: "monospace",
          fontSize: 11,
        }} />
      {error ? (
        <span style={{ fontSize: 11, color: "var(--err)" }}>
          {error} — publish will reject until this parses.
        </span>
      ) : null}
    </FieldLabel>
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
