/**
 * Shared "N in / N out" token formatter used by every table that shows
 * per-call LLM token usage (Guard overview, Guard activity feed).
 *
 * Returns null when both sides are missing so the caller can render an
 * em-dash for non-LLM tool calls (bash/edit/read) instead of "0 in / 0 out".
 */
export function formatTokensUsed(
  input: number | null | undefined,
  output: number | null | undefined,
): string | null {
  if (input == null && output == null) return null
  const fmt = (n: number) => (n >= 1_000 ? `${(n / 1_000).toFixed(0)}k` : `${n}`)
  const parts: string[] = []
  if (input) parts.push(`${fmt(input)} in`)
  if (output) parts.push(`${fmt(output)} out`)
  return parts.join(" / ") || null
}
