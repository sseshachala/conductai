import { test } from "node:test"
import assert from "node:assert/strict"
import { prepareEnvironment } from "./prepare.mjs"

const frontend = "example-test.accounts.dev"
const fixture = () => ({
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: `pk_test_${Buffer.from(frontend + "$", "utf8").toString("base64")}`,
  CLERK_SECRET_KEY: "sk_test_fixture",
  ...Object.fromEntries(["admin", "security", "developer", "viewer"].flatMap(role =>
    [[role, "fixture-password"], [`CLERK_TEST_USER_${role.toUpperCase()}`, `user_${role}`]])),
})

test("derives the required API issuer when the optional frontend secret is absent", () => {
  const result = prepareEnvironment(fixture())
  assert.equal(result.CLERK_FRONTEND_API, frontend)
  assert.equal(result.AUTH_MODE, "clerk")
  assert.equal(result.PLAYWRIGHT_SERVER_MODE, "production")
  assert.equal(result.NEXT_PUBLIC_API_URL, "http://127.0.0.1:8000")
  assert.ok(!JSON.stringify(result).includes("fixture-password"))
  assert.ok(!JSON.stringify(result).includes("sk_test_fixture"))
})

test("validates an explicit frontend against the publishable key", () => {
  assert.doesNotThrow(() => prepareEnvironment({ ...fixture(), CLERK_FRONTEND_API: frontend }))
  assert.throws(() => prepareEnvironment({ ...fixture(), CLERK_FRONTEND_API: "other.accounts.dev" }), /does not match/)
})

test("does not silently fall back to dev authentication or omit the role matrix", () => {
  for (const name of Object.keys(fixture())) {
    const env = fixture()
    delete env[name]
    assert.throws(() => prepareEnvironment(env), /Missing web-smoke configuration/)
  }
})

test("rejects production and malformed Clerk keys without exposing their values", () => {
  for (const env of [
    { ...fixture(), CLERK_SECRET_KEY: "sk_live_do-not-print" },
    { ...fixture(), NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "invalid-do-not-print" },
    { ...fixture(), NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: `pk_live_${Buffer.from("clerk.example.com$").toString("base64")}` },
  ]) {
    assert.throws(() => prepareEnvironment(env), error => /development instance/.test(error.message) && !error.message.includes("do-not-print"))
  }
})
