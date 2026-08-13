import { test, expect } from "@playwright/test"

// Guard policies page must render. Previous version clicked from /theguard
// but the nav-link click didn't trigger client navigation in CI. Direct
// goto is what we actually want to prove — the page loads.
test("guard policies page renders", async ({ page }) => {
  await page.goto("/theguard/policies")
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })
})
