import { describe, expect, it } from "vitest"
import { restorationPlan } from "../../../e2e-production/gateway-fixture"

function reader(credentials: unknown[]) {
  return async (path: string): Promise<unknown> => {
    if (path.endsWith("gateway-profiles-v2")) return []
    if (path === "/environments") return [{ id: "environment" }]
    if (path.startsWith("/credentials/by-environment/")) return credentials
    throw new Error("Unexpected metadata endpoint")
  }
}

describe("dedicated Gateway fixture restoration", () => {
  const credential = { service: "anthropic", handle: "anthropic", fields: ["api_key"] }
  it("reuses metadata without reading provider secrets", async () => {
    const plan = await restorationPlan(reader([credential]), "workspace", "anthropic", "claude-test")
    expect(plan?.working_copy.targets[0]).toMatchObject({ model: "claude-test", credential_ref: "vault://environment/anthropic" })
  })
  it("rejects missing credentials", async () => {
    await expect(restorationPlan(reader([]), "workspace", "anthropic")).rejects.toThrow("credentials=0")
  })
  it("rejects ambiguous credentials", async () => {
    await expect(restorationPlan(reader([credential, credential]), "workspace", "anthropic")).rejects.toThrow("credentials=2")
  })
  it("requires an explicit model when creating a fixture", async () => {
    await expect(restorationPlan(reader([credential]), "workspace", "anthropic")).rejects.toThrow("models=0")
  })
  it("accepts an explicitly selected model without legacy model settings", async () => {
    const plan = await restorationPlan(reader([credential]), "workspace", "anthropic", "claude-test")
    expect(plan?.working_copy.targets[0].model).toBe("claude-test")
  })
  it("rejects model URLs", async () => {
    await expect(restorationPlan(reader([credential]), "workspace", "anthropic", "https://example.invalid")).rejects.toThrow("plain upstream model ID")
  })
})
