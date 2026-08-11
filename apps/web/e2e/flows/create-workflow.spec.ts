import { test, expect } from "@playwright/test"

// Golden path — /workflows → click "New agent" → land on /workflows/new.
// The bug this catches: any regression in the top-of-funnel CTA that
// stops users from creating an agent at all.
test("agents page CTA lands on new-workflow form", async ({ page }) => {
  await page.goto("/workflows")
  await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible({ timeout: 10_000 })

  await page.getByRole("link", { name: /new agent/i }).first().click()
  await expect(page).toHaveURL(/\/workflows\/new$/)
})
