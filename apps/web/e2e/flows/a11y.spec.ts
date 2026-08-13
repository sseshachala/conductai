import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

// Accessibility baseline — runs axe against a handful of representative
// pages (marketing + app). Known UX debt is allow-listed as a set of rule
// IDs; anything outside that set fails the run.
//
// Remove entries from KNOWN_UX_DEBT as UX ships fixes. Do NOT add without
// filing a follow-up issue and citing it here.

const PAGES = [
  "/",
  "/dashboard",
  "/workflows",
  "/theguard/policies",
]

// Rule IDs graded as known UX debt (tracked separately, not gating here).
// color-contrast: --text-muted (#a8a29e) hits 2.3–2.5:1 on the sidebar
// section headings, ⌘K kbd, and status pills. Global palette change —
// bundle with the next UX pass rather than piecemeal.
const KNOWN_UX_DEBT = new Set<string>([
  "color-contrast",
])

for (const path of PAGES) {
  test(`a11y clean on ${path}`, async ({ page }) => {
    await page.goto(path)
    await page.waitForLoadState("domcontentloaded")
    // Cast: @axe-core/playwright pins a slightly older Playwright Page
    // type than we have installed; the API is identical at runtime.
    const results = await new AxeBuilder({ page: page as any })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze()
    const gating = results.violations.filter((v) => !KNOWN_UX_DEBT.has(v.id))
    expect(
      gating,
      `New accessibility violations on ${path} (outside KNOWN_UX_DEBT):\n${JSON.stringify(gating, null, 2)}`,
    ).toEqual([])
  })
}
