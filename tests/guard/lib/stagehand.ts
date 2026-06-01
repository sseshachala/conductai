/**
 * Shared Stagehand browser factory.
 *
 * Creates a LOCAL (headless Chromium) Stagehand instance backed by Claude claude-sonnet-4-6.
 * Requires ANTHROPIC_API_KEY in the environment.
 *
 * Usage:
 *   const { stagehand, page } = await createBrowser()
 *   // ... run test steps ...
 *   await stagehand.close()
 */

import { Stagehand } from "@browserbasehq/stagehand"

export interface BrowserHandle {
  stagehand: Stagehand
  page: Awaited<ReturnType<Stagehand["page"]["goto"]>> extends infer _ ? Stagehand["page"] : never
}

/**
 * Creates and initialises a Stagehand browser instance.
 *
 * @param headless  Run without a visible window (default: true).
 *                  Set to false when debugging to watch the browser.
 */
export async function createBrowser(headless = true): Promise<BrowserHandle> {
  const apiKey = process.env.ANTHROPIC_API_KEY
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY is not set in the environment")

  const stagehand = new Stagehand({
    env: "LOCAL",
    headless,
    modelName: "claude-sonnet-4-6",
    modelClientOptions: {
      apiKey,
    },
    verbose: 1,
  })

  await stagehand.init()

  return {
    stagehand,
    page: stagehand.page,
  }
}

/**
 * Waits for navigation to settle after an action that triggers a redirect.
 * Polls the current URL at 250 ms intervals until it has changed from
 * the supplied startUrl, or until the timeout expires.
 */
export async function waitForUrlChange(
  page: BrowserHandle["page"],
  startUrl: string,
  timeoutMs = 8_000
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const current = page.url()
    if (current !== startUrl && !current.endsWith(startUrl)) return current
    await new Promise((r) => setTimeout(r, 250))
  }
  return page.url()
}

/**
 * Takes a screenshot and saves it to the given path.
 * Creates parent directories as needed.
 * Returns the saved path.
 */
export async function screenshot(
  page: BrowserHandle["page"],
  outputPath: string
): Promise<string> {
  const { mkdirSync } = await import("fs")
  const { dirname } = await import("path")
  mkdirSync(dirname(outputPath), { recursive: true })
  await page.screenshot({ path: outputPath, fullPage: false })
  return outputPath
}

/**
 * Performs a Clerk username/password sign-in via the hosted sign-in UI.
 *
 * Flow:
 *   1. Navigate to CONDUCT_APP_URL/sign-in
 *   2. Fill in the email identifier and click Continue
 *   3. Fill in the password and click Continue
 *   4. Wait for redirect away from /sign-in
 *
 * Returns the URL the browser landed on after sign-in.
 */
export async function signInWithPassword(
  page: BrowserHandle["page"],
  email: string,
  password: string,
  appUrl: string
): Promise<string> {
  const signInUrl = `${appUrl.replace(/\/$/, "")}/sign-in`
  await page.goto(signInUrl)

  // Stagehand AI acts on the Clerk sign-in form
  await page.act(`Type "${email}" into the email or username field and click Continue`)
  await page.act(`Type "${password}" into the password field and click Continue`)

  // Wait for Clerk to redirect us away from /sign-in
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    const url = page.url()
    if (!url.includes("/sign-in")) return url
    await new Promise((r) => setTimeout(r, 300))
  }

  return page.url()
}
