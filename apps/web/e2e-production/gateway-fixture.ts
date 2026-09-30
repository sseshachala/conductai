import type { GatewayProfileV2Out, GatewayProfileV2WorkingCopy } from "../src/lib/api/guard"

type ReadJson = (path: string) => Promise<unknown>

export async function restorationPlan(read: ReadJson, workspaceId: string, provider: "anthropic" | "openai", requestedModel?: string) {
  if (requestedModel !== undefined && !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(requestedModel)) {
    throw new Error("Fixture model must be a plain upstream model ID")
  }
  const base = `/workspaces/${workspaceId}`
  const profiles = await read(`${base}/gateway-profiles-v2`) as GatewayProfileV2Out[]
  if (profiles.length) {
    await publishedGatewayFixture(read, workspaceId, provider)
    return null
  }
  const environments = await read("/environments") as { id: string; name?: string }[]
  const refs: string[] = []
  let providerRows = 0
  let productionRefs = 0
  for (const environment of environments) {
    const credentials = await read(`/credentials/by-environment/${environment.id}`) as { handle: string; service: string; fields: string[] }[]
    for (const credential of credentials) {
      if (credential.service === provider) providerRows++
      if (credential.service === provider && credential.fields.some(field => ["api_key", `${provider}_api_key`, `${provider.toUpperCase()}_API_KEY`].includes(field))) {
        refs.push(`vault://${environment.id}/${credential.handle}`)
        if (environment.name?.toLowerCase() === "production") productionRefs++
      }
    }
  }
  const models = requestedModel ? [requestedModel] : []
  if (refs.length !== 1 || models.length !== 1) {
    throw new Error(`${provider} restoration requires one existing environment-scoped provider credential and an explicit upstream model; found credentials=${refs.length}, models=${models.length}. Metadata: environments=${environments.length}, productionEnvironments=${environments.filter(env => env.name?.toLowerCase() === "production").length}, providerRows=${providerRows}, productionCredentials=${productionRefs}. No secrets were read and no profile was created.`)
  }
  const name = `production-canary-${provider}`
  return { name, working_copy: {
    name, model_alias: name,
    accepts: provider === "anthropic" ? ["anthropic_messages", "anthropic_count_tokens"] : ["openai_responses"],
    targets: [{ id: "primary", transport: "native_http", provider, model: models[0], credential_ref: refs[0] }],
  } }
}

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

export async function publishedCatalogModels(read: ReadJson, workspaceId: string): Promise<string[]> {
  const base = `/workspaces/${workspaceId}/gateway-profiles-v2`
  const profiles = await read(base) as GatewayProfileV2Out[]
  const models: string[] = []
  for (const profile of [...profiles].sort((a, b) => a.cond_code.localeCompare(b.cond_code))) {
    if (!profile.active_revision_id) continue
    const snapshot = await read(`${base}/${profile.id}/revisions/${profile.active_revision_id}`) as GatewayProfileV2WorkingCopy
    if (snapshot.accepts.includes("anthropic_messages")) models.push(`cond-${profile.cond_code}-${snapshot.model_alias}`)
  }
  return models
}
