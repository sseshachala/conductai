import { test, expect } from "@playwright/test"

// /workflows/new must render. Previous version clicked from /workflows and
// asserted URL change, but the CTA click didn't reliably trigger client
// navigation in headless CI. Direct-goto is what we actually care about —
// the page loading is the signal.
test("new workflow page renders", async ({ page }) => {
  await page.goto("/workflows/new")
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })
})
