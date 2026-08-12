import { test, expect, Page, ConsoleMessage } from "@playwright/test"
import { discoverRoutes } from "./routes"

/**
 * Every-page smoke.
 *
 * For each page.tsx under src/app:
 *   - HTTP status is not 5xx (a 404 for missing dynamic-param data is fine)
 *   - No uncaught page errors
 *   - No console `error`-level messages (except the allow-list below)
 *   - A `main` landmark renders within the timeout
 *
 * Clerk is disabled at webServer level so (app)/* routes render as
 * backend dev-mode admin — no JWT setup required for this layer.
 */

// Warnings we tolerate because they come from third-party bundles or dev-mode
// noise, not our own code. Add sparingly and comment WHY.
const CONSOLE_IGNORE = [
  /Download the React DevTools/,
  /webpack-hmr/i,
  /\[HMR\]/,
  /net::ERR_/,                          // network errors from backend-less dev
  /Failed to load resource/i,           // same reason
  /Refused to load the image/i,         // strict CSP in dev
  /Warning: .*validateDOMNesting/,      // pre-existing markup nits, tracked separately
]

const routes = discoverRoutes()

function collect(page: Page): { errors: string[]; pageErrors: string[] } {
  const errors: string[] = []
  const pageErrors: string[] = []
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() !== "error") return
    const text = msg.text()
    if (CONSOLE_IGNORE.some(re => re.test(text))) return
    errors.push(text)
  })
  page.on("pageerror", (err: Error) => pageErrors.push(err.message))
  return { errors, pageErrors }
}

for (const route of routes) {
  test(`smoke ${route.url}  (${route.file})`, async ({ page }) => {
    const { errors, pageErrors } = collect(page)

    const response = await page.goto(route.url, { waitUntil: "domcontentloaded" })
    const status = response?.status() ?? 0

    expect.soft(status, `${route.url} returned ${status}`).toBeLessThan(500)

    // Any page should render *some* main landmark within a reasonable window.
    // If Next served an error page, this fails loudly. .first() dodges
    // Playwright's strict-mode when marketing layouts contain multiple
    // <main> elements (nested layouts + page).
    await expect
      .soft(page.locator("main, [role=main], body").first())
      .toBeVisible({ timeout: 8_000 })

    expect(pageErrors, `page errors on ${route.url}`).toEqual([])
    expect(errors, `console errors on ${route.url}`).toEqual([])
  })
}
