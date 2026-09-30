import { defineConfig, devices } from "@playwright/test"

for (const user of ["ADMIN", "VIEWER", "UNMAPPED"]) {
  for (const field of ["USERNAME", "PASSWORD"]) {
    if (!process.env[`CONSOLE_E2E_${user}_${field}`]) throw new Error("Dedicated console test accounts required")
  }
}
if (process.env.CONSOLE_E2E_ALLOW_MUTATION !== "1") throw new Error("Explicit local fixture mutation consent required")

export default defineConfig({
  testDir: "./e2e-console", workers: 1, fullyParallel: false, retries: 0,
  timeout: 180_000, forbidOnly: true, reporter: "list",
  use: { ...devices["Desktop Chrome"], baseURL: "https://localhost:3443",
    headless: process.env.CONSOLE_E2E_HEADED !== "1", ignoreHTTPSErrors: false,
    trace: "off", screenshot: "off", video: "off", navigationTimeout: 40_000 },
})
