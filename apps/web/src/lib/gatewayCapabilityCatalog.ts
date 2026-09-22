// Client-side mirror of `apps/api/app/modules/guard/capability_catalog.py`.
//
// The Python module is the source of truth — publish enforces this matrix
// server-side. This exists so the draft-editor UI can surface "target ×
// operation is not certified" before the round-trip. Stale mirror =
// less-helpful UI, never a bad profile in the DB.

export const CATALOG_VERSION = "2026.09.22.v2-helicone-passthrough"

export type Operation =
  | "anthropic_messages"
  | "anthropic_count_tokens"
  | "openai_chat_completions"
  | "openai_responses"

export const ALL_OPERATIONS: Operation[] = [
  "anthropic_messages",
  "anthropic_count_tokens",
  "openai_chat_completions",
  "openai_responses",
]

export type Transport = "native_http" | "litellm_sdk" | "http_passthrough"

export type Integration =
  | "portkey"
  | "openrouter"
  | "helicone_anthropic"
  | "helicone_openai"
  | "azure_openai"
  | "custom"

// Native HTTP certified per provider. Preferred for Anthropic + OpenAI:
// preserves the vendor's protocol contract end-to-end, no SDK translation.
const _NATIVE_HTTP: Record<string, Operation[]> = {
  anthropic: ["anthropic_messages", "anthropic_count_tokens"],
  openai: ["openai_chat_completions", "openai_responses"],
}

// LiteLLM SDK certified per provider. Anything else = not certified.
const _LITELLM_SDK: Record<string, Operation[]> = {
  anthropic: ["anthropic_messages", "anthropic_count_tokens"],
  openai: ["openai_chat_completions", "openai_responses"],
}

// HTTP passthrough certified per integration. Keep in sync with
// _HTTP_PASSTHROUGH_CERTIFIED in apps/api/app/modules/guard/capability_catalog.py —
// the Python module is the source of truth and the server enforces at
// publish time. This mirror lets the draft editor flag uncertified
// (integration, operation) tuples before the round-trip.
const _HTTP_PASSTHROUGH: Record<Integration, Operation[]> = {
  portkey: [],
  openrouter: ["openai_chat_completions"],
  helicone_anthropic: ["anthropic_messages"],
  helicone_openai: ["openai_chat_completions"],
  azure_openai: [],
  custom: [],
}

export type TargetShape =
  | { transport: "native_http"; provider: string }
  | { transport: "litellm_sdk"; provider: string }
  | { transport: "http_passthrough"; integration: Integration }

export function certifiedOperations(target: TargetShape): Set<Operation> {
  if (target.transport === "native_http") {
    return new Set(_NATIVE_HTTP[target.provider.toLowerCase()] ?? [])
  }
  if (target.transport === "litellm_sdk") {
    return new Set(_LITELLM_SDK[target.provider.toLowerCase()] ?? [])
  }
  return new Set(_HTTP_PASSTHROUGH[target.integration] ?? [])
}

export interface CatalogError {
  target_index: number
  target_id: string
  missing: Operation[]
  where: string
  hint: string
}

// Mirrors `validate_targets_against_accepts()` in the Python catalog:
// every target must serve every accepted operation, since the coordinator
// falls back through the list and clients cannot know in advance which
// target their request lands on.
export function validateTargetsAgainstAccepts(args: {
  accepts: Operation[]
  targets: Array<TargetShape & { id: string }>
}): CatalogError[] {
  const errors: CatalogError[] = []
  args.targets.forEach((target, i) => {
    const certified = certifiedOperations(target)
    const missing = args.accepts.filter(op => !certified.has(op))
    if (missing.length === 0) return
    const where =
      target.transport === "http_passthrough"
        ? `transport=http_passthrough, integration=${target.integration}`
        : `transport=${target.transport}, provider=${target.provider}`
    const hint = target.transport === "http_passthrough"
      ? "Pick an integration + operation combo that ships in the current capability catalog."
      : "Remove the operation from accepts, or drop this target."
    errors.push({ target_index: i, target_id: target.id, missing, where, hint })
  })
  return errors
}
