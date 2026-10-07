// ── helpers ───────────────────────────────────────────────────────────────────

// Patterns that strongly suggest a hardcoded secret rather than a template ref.
const SECRET_PATTERNS = [
  /^ghp_[A-Za-z0-9]{36}/,           // GitHub personal access token
  /^github_pat_[A-Za-z0-9_]{82}/,    // GitHub fine-grained PAT
  /^ghs_[A-Za-z0-9]{36}/,           // GitHub app installation token
  /^xoxb-[0-9]+-[A-Za-z0-9-]+/,     // Slack bot token
  /^xoxp-[0-9]+-[A-Za-z0-9-]+/,     // Slack user token
  /^xoxa-[0-9]+-[A-Za-z0-9-]+/,     // Slack legacy token
  /^sk-[A-Za-z0-9]{20,}/,           // OpenAI / generic sk- key
  /^pk-[A-Za-z0-9]{20,}/,           // Generic pk- key
  /^Bearer\s+[A-Za-z0-9._-]{20,}/,  // Inline Bearer token
  /^[A-Za-z0-9_-]{40,}$/,           // Long opaque string (≥40 chars, no spaces)
]

const SECRET_FIELD_NAMES = /token|secret|key|password|api_key|access_token|auth/i

function looksLikeSecret(fieldName: string, value: unknown): boolean {
  if (typeof value !== "string" || !value.trim()) return false
  if (value.startsWith("{{") && value.endsWith("}}")) return false  // template ref — fine
  if (SECRET_FIELD_NAMES.test(fieldName)) return true
  return SECRET_PATTERNS.some(re => re.test(value.trim()))
}

export function findHardcodedSecrets(params: unknown): string[] {
  if (!params || typeof params !== "object") return []
  return Object.entries(params as Record<string, unknown>)
    .filter(([k, v]) => looksLikeSecret(k, v))
    .map(([k]) => k)
}

export function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object") return (acc as Record<string, unknown>)[key]
    return undefined
  }, obj)
}

export function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const keys = path.split(".")
  const result = { ...obj }
  let cur: Record<string, unknown> = result
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i]
    cur[k] = cur[k] && typeof cur[k] === "object" ? { ...(cur[k] as Record<string, unknown>) } : {}
    cur = cur[k] as Record<string, unknown>
  }
  cur[keys[keys.length - 1]] = value
  return result
}
