import type { GatewayProfileV2Out, GatewayProfileV2WorkingCopy } from "../src/lib/api/guard"

type ReadJson = (path: string) => Promise<unknown>

export async function publishedGatewayFixture(
  read: ReadJson,
  workspaceId: string,
  provider: "anthropic" | "openai",
  requestedModel?: string,
) {
  const base = `/workspaces/${workspaceId}/gateway-profiles-v2`
  const profiles = await read(base) as GatewayProfileV2Out[]
  const required = provider === "anthropic"
    ? ["anthropic_messages", "anthropic_count_tokens"]
    : ["openai_responses"]
  const matches = []
  for (const profile of profiles) {
    if (!profile.active_revision_id) continue
    // Read the served snapshot, never the editor's working copy.
    const snapshot = await read(`${base}/${profile.id}/revisions/${profile.active_revision_id}`) as GatewayProfileV2WorkingCopy
    const model = `cond-${profile.cond_code}-${snapshot.model_alias}`
    if (requestedModel && requestedModel !== model) continue
    if (!required.every(operation => snapshot.accepts.includes(operation as typeof snapshot.accepts[number]))) continue
    if (!snapshot.targets.length || !snapshot.targets.every(target =>
      target.transport !== "http_passthrough" && target.provider === provider &&
      Boolean(target.model.trim()) && /^vault:\/\/[^/]+\/[^/]+$/.test(target.credential_ref),
    )) continue
    matches.push({ model, revisionId: profile.active_revision_id, condCode: profile.cond_code })
  }
  if (matches.length !== 1) {
    throw new Error(`${provider} canary requires one published v2 profile with ${required.join(", ")} and Vault-backed ${provider} targets; found ${matches.length}. Set PROD_E2E_${provider.toUpperCase()}_MODEL to its cond-<code>-<alias> identifier when multiple profiles qualify.`)
  }
  return matches[0]
}

export type LegacyCatalogProfile = {
  id: string | null
  provider: string
  environment_id: string | null
  deployments: { model: string }[]
}

export function legacyCatalogModels(profiles: LegacyCatalogProfile[]): string[] {
  // The API is name-ordered, matching TransportResolver's default selection.
  // Synthetic legacy rows (id=null) are not persisted resolver candidates.
  const profile = profiles.find(p => p.id && p.environment_id === null && ["anthropic", "litellm"].includes(p.provider))
  return [...new Set((profile?.deployments ?? []).map(d => d.model.trim().replace(/^anthropic\//, "")).filter(Boolean))]
}
