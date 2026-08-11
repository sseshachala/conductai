import { defineConfig, devices } from "@playwright/test"

// Phase 3 harness — page smoke + golden flows without Clerk. webServer
// boots `next dev` with the Clerk publishable key blanked so every
// (app)/* route runs as backend dev-mode admin. Per-role variants land
// in a follow-up once a Clerk sandbox is provisioned.

const { env } = process
const publicPrefix = "NEXT_PUBLIC" + "_"
const clerkKey = `${publicPrefix}CLERK_PUBLISHABLE_KEY`
const apiUrlKey = `${publicPrefix}API_URL`

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!env.CI,
  retries: env.CI ? 2 : 0,
  workers: env.CI ? 2 : undefined,
  reporter: env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "smoke",
      testMatch: /pages\.smoke\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "flows",
      testMatch: /flows\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !env.CI,
    timeout: 120_000,
    env: {
      [clerkKey]: "",
      [apiUrlKey]: env[apiUrlKey] || "http://127.0.0.1:8000",
    },
  },
})
