// Vault (environment) selection shared by the Guard-rules and Alerts cards:
// the selected Vault decides which credential a new channel uses.

export interface VaultEnvironment { id: string; name: string }
export interface VaultEntry { id: string; handle: string; environment_id: string | null; environment_name: string | null }
export type SlackIntegration = VaultEntry

/** Vault services a channel type can reference. */
export type VaultService = "slack" | "pagerduty" | "webhook" | "email"
export type VaultEntries = Record<VaultService, VaultEntry[]>

export const EMPTY_VAULT_ENTRIES: VaultEntries = { slack: [], pagerduty: [], webhook: [], email: [] }

export const VAULT_SERVICE_LABEL: Record<VaultService, string> = {
  slack: "Slack", pagerduty: "PagerDuty", webhook: "Webhook", email: "Email",
}

/** The Slack integration to use for a new channel: the selected Vault's, else the first. */
export function slackIntegrationFor(integrations: SlackIntegration[], envId: string): SlackIntegration | null {
  return envId
    ? (integrations.find(i => i.environment_id === envId) ?? null)
    : (integrations[0] ?? null)
}

/** Entries of one service that live in the selected Vault (all when none is selected). */
export function entriesForEnv(entries: VaultEntry[], envId: string): VaultEntry[] {
  return envId ? entries.filter(e => e.environment_id === envId) : entries
}

/** Label for the Vault a channel's entry lives in, from the API row or the loaded entries. */
export function channelVaultLabel(
  ch: { integration_id?: string | null; environment_name?: string | null },
  entries: VaultEntry[],
): string | null {
  if (!ch.integration_id) return null
  if (ch.environment_name) return ch.environment_name
  const e = entries.find(i => i.id === ch.integration_id)
  return e ? (e.environment_name ?? "(default env)") : null
}
