// Vault (environment) selection shared by the Guard-rules and Alerts cards:
// the selected Vault decides which Slack credential a new channel uses.

export interface VaultEnvironment { id: string; name: string }
export interface SlackIntegration { id: string; handle: string; environment_id: string | null; environment_name: string | null }

/** The Slack integration to use for a new channel: the selected Vault's, else the first. */
export function slackIntegrationFor(integrations: SlackIntegration[], envId: string): SlackIntegration | null {
  return envId
    ? (integrations.find(i => i.environment_id === envId) ?? null)
    : (integrations[0] ?? null)
}
