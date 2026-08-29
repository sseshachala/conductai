import { test, expect } from "@playwright/test"

// Visual regression — one screenshot per representative page. First run
// creates the baseline; subsequent runs diff against it. Reviewer
// approves an intentional visual diff by updating the snapshot.
//
// Gated on RUN_VISUAL_REGRESSION=true because linux baselines aren't
// committed yet. Generate + commit them via:
//   .github/workflows/update-visual-snapshots.yml (workflow_dispatch)
// Then remove this gate.
const RUN = process.env.RUN_VISUAL_REGRESSION === "true"

const PAGES = [
  { path: "/", name: "home" },
  { path: "/dashboard", name: "dashboard" },
  { path: "/workflows", name: "workflows" },
  { path: "/theguard/policies", name: "policies" },
]

for (const { path, name } of PAGES) {
  test(`visual snapshot ${name}`, async ({ page }) => {
    test.skip(!RUN, "Set RUN_VISUAL_REGRESSION=true after linux baselines are committed")
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
