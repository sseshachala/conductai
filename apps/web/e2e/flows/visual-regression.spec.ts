import { test, expect } from "@playwright/test"

// Visual regression — one screenshot per representative page. First run
// creates the baseline; subsequent runs diff against it. Reviewer
// approves an intentional visual diff by updating the snapshot.

const PAGES = [
  { path: "/", name: "home" },
  { path: "/dashboard", name: "dashboard" },
  { path: "/workflows", name: "workflows" },
  { path: "/theguard/policies", name: "policies" },
]

for (const { path, name } of PAGES) {
  test(`visual snapshot ${name}`, async ({ page }) => {
    await page.goto(path)
    await page.waitForLoadState("domcontentloaded")
    // Give animations a beat to settle.
    await page.waitForTimeout(500)
    await expect(page).toHaveScreenshot(`${name}.png`, {
      fullPage: true,
      // 0.5% pixel-diff tolerance — pixel-perfect is too flaky in CI.
      maxDiffPixelRatio: 0.005,
    })
  })
}
