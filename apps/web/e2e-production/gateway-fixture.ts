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
  const excluded: Record<string, number> = {}
  const exclude = (reason: string) => { excluded[reason] = (excluded[reason] ?? 0) + 1 }
  for (const profile of profiles) {
    if (!profile.active_revision_id) { exclude("unpublished"); continue }
    // Read the served snapshot, never the editor's working copy.
    const snapshot = await read(`${base}/${profile.id}/revisions/${profile.active_revision_id}`) as GatewayProfileV2WorkingCopy
    const model = `cond-${profile.cond_code}-${snapshot.model_alias}`
    if (requestedModel && requestedModel !== model) { exclude("configured_identifier_mismatch"); continue }
    const missing = required.filter(operation => !snapshot.accepts.includes(operation as typeof snapshot.accepts[number]))
    if (missing.length) { exclude(`missing_operations:${missing.join(",")}`); continue }
    if (!snapshot.targets.length) { exclude("no_targets"); continue }
    if (!snapshot.targets.every(target => target.transport === "native_http" || target.transport === "litellm_sdk")) {
      exclude("unsupported_transport"); continue
    }
    if (!snapshot.targets.every(target => "provider" in target && target.provider === provider)) {
      exclude("provider_mismatch"); continue
    }
    if (!snapshot.targets.every(target => Boolean(target.model.trim()) && /^vault:\/\/[^/]+\/[^/]+$/.test(target.credential_ref))) {
      exclude("missing_model_or_vault_reference"); continue
    }
    matches.push({ model, revisionId: profile.active_revision_id, condCode: profile.cond_code })
  }
  if (matches.length !== 1) {
    const guidance = matches.length > 1
      ? `Set PROD_E2E_${provider.toUpperCase()}_MODEL to select one eligible profile.`
      : "Publish an eligible profile in this canary account's workspace, or correct its configured identifier. Setting an identifier cannot make an ineligible profile qualify."
    // Counts and fixed reason codes only: never log snapshots, credentials, or user-defined names.
    throw new Error(`${provider} canary requires one published v2 profile with ${required.join(", ")} and Vault-backed ${provider} targets; found ${matches.length}. ${guidance} Inventory: ${JSON.stringify({ total: profiles.length, excluded })}`)
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
