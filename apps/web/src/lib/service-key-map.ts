/**
 * service-key-map.ts
 *
 * Single source of truth for mapping environment-variable key names to
 * Conduct's integration service IDs.
 *
 * Two structures live here:
 *
 *   SERVICE_KEY_PREFIXES  — "starts with" rules used for fast auto-detection
 *                           when a user adds or edits a var.
 *
 *   SERVICE_DETECTION     — per-service field definitions used by the
 *                           TestConnectionsPanel (exact key lists, labels,
 *                           badge colours, required flags).
 *
 * To add a new provider:
 *   1. Add a prefix entry to SERVICE_KEY_PREFIXES.
 *   2. Add a full entry to SERVICE_DETECTION.
 *   That's it — the UI and auto-trigger logic pick it up automatically.
 */

// ── Starts-with prefix table ─────────────────────────────────────────────────
// More specific prefixes must come before shorter ones so the first match wins.
// "DO_" is intentionally omitted — too short and collides with unrelated keys.

export const SERVICE_KEY_PREFIXES: Array<[prefix: string, service: string]> = [
  ["GITHUB_",        "github"],
  ["GH_",            "github"],
  ["SLACK_",         "slack"],
  ["ANTHROPIC_",     "anthropic"],
  ["CLAUDE_",        "anthropic"],
  ["LINEAR_",        "linear"],
  ["DIGITALOCEAN_",  "digitalocean"],
  ["DO_API_",        "digitalocean"],
  ["DO_TOKEN",       "digitalocean"],  // specific enough to be unambiguous
  ["RESEND_",        "email"],
  ["SENDGRID_",      "email"],
  ["VERCEL_",        "vercel"],
  ["RAILWAY_",       "railway"],
]

/** Returns the service ID for an env-var key, or null if unrecognised. */
export function keyToService(key: string): string | null {
  const upper = key.toUpperCase()
  for (const [prefix, service] of SERVICE_KEY_PREFIXES) {
    if (upper.startsWith(prefix)) return service
  }
  return null
}

/** Returns the unique set of service IDs touched by a list of env-var keys. */
export function affectedServices(keys: string[]): string[] {
  return [...new Set(keys.map(keyToService).filter(Boolean) as string[])]
}

// ── Per-service field definitions ────────────────────────────────────────────

export interface ServiceFieldDef {
  /** Field name that POST /credentials/test expects in the `credentials` dict. */
  fieldKey: string
  /** Human-readable label shown in the card. */
  label: string
  /** Common env-var names to scan, in priority order. */
  envKeys: string[]
  /** Card is testable only when all required fields have a value. */
  required: boolean
}

export interface ServiceDetection {
  label: string
  abbr: string
  /** Tailwind classes for the coloured badge. */
  color: string
  fields: ServiceFieldDef[]
}

export const SERVICE_DETECTION: Record<string, ServiceDetection> = {
  github: {
    label: "GitHub", abbr: "GH", color: "bg-stone-900 text-white",
    fields: [{ fieldKey: "token", label: "Personal access token", required: true,
      envKeys: ["GITHUB_TOKEN", "GITHUB_PAT", "GH_TOKEN", "GITHUB_ACCESS_TOKEN", "GH_PAT"] }],
  },
  slack: {
    label: "Slack", abbr: "SL", color: "bg-purple-600 text-white",
    fields: [{ fieldKey: "token", label: "Bot token", required: true,
      envKeys: ["SLACK_BOT_TOKEN", "SLACK_TOKEN", "SLACK_ACCESS_TOKEN", "SLACK_API_TOKEN"] }],
  },
  anthropic: {
    label: "Anthropic", abbr: "AI", color: "bg-amber-600 text-white",
    fields: [{ fieldKey: "api_key", label: "API key", required: true,
      envKeys: ["ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY", "ANTHROPIC_TOKEN"] }],
  },
  linear: {
    label: "Linear", abbr: "LN", color: "bg-indigo-600 text-white",
    fields: [{ fieldKey: "api_key", label: "API key", required: true,
      envKeys: ["LINEAR_API_KEY", "LINEAR_KEY", "LINEAR_TOKEN", "LINEAR_API_TOKEN"] }],
  },
  digitalocean: {
    label: "DigitalOcean", abbr: "DO", color: "bg-blue-500 text-white",
    fields: [{ fieldKey: "token", label: "Personal access token", required: true,
      envKeys: ["DIGITALOCEAN_TOKEN", "DO_TOKEN", "DIGITALOCEAN_API_TOKEN", "DO_API_TOKEN"] }],
  },
  email: {
    label: "Email", abbr: "EM", color: "bg-emerald-600 text-white",
    fields: [
      { fieldKey: "resend_api_key",   label: "Resend API key",   required: false,
        envKeys: ["RESEND_API_KEY", "RESEND_KEY"] },
      { fieldKey: "sendgrid_api_key", label: "SendGrid API key", required: false,
        envKeys: ["SENDGRID_API_KEY", "SENDGRID_KEY"] },
    ],
  },
}
