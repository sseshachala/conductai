// Playwright global setup — signs in as each Clerk sandbox test user via
// @clerk/testing and saves storage state per role so the per-role project
// matrix can reuse the session without hitting Clerk on every test.
//
// Requires the sandbox Clerk keys in env (loaded from .env.test locally or
// injected from GitHub secrets in CI):
//   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
//   CLERK_SECRET_KEY

import { chromium, expect, FullConfig } from "@playwright/test"
import { clerk, clerkSetup } from "@clerk/testing/playwright"
import { mkdirSync } from "fs"
import { dirname } from "path"

import { ROLE_ACCOUNTS, ROLES, storageStatePath } from "./roles"

export default async function globalSetup(config: FullConfig) {
  // Fetch a testing token — one call primes @clerk/testing for the whole
  // suite (no rate-limits, no browser CAPTCHAs).
  await clerkSetup()

  const baseURL = config.projects[0].use.baseURL || "http://127.0.0.1:3000"

  for (const role of ROLES) {
    const account = ROLE_ACCOUNTS[role]
    const outPath = storageStatePath(role)
    mkdirSync(dirname(outPath), { recursive: true })

    const browser = await chromium.launch()
    const context = await browser.newContext()
    const page = await context.newPage()

    await page.goto(baseURL)
    await clerk.signIn({
      page,
      signInParams: { strategy: "password", identifier: account.email, password: account.password },
    })

    // Land on an authenticated route so Clerk finishes setting the session
    // cookie before we snapshot storage.
    await page.goto(`${baseURL}/dashboard`)
    await expect(page.locator("body")).toBeVisible()

    await context.storageState({ path: outPath })
    await browser.close()

    console.log(`[auth-setup] signed in ${role} → ${outPath}`)
  }
}
