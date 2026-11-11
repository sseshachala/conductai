/**
 * Shared token/usage formatting for every table that shows per-call LLM
 * usage (Guard overview, Guard activity feed, Flight Recorder, CSV export).
 *
 * Rule (#2069): null/undefined means unknown and renders as "—"; a known
 * zero renders as 0. Missing usage is never presented as zero.
 */
export const UNKNOWN = "—"

const SOURCE_LABELS: Record<string, string> = {
  provider: "Provider-reported",
  estimated: "Estimated",
  client_reported: "Client-reported",
}
const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  partial: "Partial",
  unavailable: "Unavailable",
  no_upstream: "No upstream call",
}

export function usageSourceLabel(source: string | null | undefined): string | null {
  return source ? (SOURCE_LABELS[source] ?? source) : null
}

/** Label for non-complete statuses only; "complete" and legacy NULL show nothing. */
export function usageStatusLabel(status: string | null | undefined): string | null {
  return status ? (STATUS_LABELS[status] ?? null) : null
}

export function formatCount(n: number | null | undefined): string {
  if (n == null) return UNKNOWN
  return n >= 1_000 ? `${(n / 1_000).toFixed(0)}k` : `${n}`
}

export function formatCostUsd(usd: number | null | undefined): string {
  if (usd == null) return UNKNOWN
  return `$${usd < 0.01 && usd > 0 ? usd.toFixed(4) : usd.toFixed(2)}`
}

/**
 * "N in / N out". Returns null when both sides are unknown so the caller can
 * render an em-dash. A known zero is shown as "0 in"; an unknown side is "— in".
 */
export function formatTokensUsed(
  input: number | null | undefined,
  output: number | null | undefined,
): string | null {
  if (input == null && output == null) return null
  return `${formatCount(input)} in / ${formatCount(output)} out`
}
