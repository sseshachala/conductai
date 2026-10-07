import type { GatewayProfileV2Out, GatewayProfileV2Target } from "@/lib/api/guard"
import { type Operation, type Transport, type Integration, type TargetShape, certifiedOperations } from "@/lib/gatewayCapabilityCatalog"

// Turn a workspace tier_map slice ({ cheap: "id", balanced: "id", smart: "id" })
// into the dropdown option shape. Preserves tier order (cheap → balanced
// → smart) so the UI is stable across renders. Empty slice → [] so the
// caller can fall back to the hardcoded ``MODELS_BY_PROVIDER`` list.
export const TIER_ORDER = ["cheap", "balanced", "smart"] as const
export function modelsFromTierMap(slice: Record<string, string> | undefined): Array<{ id: string; label: string }> {
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

// Expected vault key name per passthrough integration. Mirrors
// ``INTEGRATION_KEY_ALIASES`` in
// ``apps/api/app/modules/guard/gateway_credentials.py`` — first tuple
// entry is the canonical name shown to users.
export const INTEGRATION_KEY_HINTS: Record<string, string> = {
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
export function _capabilitiesOf(t: DraftTarget): Operation[] {
  return [...certifiedOperations(catalogTarget(t))]
}

export function catalogTarget(t: DraftTarget): TargetShape {
  return t.transport === "http_passthrough"
    ? { transport: t.transport, integration: t.integration as Integration, provider_options: t.provider_options }
    : { transport: t.transport, provider: t.provider }
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
export function deriveAccepts(targets: DraftTarget[]): Operation[] {
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

export type EnvironmentRow = { id: string; name: string }
export type CredentialRow = { handle: string }

export interface DraftTarget {
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

export interface EditorState {
  name: string
  model_alias: string
  accepts: Operation[]
  timeout_seconds: number
  max_attempts: number
  targets: DraftTarget[]
}

export function nextTargetId(existing: DraftTarget[]): string {
  let i = 1
  const ids = new Set(existing.map(t => t.id))
  while (ids.has(`target-${i}`)) i += 1
  return `target-${i}`
}

export function emptyTarget(existing: DraftTarget[]): DraftTarget {
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

export function parseVaultRef(ref: string | undefined): { env: string; handle: string } {
  const match = String(ref ?? "").match(/^vault:\/\/([0-9a-f-]{36})\/([^/]+)$/i)
  return match ? { env: match[1], handle: match[2] } : { env: "", handle: "" }
}

export function stateFromProfile(profile: GatewayProfileV2Out): EditorState {
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

export function stateToWorkingCopy(s: EditorState): Record<string, unknown> {
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
    name: s.name.trim(), model_alias: s.model_alias.trim(),
    accepts: s.accepts,
    timeout_seconds: s.timeout_seconds, max_attempts: s.max_attempts, targets,
  }
}

export const inputStyle: React.CSSProperties = {
  width: "100%", padding: "9px 11px",
  border: "1px solid var(--border)", borderRadius: 7,
  background: "var(--surface)", color: "var(--text)", fontSize: 13,
}
