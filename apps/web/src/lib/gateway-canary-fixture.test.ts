import { describe, expect, it, vi } from "vitest"
import { legacyCatalogModels, publishedGatewayFixture } from "../../e2e-production/gateway-fixture"

const profile = { id: "p1", cond_code: "abcdefgh", active_revision_id: "r1", working_copy: { model_alias: "draft" } }
const snapshot = {
  model_alias: "claude-canary",
  accepts: ["anthropic_messages", "anthropic_count_tokens"],
  targets: [{ transport: "native_http", provider: "anthropic", model: "claude-test", credential_ref: "vault://env/key" }],
}
function reader(profiles = [profile], revision = snapshot) {
  return vi.fn(async (path: string) => path.endsWith("gateway-profiles-v2") ? profiles : revision)
}

describe("production Gateway fixture", () => {
  it("uses the active revision, not the working copy or upstream model", async () => {
    const read = reader()
    expect(await publishedGatewayFixture(read, "ws", "anthropic")).toEqual({ model: "cond-abcdefgh-claude-canary", revisionId: "r1", condCode: "abcdefgh" })
    expect(read).toHaveBeenCalledWith("/workspaces/ws/gateway-profiles-v2/p1/revisions/r1")
  })
  it("rejects missing and draft-only fixtures", async () => {
    await expect(publishedGatewayFixture(reader([]), "ws", "anthropic")).rejects.toThrow("found 0")
    const read = reader([{ ...profile, active_revision_id: null! }])
    await expect(publishedGatewayFixture(read, "ws", "anthropic")).rejects.toThrow("found 0")
    expect(read).toHaveBeenCalledTimes(1)
  })
  it("rejects ambiguous profiles unless explicitly selected", async () => {
    const read = reader([profile, { ...profile, id: "p2", cond_code: "ijklmnop" }])
    await expect(publishedGatewayFixture(read, "ws", "anthropic")).rejects.toThrow("found 2")
    expect((await publishedGatewayFixture(read, "ws", "anthropic", "cond-ijklmnop-claude-canary")).condCode).toBe("ijklmnop")
    await expect(publishedGatewayFixture(read, "ws", "anthropic", "cond-missing1-nope")).rejects.toThrow("found 0")
  })
  it("requires all tested operations", async () => {
    await expect(publishedGatewayFixture(reader([profile], { ...snapshot, accepts: ["anthropic_messages"] }), "ws", "anthropic")).rejects.toThrow("found 0")
  })
  it.each([
    { ...snapshot.targets[0], provider: "openai" },
    { ...snapshot.targets[0], transport: "http_passthrough" },
    { ...snapshot.targets[0], credential_ref: "not-a-vault-ref" },
  ])("rejects incompatible or uncredentialed targets", async target => {
    await expect(publishedGatewayFixture(reader([profile], { ...snapshot, targets: [snapshot.targets[0], target] }), "ws", "anthropic")).rejects.toThrow("found 0")
  })
  it("supports OpenAI Responses via LiteLLM", async () => {
    const read = reader([profile], { ...snapshot, accepts: ["openai_responses"], targets: [{ ...snapshot.targets[0], transport: "litellm_sdk", provider: "openai" }] })
    expect((await publishedGatewayFixture(read, "ws", "openai")).revisionId).toBe("r1")
  })
})

describe("legacy model discovery contract", () => {
  const legacy = { id: "v1", environment_id: null, provider: "anthropic", deployments: [{ model: "anthropic/claude-test" }, { model: "claude-test" }] }
  it("does not advertise synthetic or environment-scoped defaults", () => {
    expect(legacyCatalogModels([{ ...legacy, id: null }, { ...legacy, environment_id: "env" }])).toEqual([])
  })
  it("filters by provider and strips internal prefixes before deduplicating", () => {
    expect(legacyCatalogModels([{ ...legacy, provider: "openai" }, legacy])).toEqual(["claude-test"])
  })
})
