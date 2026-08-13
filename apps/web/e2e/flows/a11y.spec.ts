import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

// Accessibility baseline — runs axe against a handful of representative
// pages (marketing + app). Baseline-mode: any WCAG A/AA violation logs
// and fails. Tune / allow-list once we see the first real report.

const PAGES = [
  "/",
  "/dashboard",
  "/workflows",
  "/theguard/policies",
]

for (const path of PAGES) {
  test(`a11y clean on ${path}`, async ({ page }) => {
    await page.goto(path)
    await page.waitForLoadState("domcontentloaded")
    // Cast: @axe-core/playwright pins a slightly older Playwright Page
    // type than we have installed; the API is identical at runtime.
    const results = await new AxeBuilder({ page: page as any })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze()
    expect(
      results.violations,
      `Accessibility violations on ${path}:\n${JSON.stringify(results.violations, null, 2)}`,
    ).toEqual([])
  })
}
