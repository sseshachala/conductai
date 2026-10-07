import { API, AuthFetch } from "./client"

export const base = () => `${API}/guard`

// ─── Structured validation errors (PR 6, #2033) ──────────────────────
// Publish + save endpoints for Gateway Profile v2 return errors as
// ``{"detail": {"summary": "...", "errors": [{"path": "targets.2.
// credential_ref", "message": "...", "target_index": 2, "type":
// "value_error"}]}}``. `_formatGatewayError` collapses that back into
// a human-readable string so `new Error(msg).message` reads sensibly
// wherever the editor dialogs surface it. Callers that want per-target
// highlighting can catch and re-parse via `GatewayValidationError`.
export interface GatewayValidationErrorItem {
  path: string
  message: string
  target_index: number | null
  type: string
}

const GATEWAY_FIELD_LABELS: Record<string, string> = {
  name: "Name", model_alias: "Alias", timeout_seconds: "Timeout", max_attempts: "Max attempts",
  id: "Role", provider: "Provider", model: "Model", credential_ref: "Credential",
  targets: "Targets", accepts: "Supported APIs", endpoint: "Endpoint", transport: "Transport",
  rpm: "Requests per minute", tpm: "Tokens per minute", agent_limits: "Agent limits", agent_identity_id: "Agent identity",
}

function validationMessage(error: GatewayValidationErrorItem, field: string): string {
  if (field === "rpm" || field === "tpm") return "Enter a positive whole number up to 2147483647, or leave it blank."
  if (field === "agent_identity_id") return "Choose an agent in this workspace."
  if (field === "agent_limits" && error.type === "too_long") return "Use no more than 200 agent limits per profile."
  if (field === "timeout_seconds") return "Enter a whole number from 1 to 600 seconds."
  if (field === "max_attempts") return "Enter a whole number from 1 to 5."
  if (field === "credential_ref") return "Choose a credential vault and handle."
  if (error.type === "missing" || error.type === "string_too_short") {
    if (field === "model_alias") return "Enter an alias."
    if (field === "name") return "Enter a name."
    if (field === "model") return "Choose a model."
    if (field === "provider") return "Choose a provider."
    if (field === "id") return "Enter a role."
  }
  if (error.type === "string_too_long" && (field === "model_alias" || field === "name")) {
    return "Use no more than 128 characters."
  }
  return error.message
}

export class GatewayValidationError extends Error {
  summary: string
  errors: GatewayValidationErrorItem[]

  constructor(summary: string, errors: GatewayValidationErrorItem[]) {
    const lines = errors.slice(0, 3).map((e) => {
      const field = e.path.split(".").at(-1) ?? ""
      const label = GATEWAY_FIELD_LABELS[field] ?? (field.replaceAll("_", " ") || "Profile")
      const where =
        e.target_index !== null && e.target_index !== undefined
          ? `Target ${e.target_index + 1} - ${label}`
          : label
      return `${where}: ${validationMessage(e, field)}`
    })
    if (errors.length > 3) {
      lines.push(`+${errors.length - 3} more`)
    }
    const heading = summary === "schema invalid" ? "Check the profile fields."
      : summary === "capability check failed" ? "Check the target compatibility." : summary
    super([heading, ...lines].filter(Boolean).join(" "))
    this.name = "GatewayValidationError"
    this.summary = summary
    this.errors = errors
  }
}

/**
 * Parse a response body into a readable error. Prefers the structured
 * shape (PR 6). Falls back to the raw text so older-shape backends and
 * non-validation 4xx/5xx still surface something legible.
 */
function _formatGatewayError(bodyText: string, status: number): Error {
  try {
    const parsed = JSON.parse(bodyText)
    const detail = parsed?.detail
    if (Array.isArray(detail)) {
      return new GatewayValidationError("Check the profile fields.", detail.map(item => ({
        path: Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== "body").join(".") : "",
        message: typeof item.msg === "string" ? item.msg : "Invalid value.",
        type: typeof item.type === "string" ? item.type : "value_error", target_index: null,
      })))
    }
    if (
      detail &&
      typeof detail === "object" &&
      Array.isArray(detail.errors)
    ) {
      return new GatewayValidationError(
        typeof detail.summary === "string" ? detail.summary : "invalid",
        detail.errors as GatewayValidationErrorItem[],
      )
    }
    if (typeof detail === "string" && detail.length > 0) {
      if (detail.startsWith("schema invalid:")) return new Error("Check the profile fields and try again.")
      return new Error(detail)
    }
  } catch {
    // fall through
  }
  return new Error(bodyText || `HTTP ${status}`)
}

// Mutation helpers that THROW on non-2xx and return the parsed JSON body.
// The base `post`/`put`/`del` in ./client swallow errors — the caller gets
// a raw Response object even for 4xx/5xx, which silently masks server
// rejections. Every Gateway v2 mutation goes through these so the UI
// dialogs see errors and surface them.
export async function _mutateJson<T>(
  f: AuthFetch, method: "POST" | "PUT" | "PATCH", url: string, body: unknown,
): Promise<T> {
  const res = await f(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw _formatGatewayError(text, res.status)
  }
  return res.json() as Promise<T>
}

export async function _mutateVoid(
  f: AuthFetch, method: "DELETE", url: string,
): Promise<void> {
  const res = await f(url, { method })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw _formatGatewayError(text, res.status)
  }
}
