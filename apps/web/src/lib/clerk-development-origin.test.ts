import { describe, expect, it } from "vitest"
import { clerkDevelopmentOrigin } from "./clerk-development-origin"

describe("Clerk development CSP origin", () => {
  const key = (host: string) => `pk_test_${btoa(host + "$")}`
  it("permits exactly the configured Clerk development host", () => {
    expect(clerkDevelopmentOrigin(key("synthetic.clerk.accounts.dev"))).toBe("https://synthetic.clerk.accounts.dev")
  })
  it("does not change production-key behavior", () => {
    expect(clerkDevelopmentOrigin("pk_live_" + btoa("clerk.example.com$"))).toBe("")
  })
  it.each(["", "pk_test_invalid!", key("attacker.example"), key("test.clerk.accounts.dev; script-src *"), key("test.clerk.accounts.dev/evil")])("rejects malformed or unrelated origins", candidate => {
    expect(clerkDevelopmentOrigin(candidate)).toBe("")
  })
})
