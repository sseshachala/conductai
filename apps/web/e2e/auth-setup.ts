// Playwright global setup — signs in as each Clerk sandbox test user via
// the ACTUAL Clerk sign-in form on our app (SDK-bypass approach kept
// silently no-op'ing). Saves storage state per role so the per-role
// project matrix can reuse the session without hitting Clerk on every
// test.

import { chromium, expect, FullConfig } from "@playwright/test"
import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright"
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

    await setupClerkTestingToken({ page })

    // Go straight to the Clerk-mounted sign-in page and drive the real form.
    // The SDK bypass (`clerk.signIn`) silently failed for our setup —
    // form-based is closer to how a real user signs in and is the pattern
    // @clerk/testing docs recommend when SDK bypass misbehaves.
    await page.goto(`${baseURL}/sign-in`)
    await dumpState(page, role, "01-signin-page")

    // Clerk's ClerkJS component uses <input name=identifier> then transitions
    // to <input name=password>. Field labels are stable across versions.
    await page.getByLabel(/email address/i).fill(account.email)
    // { exact: true } dodges the "Sign in with Google Continue" OAuth button.
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    // getByLabel(/password/i) also matches the "Show password" toggle button.
    // Pin to the actual input.
    await page.locator('input[name="password"]').fill(account.password)
    // { exact: true } dodges the "Sign in with Google Continue" OAuth button.
    await page.getByRole("button", { name: "Continue", exact: true }).click()

    // App should redirect us past /sign-in after successful auth.
    await page.waitForURL(url => !/\/sign-in/.test(url.pathname), { timeout: 20_000 }).catch(() => {})
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
