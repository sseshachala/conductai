import { test, expect } from "@playwright/test"

// Seed row (PR-N2 in #1094): custom rule e2e-block-rm-rf.
// All roles have guard.policies.view so the rule renders for everyone;
// only admin+security can edit (that's the CTA-visibility spec).
test("policies list shows seeded custom rule", async ({ page }) => {
  await page.goto("/theguard/policies")
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText(/e2e-block-rm-rf/).first()).toBeVisible({ timeout: 10_000 })
})
