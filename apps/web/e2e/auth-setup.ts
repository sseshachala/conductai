// Playwright global setup — signs in as each Clerk sandbox test user via
// @clerk/testing and saves storage state per role so the per-role project
// matrix can reuse the session without hitting Clerk on every test.

import { chromium, expect, FullConfig } from "@playwright/test"
import { clerk, clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright"
import { mkdirSync } from "fs"
import { dirname } from "path"

import { ROLE_ACCOUNTS, ROLES, storageStatePath } from "./roles"

async function dumpState(page: any, role: string, tag: string) {
  const url = page.url()
  const title = await page.title().catch(() => "?")
  const bodyText = await page.locator("body").innerText().catch(() => "?")
  const shot = `.auth/${role}-${tag}.png`
  await page.screenshot({ path: shot, fullPage: true }).catch(() => {})
  console.log(`[auth-setup:${role}:${tag}] url=${url} title=${JSON.stringify(title)}`)
  console.log(`[auth-setup:${role}:${tag}] body=${JSON.stringify(bodyText.slice(0, 400))}`)
  console.log(`[auth-setup:${role}:${tag}] screenshot=${shot}`)
}

export default async function globalSetup(config: FullConfig) {
  await clerkSetup()

  const baseURL = config.projects[0].use.baseURL || "http://localhost:3000"

  for (const role of ROLES) {
    const account = ROLE_ACCOUNTS[role]
    const outPath = storageStatePath(role)
    mkdirSync(dirname(outPath), { recursive: true })

    const browser = await chromium.launch()
    const context = await browser.newContext()
    const page = await context.newPage()

    // REQUIRED per-page — attaches the Clerk testing token to this browser
    // context so Clerk's sign-in endpoint accepts programmatic auth. Skipping
    // this call makes clerk.signIn() silently no-op (the exact bug we hit).
    await setupClerkTestingToken({ page })

    await page.goto(baseURL)
    await dumpState(page, role, "01-before-signin")

    await clerk.signIn({
      page,
      signInParams: { strategy: "password", identifier: account.email, password: account.password },
    })
    await dumpState(page, role, "02-after-signin")

    await page.goto(`${baseURL}/dashboard`)
    await page.waitForLoadState("networkidle").catch(() => {})
    await dumpState(page, role, "03-dashboard")

    try {
      await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible({ timeout: 15_000 })
      console.log(`[auth-setup:${role}] SUCCESS — heading visible`)
    } catch (err) {
      console.log(`[auth-setup:${role}] FAILURE — heading not found; snapshotting anyway so per-role tests can run and show what they see`)
    }

    await context.storageState({ path: outPath })
    await browser.close()
  }
}
