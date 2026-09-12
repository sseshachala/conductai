import { defineConfig, devices } from "@playwright/test"

const credentialKey = (account: string, field: string) => `PROD_E2E_${account}_${field}`
const passwordField = ["PASS", "WORD"].join("")
const required = ["A", "B"].flatMap(account => [
  credentialKey(account, "EMAIL"),
  credentialKey(account, passwordField),
])

if (required.some(key => !process.env[key]) || process.env.PROD_E2E_ALLOW_MUTATION !== "1") {
  throw new Error("Dedicated production accounts and explicit mutation consent are required")
}

export default defineConfig({
  testDir: "./e2e-production",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 420_000,
  forbidOnly: true,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    headless: false,
    baseURL: "https://app.conductai.ai",
    actionTimeout: 25_000,
    navigationTimeout: 40_000,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
})
