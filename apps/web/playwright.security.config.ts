import { defineConfig, devices } from "@playwright/test"

// Deliberately separate from the dev-admin smoke suite. No automatic local
// credential-file loading and no fallback when test authentication is absent.
if (!process.env.CLERK_SECRET_KEY?.startsWith("sk_test_") ||
    !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.startsWith("pk_test_") ||
    !process.env.CLERK_FRONTEND_API?.endsWith(".accounts.dev") ||
    process.env.E2E_ALLOW_TEST_USERS !== "1") {
  throw new Error("Clerk test credentials and E2E_ALLOW_TEST_USERS=1 are required; run the local E2E preflight")
}

export default defineConfig({
  testDir: "./e2e-security",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  forbidOnly: true,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://localhost:3100",
    actionTimeout: 20_000,
    // Auth tokens and verification URLs must not become test artifacts.
    trace: "off",
    screenshot: "off",
    video: "off",
  },
})
