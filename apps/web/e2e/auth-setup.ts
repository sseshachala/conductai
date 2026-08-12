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

    // Sign in on the app origin (not on Clerk's hosted UI) so cookies land
    // on 127.0.0.1:3000 and survive storage snapshot.
    await page.goto(`${baseURL}/sign-in`)
    await clerk.signIn({
      page,
      signInParams: { strategy: "password", identifier: account.email, password: account.password },
    })

    // Wait for the app to redirect us past the sign-in page. If the session
    // cookie didn't land, we stay on /sign-in and this timeout catches it
    // — much clearer failure than "no dashboard heading" downstream.
    await page.waitForURL(url => !/\/sign-in/.test(url.pathname), { timeout: 15_000 })

    // Land on an authenticated route so Clerk finishes hydrating.
    await page.goto(`${baseURL}/dashboard`)
    await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible({ timeout: 15_000 })

    await context.storageState({ path: outPath })
    await browser.close()

    console.log(`[auth-setup] signed in ${role} → ${outPath}`)
  }
}
