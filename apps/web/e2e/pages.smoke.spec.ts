import { test, expect, Page, ConsoleMessage } from "@playwright/test"
import { discoverRoutes } from "./routes"

/**
 * Every-page smoke.
 *
 * For each static page.tsx under src/app:
 *   - HTTP status is successful
 *   - Protected pages use a real Clerk session when Clerk is configured
 *   - API authentication and server errors fail the test
 *   - No uncaught page errors
 *   - No console `error`-level messages (except the allow-list below)
 *   - A `main` landmark renders within the timeout
 *
 * Dynamic fake-ID routes belong in focused flows with seeded records; sweeping
 * them here only proves that a not-found page can render.
 */

// Warnings we tolerate because they come from third-party bundles or dev-mode
// noise, not our own code. Add sparingly and comment WHY.
const CONSOLE_IGNORE = [
  /Download the React DevTools/,
  /webpack-hmr/i,
  /\[HMR\]/,
  /Refused to load the image/i,         // strict CSP in dev
  /Warning: .*validateDOMNesting/,      // pre-existing markup nits, tracked separately
]

const routes = discoverRoutes().filter(route => !route.isDynamic)

function collect(page: Page): { errors: string[]; pageErrors: string[]; apiErrors: string[] } {
  const errors: string[] = []
  const pageErrors: string[] = []
  const apiErrors: string[] = []
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() !== "error") return
    const text = msg.text()
    if (CONSOLE_IGNORE.some(re => re.test(text))) return
    errors.push(text)
  })
  page.on("pageerror", (err: Error) => pageErrors.push(err.message))
  page.on("requestfailed", request => {
    if (["fetch", "xhr"].includes(request.resourceType())) {
      apiErrors.push(`${request.method()} ${request.url()} failed: ${request.failure()?.errorText ?? "unknown error"}`)
    }
  })
  page.on("response", response => {
    if (!["fetch", "xhr"].includes(response.request().resourceType())) return
    if ([401, 403].includes(response.status()) || response.status() >= 500) {
      apiErrors.push(`${response.request().method()} ${response.url()} returned ${response.status()}`)
    }
  })
  return { errors, pageErrors, apiErrors }
}

for (const route of routes) {
  test(`smoke ${route.url}  (${route.file})`, async ({ page }) => {
    const { errors, pageErrors, apiErrors } = collect(page)

    const response = await page.goto(route.url, { waitUntil: "domcontentloaded" })
    const status = response?.status() ?? 0

    expect(status, `${route.url} returned ${status}`).toBeGreaterThanOrEqual(200)
    expect(status, `${route.url} returned ${status}`).toBeLessThan(400)
    expect(new URL(page.url()).pathname, `${route.url} redirected to sign-in`).not.toMatch(/^\/sign-in(?:\/|$)/)

    await expect(page.locator("main, [role=main]").first()).toBeVisible({ timeout: 8_000 })

    expect(pageErrors, `page errors on ${route.url}`).toEqual([])
    expect(errors, `console errors on ${route.url}`).toEqual([])
    expect(apiErrors, `API/network errors on ${route.url}`).toEqual([])
  })
}
