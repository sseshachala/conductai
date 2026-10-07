import type { GatewayProfileV2Out } from "@/lib/api/guard"

export type EnvironmentRow = { id: string; name: string }

export interface PresetChip {
  label: string
  hint: string
  name: string
  workingCopy: Record<string, unknown>
}

// Model IDs pulled from the runtime pins we know work today:
// Anthropic 4.x family, OpenAI GA models. Adjust in one place when
// the pinned catalog moves.
// Presets pair same-vendor fallbacks only. The capability catalog
// requires every target to serve every accepted operation — so
// "Anthropic primary + OpenAI fallback" fails publish because OpenAI
// can't serve anthropic_messages. If a customer wants cross-vendor
// failover, that's a follow-up on top of the passthrough executor
// (#2005) which translates between surfaces.
export const PRESET_CHIPS: PresetChip[] = [
  {
    label: "Claude Sonnet + Haiku fallback",
    hint: "Primary → Claude Sonnet; fallback → Claude Haiku.",
    name: "claude-sonnet",
    workingCopy: {
      name: "claude-sonnet",
      model_alias: "claude-sonnet",
      timeout_seconds: 60,
      max_attempts: 2,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "anthropic", model: "claude-sonnet-4-6",
          credential_ref: "",
        },
        {
          id: "fallback", transport: "native_http",
          provider: "anthropic", model: "claude-haiku-4-5-20251001",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "Claude Opus (single)",
    hint: "Most capable Anthropic model, no fallback.",
    name: "claude-opus",
    workingCopy: {
      name: "claude-opus",
      model_alias: "claude-opus",
      timeout_seconds: 60,
      max_attempts: 1,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "anthropic", model: "claude-opus-4-7",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "GPT-4o + mini fallback",
    hint: "Primary → GPT-4o; fallback → GPT-4o mini.",
    name: "gpt-4o",
    workingCopy: {
      name: "gpt-4o",
      model_alias: "gpt-4o",
      timeout_seconds: 60,
      max_attempts: 2,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "openai", model: "gpt-4o",
          credential_ref: "",
        },
        {
          id: "fallback", transport: "native_http",
          provider: "openai", model: "gpt-4o-mini",
          credential_ref: "",
        },
      ],
    },
  },
  {
    label: "o1 reasoning (single)",
    hint: "OpenAI o1, no fallback.",
    name: "o1",
    workingCopy: {
      name: "o1",
      model_alias: "o1",
      timeout_seconds: 120,
      max_attempts: 1,
      targets: [
        {
          id: "primary", transport: "native_http",
          provider: "openai", model: "o1",
          credential_ref: "",
        },
      ],
    },
  },
]

for (const [index, label, name] of [
  [0, "Claude via LiteLLM", "claude-litellm"],
  [2, "OpenAI via LiteLLM", "openai-litellm"],
] as const) {
  const base = PRESET_CHIPS[index]
  const targets = base.workingCopy.targets as Record<string, unknown>[]
  PRESET_CHIPS.push({
    label, hint: base.hint, name,
    workingCopy: { ...base.workingCopy, name, model_alias: name,
      targets: targets.map(target => ({ ...target, transport: "litellm_sdk" })),
    },
  })
}
PRESET_CHIPS.push({
  label: "Claude + OpenAI fallback via LiteLLM",
  hint: "Claude primary, OpenAI fallback.",
  name: "claude-openai",
  workingCopy: {
    name: "claude-openai", model_alias: "claude-openai", timeout_seconds: 60, max_attempts: 2,
    accepts: ["anthropic_messages", "openai_chat_completions"],
    targets: [
      { id: "primary", transport: "litellm_sdk", provider: "anthropic", model: "claude-sonnet-4-6", credential_ref: "" },
      { id: "fallback", transport: "litellm_sdk", provider: "openai", model: "gpt-4o", credential_ref: "" },
    ],
  },
})

export function isPublished(profile: GatewayProfileV2Out): boolean {
  // v3: served state lives on active_revision_id. Working_copy is
  // locked whenever this is non-null.
  return profile.active_revision_id !== null
}

export function conditIdentifier(profile: GatewayProfileV2Out): string {
  const alias = profile.model_alias ?? ""
  return alias ? `cond-${profile.cond_code}-${alias}` : `cond-${profile.cond_code}`
}
