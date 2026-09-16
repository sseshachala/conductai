// Client-side mirror of `apps/api/app/modules/guard/capability_catalog.py`.
//
// The Python module is the source of truth — publish enforces this matrix
// server-side. This exists so the draft-editor UI can surface "target ×
// operation is not certified" before the round-trip. Stale mirror =
// less-helpful UI, never a bad profile in the DB.

export const CATALOG_VERSION = "2026.09.15.v2-launch-litellm-only"

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

export type Transport = "litellm_sdk" | "http_passthrough"

export type Integration =
  | "portkey"
  | "openrouter"
  | "helicone_anthropic"
  | "helicone_openai"
  | "azure_openai"
  | "custom"

// LiteLLM SDK certified per provider. Anything else = not certified.
const _LITELLM_SDK: Record<string, Operation[]> = {
  anthropic: ["anthropic_messages", "anthropic_count_tokens"],
  openai: ["openai_chat_completions", "openai_responses"],
}

// HTTP passthrough is empty in the launch set — coordinator raises
// UnsupportedTransport until #2005 lands the executor.
const _HTTP_PASSTHROUGH: Record<Integration, Operation[]> = {
  portkey: [], openrouter: [], helicone_anthropic: [],
  helicone_openai: [], azure_openai: [], custom: [],
}

export type TargetShape =
  | { transport: "litellm_sdk"; provider: string }
  | { transport: "http_passthrough"; integration: Integration }

export function certifiedOperations(target: TargetShape): Set<Operation> {
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
    const where = target.transport === "litellm_sdk"
      ? `transport=litellm_sdk, provider=${target.provider}`
      : `transport=http_passthrough, integration=${target.integration}`
    const hint = target.transport === "http_passthrough"
      ? "HTTP passthrough targets aren't certified until #2005 lands the executor."
      : "Remove the operation from accepts, or drop this target."
    errors.push({ target_index: i, target_id: target.id, missing, where, hint })
  })
  return errors
}
