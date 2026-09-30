import { describe, expect, it } from "vitest"
import { deploymentConfig, serializeRuntime } from "./runtime"

describe("runtime deployment configuration", () => {
  it("defaults to Clerk, never implicit development", () => {
    expect(deploymentConfig({}).authMode).toBe("clerk")
    expect(() => deploymentConfig({ AUTH_MODE: "development" })).toThrow()
    expect(() => deploymentConfig({ AUTH_MODE: "anything" })).toThrow()
    expect(deploymentConfig({ AUTH_MODE: "development", ENVIRONMENT: "local" }).authMode).toBe("development")
  })
  it("uses runtime URLs without exposing server secrets or Clerk configuration in proxy mode", () => {
    const config = deploymentConfig({ AUTH_MODE: "proxy", API_URL: "http://private-api:8000",
      API_BASE_URL: "https://api.customer.test", CONSOLE_PROXY_SECRET: "not-public",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "unused-key", OIDC_CLIENT_SECRET: "not-public" })
    expect(config).toEqual({ authMode: "proxy", apiUrl: "/api/backend",
      publicApiUrl: "https://api.customer.test", clerkPublishableKey: "" })
    expect(JSON.stringify(config)).not.toContain("not-public")
    expect(JSON.stringify(config)).not.toContain("private-api")
  })
  it("supports different URL configurations from the same code", () => {
    for (const host of ["first.test", "second.test"]) {
      expect(deploymentConfig({ NEXT_PUBLIC_API_URL: `https://${host}` }).apiUrl).toBe(`https://${host}`)
    }
  })
  it("escapes markup in the serialized runtime document", () => {
    const encoded = serializeRuntime(deploymentConfig({ API_BASE_URL: "</script><script>" }))
    expect(encoded).not.toContain("<")
    expect(JSON.parse(encoded).publicApiUrl).toBe("</script><script>")
  })
})
