"use client"

import type { Transport } from "@/lib/gatewayCapabilityCatalog"
import { modelsFromTierMap, INTEGRATION_KEY_HINTS, type EnvironmentRow, type CredentialRow, type DraftTarget, inputStyle } from "./state"
import { FieldLabel, CustomExtraHeadersField } from "./fields"

export function TargetRow({
  index, target, envs, isAdmin, credentialsByEnv, onLoadCredsFor,
  tierMap, onChange, onRemove, onMoveUp, onMoveDown, isFirst, isLast,
}: {
  index: number
  target: DraftTarget
  envs: EnvironmentRow[]
  isAdmin: boolean
  credentialsByEnv: Record<string, CredentialRow[]>
  onLoadCredsFor: (envId: string) => void
  tierMap: Record<string, Record<string, string>>
  onChange: (u: Partial<DraftTarget>) => void
  onRemove: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  isFirst: boolean
  isLast: boolean
}) {
  const creds = target.credential_env_id ? credentialsByEnv[target.credential_env_id] ?? [] : []
  // Prefer the workspace's LLM Model Primitives tier_map for this
  // provider; fall back to the hardcoded catalog if the workspace
  // hasn't customized (or if the primitives fetch failed).
  const modelsForProvider = (provider: string): Array<{ id: string; label: string }> => {
    // No fallback — primitives is authoritative. Empty list surfaces
    // the empty-state hint that points at Settings.
    return modelsFromTierMap(tierMap[provider])
  }
  const modelsForCurrent = modelsForProvider(target.provider)
  // Provider list = keys the workspace declared in primitives.
  // Sorted for stable render. Empty state handled in the render below.
  const providers = Object.keys(tierMap).sort()
  return (
    <div className="card grid grid-cols-1 items-end gap-2.5 sm:grid-cols-2 xl:grid-cols-[auto_repeat(4,minmax(0,1fr))_auto]" style={{ padding: 12 }}>
      <div className="flex items-center gap-1 sm:col-span-2 xl:col-span-1 xl:flex-col">
        <button className="btn btn-ghost btn-sm btn-icon" onClick={onMoveUp} disabled={!isAdmin || isFirst}
          style={{ height: 24, width: 24, opacity: isFirst ? 0.35 : 1 }} title="Move up">↑</button>
        <span style={{ fontSize: 11, color: "var(--text-3)" }}>#{index + 1}</span>
        <button className="btn btn-ghost btn-sm btn-icon" onClick={onMoveDown} disabled={!isAdmin || isLast}
          style={{ height: 24, width: 24, opacity: isLast ? 0.35 : 1 }} title="Move down">↓</button>
      </div>

      <FieldLabel label="Role" hint="First target = primary; the rest are fallbacks in order.">
        <input value={target.id} disabled={!isAdmin}
          placeholder={index === 0 ? "primary" : "fallback"}
          onChange={e => onChange({ id: e.target.value })} style={inputStyle} />
      </FieldLabel>

      <FieldLabel
        label="Transport"
        hint="Native HTTPS connects directly to Anthropic or OpenAI. LiteLLM SDK translates between supported provider protocols. HTTPS Passthrough connects to an external gateway."
      >
        <select value={target.transport} disabled={!isAdmin}
          onChange={e => onChange({ transport: e.target.value as Transport })}
          style={inputStyle}>
          <option value="native_http">Native HTTPS (recommended)</option>
          <option value="litellm_sdk">LiteLLM SDK</option>
          <option value="http_passthrough">HTTPS Passthrough</option>
        </select>
      </FieldLabel>

      {target.transport === "http_passthrough" ? (
        <FieldLabel
          label="Integration"
          hint="External gateway routing traffic on our behalf. All six integrations certified: OpenRouter, Portkey, Helicone (OpenAI + Anthropic), Azure OpenAI, and Custom. Portkey needs virtual_key/provider/config. Helicone vault holds two keys (HELICONE_API_KEY + vendor). Azure needs Resource endpoint + deployment name + api-version. Custom is a template — you pick protocol + endpoint + auth shape."
        >
          <select value={target.integration} disabled={!isAdmin}
            onChange={e => onChange({ integration: e.target.value })}
            style={inputStyle}>
            <option value="openrouter">openrouter (certified)</option>
            <option value="portkey">portkey (certified)</option>
            <option value="helicone_anthropic">helicone_anthropic (certified)</option>
            <option value="helicone_openai">helicone_openai (certified)</option>
            <option value="azure_openai">azure_openai (certified)</option>
            <option value="custom">custom (certified)</option>
          </select>
        </FieldLabel>
      ) : (
        <FieldLabel label="Provider" hint="Upstream provider — sourced from workspace LLM Model Primitives. Add providers under Settings → LLM Model Primitives. Only anthropic + openai + LiteLLM-compat (perplexity/together) are catalog-certified for native_http / litellm_sdk today; others surface a publish-time capability error.">
          <select value={target.provider} disabled={!isAdmin || providers.length === 0}
            onChange={e => {
              const provider = e.target.value
              const models = modelsForProvider(provider)
              const modelStillValid = models.some(m => m.id === target.model)
              onChange({
                provider,
                model: modelStillValid ? target.model : (models[0]?.id ?? ""),
              })
            }} style={inputStyle}>
            {providers.length === 0 ? (
              <option value="">— no providers in primitives — configure Settings → LLM Model Primitives —</option>
            ) : null}
            {providers.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </FieldLabel>
      )}

      <FieldLabel
        label={target.transport === "http_passthrough" && target.integration === "azure_openai" ? "Deployment name" : "Model"}
        hint={
          target.transport === "http_passthrough"
            ? (target.integration === "azure_openai"
                ? "Azure OpenAI deployment name — the URL becomes /openai/deployments/{deployment}/... Not a model id."
                : target.integration === "custom"
                    ? "Model id the request body carries — whatever your proxy expects (e.g. gpt-4o or claude-sonnet-4-6)."
                    : "Upstream model id in the integration's format (OpenRouter: `anthropic/claude-3.5-sonnet`, Portkey: `gpt-4o` or vendor-prefixed via virtual key).")
            : "Real upstream model ID the request goes to."
        }
      >
        {target.transport === "http_passthrough" ? (
          <input value={target.model} disabled={!isAdmin}
            placeholder={
              target.integration === "azure_openai" ? "gpt-4o-prod-deploy"
              : target.integration === "portkey" ? "gpt-4o"
              : target.integration === "custom" ? "gpt-4o"
              : "anthropic/claude-3.5-sonnet"
            }
            onChange={e => onChange({ model: e.target.value })}
            style={inputStyle} />
        ) : (
          <select value={target.model} disabled={!isAdmin}
            onChange={e => onChange({ model: e.target.value })} style={inputStyle}>
            {modelsForCurrent.length === 0 ? (
              <option value="">— no models for {target.provider} — configure Settings → LLM Model Primitives —</option>
            ) : null}
            {modelsForCurrent.map(m => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        )}
      </FieldLabel>

      {isAdmin ? (
        <button onClick={onRemove} className="btn btn-ghost btn-sm btn-icon"
          style={{ color: "var(--err)", borderColor: "var(--err-bd)" }} title="Remove target">×</button>
      ) : <div />}

      <div className="grid grid-cols-1 gap-2.5 sm:col-span-2 sm:grid-cols-2 xl:col-start-2 xl:col-end-7">
        <FieldLabel label="Credential vault" hint="Which environment holds the upstream API key.">
          <select value={target.credential_env_id} disabled={!isAdmin}
            onChange={e => {
              const envId = e.target.value
              onChange({ credential_env_id: envId, credential_handle: "" })
              onLoadCredsFor(envId)
            }} style={inputStyle}>
            <option value="">— pick vault —</option>
            {envs.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </FieldLabel>
        <FieldLabel label="Credential handle" hint="The named credential inside that vault (e.g. `anthropic`).">
          {creds.length > 0 ? (
            <select value={target.credential_handle} disabled={!isAdmin}
              onChange={e => onChange({ credential_handle: e.target.value })} style={inputStyle}>
              <option value="">— pick handle —</option>
              {creds.map(c => <option key={c.handle} value={c.handle}>{c.handle}</option>)}
            </select>
          ) : (
            <input value={target.credential_handle} disabled={!isAdmin}
              placeholder={target.credential_env_id ? "no credentials in this vault yet" : "pick a vault first"}
              onChange={e => onChange({ credential_handle: e.target.value })} style={inputStyle} />
          )}
          {target.transport === "http_passthrough" && INTEGRATION_KEY_HINTS[target.integration] ? (
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>
              Expected key in vault: <code>{INTEGRATION_KEY_HINTS[target.integration]}</code>
              {target.integration === "custom" ? (
                <> (or <code>api_key</code> / <code>CUSTOM_API_KEY</code>)</>
              ) : null}
            </span>
          ) : null}
        </FieldLabel>
      </div>

      {/* PR 4 — Portkey needs an upstream selector alongside the
          gateway key. Any one of virtual_key / provider / config
          satisfies the required-selector check server-side. */}
      {target.transport === "http_passthrough" && target.integration === "portkey" ? (
        <div className="grid grid-cols-1 gap-2.5 sm:col-span-2 sm:grid-cols-2 xl:col-start-2 xl:col-end-7 xl:grid-cols-3">
          <FieldLabel label="Virtual key" hint="Portkey virtual key ID (recommended — carries provider config). Sent as x-portkey-virtual-key.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.virtual_key ?? "")}
              disabled={!isAdmin}
              placeholder="vk-openai-prod"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  virtual_key: e.target.value || undefined,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
          <FieldLabel label="Provider" hint="Portkey provider slug (openai / anthropic / etc.). Sent as x-portkey-provider.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.provider ?? "")}
              disabled={!isAdmin}
              placeholder="openai"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  provider: e.target.value || undefined,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
          <FieldLabel label="Config ID" hint="Portkey saved config ID. Sent as x-portkey-config.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.config ?? "")}
              disabled={!isAdmin}
              placeholder="cfg_abc"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  config: e.target.value || undefined,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
        </div>
      ) : null}

      {/* PR 6 — Azure OpenAI needs per-tenant endpoint + api-version.
          Endpoint reuses the existing `endpoint` field; api-version
          lives in `provider_options` and is opaque to the schema. */}
      {target.transport === "http_passthrough" && target.integration === "azure_openai" ? (
        <div className="grid grid-cols-1 gap-2.5 sm:col-span-2 sm:grid-cols-2 xl:col-start-2 xl:col-end-7">
          <FieldLabel label="Resource endpoint" hint="Your Azure OpenAI resource URL, e.g. https://my-resource.openai.azure.com (no trailing path).">
            <input value={target.endpoint} disabled={!isAdmin}
              placeholder="https://my-resource.openai.azure.com"
              onChange={e => onChange({ endpoint: e.target.value })}
              style={inputStyle} />
          </FieldLabel>
          <FieldLabel label="api-version" hint="Azure OpenAI API version, e.g. 2024-06-01. Added as a URL query parameter.">
            <input
              value={String((target.provider_options as Record<string, unknown> | undefined)?.api_version ?? "")}
              disabled={!isAdmin}
              placeholder="2024-06-01"
              onChange={e => onChange({
                provider_options: {
                  ...(target.provider_options ?? {}),
                  api_version: e.target.value,
                },
              })}
              style={inputStyle} />
          </FieldLabel>
        </div>
      ) : null}

      {/* PR 7 — Custom integration exposes protocol + auth-header shape
          + extra headers JSON on the target itself. Endpoint reuses
          the existing `endpoint` field. All live in provider_options. */}
      {target.transport === "http_passthrough" && target.integration === "custom" ? (
        <>
          <div className="grid grid-cols-1 gap-2.5 sm:col-span-2 sm:grid-cols-2 xl:col-start-2 xl:col-end-7 xl:grid-cols-[2fr_1fr_1fr]">
            <FieldLabel label="Endpoint URL" hint="Full base URL up to /v1 (e.g. https://my-llm-proxy.example.com/v1). Suffixes like /chat/completions or /messages are added per operation.">
              <input value={target.endpoint} disabled={!isAdmin}
                placeholder="https://my-llm-proxy.example.com/v1"
                onChange={e => onChange({ endpoint: e.target.value })}
                style={inputStyle} />
            </FieldLabel>
            <FieldLabel label="Protocol" hint="Which wire shape your upstream speaks. Determines which operations publish will certify (openai_* vs anthropic_*).">
              <select
                value={String((target.provider_options as Record<string, unknown> | undefined)?.protocol ?? "")}
                disabled={!isAdmin}
                onChange={e => onChange({
                  provider_options: {
                    ...(target.provider_options ?? {}),
                    protocol: e.target.value || undefined,
                  },
                })}
                style={inputStyle}>
                <option value="">— pick protocol —</option>
                <option value="openai">OpenAI-shape</option>
                <option value="anthropic">Anthropic-shape</option>
              </select>
            </FieldLabel>
            <FieldLabel label="Bearer prefix" hint="Prepend `Bearer ` to the key value. Turn off if your proxy expects the raw key.">
              <select
                value={((target.provider_options as Record<string, unknown> | undefined)?.bearer_prefix ?? true) ? "yes" : "no"}
                disabled={!isAdmin}
                onChange={e => onChange({
                  provider_options: {
                    ...(target.provider_options ?? {}),
                    bearer_prefix: e.target.value === "yes",
                  },
                })}
                style={inputStyle}>
                <option value="yes">Bearer</option>
                <option value="no">Raw</option>
              </select>
            </FieldLabel>
          </div>
          <div className="grid grid-cols-1 gap-2.5 sm:col-span-2 xl:col-start-2 xl:col-end-7">
            <FieldLabel label="Auth header" hint="Name of the header carrying the API key (default: authorization). Reserved names (cookie / host / content-* / *-api-key etc.) are refused.">
              <input
                value={String((target.provider_options as Record<string, unknown> | undefined)?.auth_header ?? "")}
                disabled={!isAdmin}
                placeholder="authorization"
                onChange={e => onChange({
                  provider_options: {
                    ...(target.provider_options ?? {}),
                    auth_header: e.target.value,
                  },
                })}
                style={inputStyle} />
            </FieldLabel>
          </div>
          <div className="sm:col-span-2 xl:col-start-2 xl:col-end-7">
            <CustomExtraHeadersField
              value={target.provider_options as Record<string, unknown> | undefined}
              disabled={!isAdmin}
              onChange={next => onChange({ provider_options: next })}
            />
          </div>
        </>
      ) : null}
    </div>
  )
}
