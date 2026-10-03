import { expect, it } from "vitest"
import { certifiedOperations, validateTargetsAgainstAccepts } from "./gatewayCapabilityCatalog"

it("permits SDK translation without advertising it for native HTTPS", () => {
  expect(certifiedOperations({ transport: "litellm_sdk", provider: "anthropic" }).has("openai_chat_completions")).toBe(true)
  expect(certifiedOperations({ transport: "litellm_sdk", provider: "openai" }).has("anthropic_messages")).toBe(true)
  expect(certifiedOperations({ transport: "native_http", provider: "anthropic" }).has("openai_chat_completions")).toBe(false)
  expect(certifiedOperations({ transport: "native_http", provider: "openai" }).has("anthropic_messages")).toBe(false)
})

it("accepts the common operations of a mixed SDK fallback profile", () => {
  expect(validateTargetsAgainstAccepts({ accepts: ["anthropic_messages", "openai_chat_completions"], targets: [
    { id: "primary", transport: "litellm_sdk", provider: "anthropic" },
    { id: "fallback", transport: "litellm_sdk", provider: "openai" },
  ] })).toEqual([])
})

it("requires a custom protocol and limits operations to that protocol", () => {
  expect([...certifiedOperations({ transport: "http_passthrough", integration: "custom" })]).toEqual([])
  expect([...certifiedOperations({ transport: "http_passthrough", integration: "custom", provider_options: { protocol: "openai" } })])
    .toEqual(["openai_chat_completions", "openai_responses"])
  expect([...certifiedOperations({ transport: "http_passthrough", integration: "custom", provider_options: { protocol: "anthropic" } })])
    .toEqual(["anthropic_messages", "anthropic_count_tokens"])
})
