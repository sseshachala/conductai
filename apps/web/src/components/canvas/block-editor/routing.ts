import type { RoutingTable } from "@/hooks/useRoutingTable"

// ── Client-side model router preview (mirrors model_router.py) ────────────────

const MODEL_LABELS: Record<string, string> = {
  "claude-opus-4-7":            "Claude Opus",
  "claude-sonnet-4-6":          "Claude Sonnet",
  "claude-haiku-4-5-20251001":  "Claude Haiku",
  "gpt-4.1":                    "GPT-4.1",
  "gpt-4.1-mini":               "GPT-4.1 Mini",
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
}

const SLUG_CATEGORY: Record<string, string> = {
  autopilot_quick: "code_implementation", autopilot_full: "code_implementation",
  autopilot_approved: "code_implementation", dependency_updater: "code_implementation",
  security_patch_updater: "code_implementation",
  pr_reviewer: "code_review", copilot_reviewer: "code_review", release_readiness: "code_review",
  security_scanner: "security",
  issue_triage: "triage", ci_notify: "triage", flaky_test_detective: "triage",
  release_notes: "summarization", postmortem_drafter: "summarization", docs_drift_detector: "summarization",
  incident_responder: "reasoning", terraform_reviewer: "reasoning",
}

const POLICY: Record<string, Record<string, [string, string, string]>> = {
  code_implementation: { quality: ["anthropic", "claude-opus-4-7", "code implementation benefits from strongest reasoning"], balanced: ["anthropic", "claude-sonnet-4-6", "balanced model for code implementation"], speed: ["anthropic", "claude-sonnet-4-6", "sonnet is fast enough for code tasks"], cost: ["openai", "gpt-4.1-mini", "cost-efficient model for code implementation"] },
  code_review:         { quality: ["anthropic", "claude-opus-4-7", "code review benefits from strongest reasoning model"], balanced: ["anthropic", "claude-sonnet-4-6", "balanced model for code review"], speed: ["openai", "gpt-4.1-mini", "fast and efficient for code review"], cost: ["openai", "gpt-4.1-mini", "cost-efficient for structured code review output"] },
  security:            { quality: ["anthropic", "claude-opus-4-7", "security scanning requires highest-precision model"], balanced: ["anthropic", "claude-opus-4-7", "security scanning: quality always preferred over cost"], speed: ["anthropic", "claude-sonnet-4-6", "sonnet for security when speed is prioritized"], cost: ["anthropic", "claude-sonnet-4-6", "sonnet minimum viable for security"] },
  triage:              { quality: ["anthropic", "claude-sonnet-4-6", "sonnet sufficient for structured triage tasks"], balanced: ["openai", "gpt-4.1-mini", "balanced and efficient for triage"], speed: ["openai", "gpt-4.1-mini", "fast triage classification"], cost: ["openai", "gpt-4.1-mini", "cost-optimal for simple triage tasks"] },
  summarization:       { quality: ["anthropic", "claude-sonnet-4-6", "sonnet more than sufficient for summarization"], balanced: ["openai", "gpt-4.1-mini", "balanced model for summarization"], speed: ["openai", "gpt-4.1-mini", "fast summarization"], cost: ["openai", "gpt-4.1-mini", "cost-optimal for summarization"] },
  reasoning:           { quality: ["anthropic", "claude-opus-4-7", "reasoning tasks benefit from strongest model"], balanced: ["anthropic", "claude-sonnet-4-6", "balanced model for reasoning tasks"], speed: ["anthropic", "claude-sonnet-4-6", "sonnet balances speed and reasoning depth"], cost: ["openai", "gpt-4.1-mini", "cost-efficient minimum viable reasoning"] },
}

const PREF_DEFAULTS: Record<string, [string, string, string]> = {
  quality: ["anthropic", "claude-opus-4-7", "quality preference: strongest model"],
  balanced: ["anthropic", "claude-sonnet-4-6", "balanced preference: default model"],
  speed: ["openai", "gpt-4.1-mini", "speed preference: efficient model"],
  cost: ["openai", "gpt-4.1-mini", "cost preference: efficient model"],
}

const PROVIDER_DEFAULTS: Record<string, Record<string, [string, string]>> = {
  anthropic: {
    code_implementation: ["claude-sonnet-4-6", "anthropic override: balanced default for code implementation"],
    code_review: ["claude-sonnet-4-6", "anthropic override: balanced default for code review"],
    security: ["claude-opus-4-7", "anthropic override: strongest model for security"],
    triage: ["claude-sonnet-4-6", "anthropic override: balanced default for triage"],
    summarization: ["claude-sonnet-4-6", "anthropic override: balanced default for summarization"],
    reasoning: ["claude-sonnet-4-6", "anthropic override: balanced default for reasoning"],
    unknown: ["claude-sonnet-4-6", "anthropic override: balanced default model"],
  },
  openai: {
    code_implementation: ["gpt-4.1-mini", "openai override: efficient model for code implementation"],
    code_review: ["gpt-4.1-mini", "openai override: efficient model for code review"],
    security: ["gpt-4.1", "openai override: strongest available OpenAI model for security"],
    triage: ["gpt-4.1-mini", "openai override: efficient model for triage"],
    summarization: ["gpt-4.1-mini", "openai override: efficient model for summarization"],
    reasoning: ["gpt-4.1", "openai override: strongest available OpenAI model for reasoning"],
    unknown: ["gpt-4.1-mini", "openai override: balanced default model"],
  },
}

export function previewModel(
  playbookSlug: string | null | undefined,
  pref: string,
  providerOverride?: string,
  routingTable?: RoutingTable | null,
): [string, string, string] {
  const p = (pref || "balanced").toLowerCase()
  const category = SLUG_CATEGORY[playbookSlug ?? ""] ?? ""
  const override = (providerOverride || "").toLowerCase()
  if (override === "anthropic" || override === "openai") {
    const [model, reason] = PROVIDER_DEFAULTS[override][category || "unknown"] ?? PROVIDER_DEFAULTS[override].unknown
    return [PROVIDER_LABELS[override] ?? override, MODEL_LABELS[model] ?? model, reason]
  }
  // Prefer live DB table when available
  if (routingTable) {
    const row = routingTable[category]?.[p] ?? routingTable[""]?.[p]
    if (row) {
      return [PROVIDER_LABELS[row.provider] ?? row.provider, MODEL_LABELS[row.model_id] ?? row.model_id, row.reason]
    }
  }
  const [provider, model, reason] = (category ? POLICY[category]?.[p] : null) ?? PREF_DEFAULTS[p] ?? ["anthropic", "claude-sonnet-4-6", "default"]
  return [PROVIDER_LABELS[provider] ?? provider, MODEL_LABELS[model] ?? model, reason]
}

// ── Schedule cron presets ─────────────────────────────────────────────────────

export const CRON_PRESETS: { label: string; value: string }[] = [
  { label: "Every hour",             value: "0 * * * *"   },
  { label: "Every day at 9am",       value: "0 9 * * *"   },
  { label: "Every weekday at 9am",   value: "0 9 * * 1-5" },
  { label: "Every week on Monday",   value: "0 9 * * 1"   },
  { label: "Every month on the 1st", value: "0 9 1 * *"   },
  { label: "Custom (enter cron)",    value: "__custom__"  },
]

export function matchPreset(cron: string): string {
  return CRON_PRESETS.find(p => p.value === cron)?.value ?? "__custom__"
}
