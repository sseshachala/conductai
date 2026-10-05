import { describe, expect, it } from "vitest"
import { apiSecurityOrigin, isLocalHttpOrigin } from "../api-security-origin"

describe("API CSP origins", () => {
  it("retains explicitly configured HTTPS origins in SaaS and on-prem", () => {
    expect(apiSecurityOrigin("https://api.conductai.ai", "production")).toBe("https://api.conductai.ai")
    expect(apiSecurityOrigin("https://api.company.example/api", "production")).toBe("https://api.company.example")
    expect(apiSecurityOrigin("/api/backend", "production")).toBe("")
  })

  it("allows HTTP only for explicit loopback URLs in local environments", () => {
    for (const host of ["localhost", "127.0.0.1", "[::1]"]) {
      const url = `http://${host}:8000`
      expect(apiSecurityOrigin(url, "local")).toBe(url)
      expect(apiSecurityOrigin(url, "development")).toBe(url)
      expect(apiSecurityOrigin(url, "production")).toBe("")
      expect(apiSecurityOrigin(url)).toBe("")
    }
    expect(apiSecurityOrigin("http://api.company.example", "development")).toBe("")
    expect(apiSecurityOrigin("http://localhost.attacker.example", "local")).toBe("")
    expect(apiSecurityOrigin("https://user:password@api.example", "local")).toBe("")
  })

  it("omits HTTPS upgrading only for an HTTP loopback page in an explicit local environment", () => {
    expect(isLocalHttpOrigin("http://localhost:3000/dashboard", "local")).toBe(true)
    expect(isLocalHttpOrigin("https://localhost:3443/dashboard", "local")).toBe(false)
    expect(isLocalHttpOrigin("http://app.conductai.ai/dashboard", "local")).toBe(false)
    expect(isLocalHttpOrigin("http://localhost:3000/dashboard", "production")).toBe(false)
  })
})
