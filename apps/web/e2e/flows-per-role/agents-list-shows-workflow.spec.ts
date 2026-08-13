import { test, expect } from "@playwright/test"

// Seed row (PR-N2 in #1094): e2e-sample-workflow under DEV_WORKSPACE_ID.
// Every authenticated role should see it in /workflows — reads are open
// to anyone with platform.workflows.view (all 4 roles have it).
test("agents list shows seeded workflow", async ({ page }) => {
  await page.goto("/workflows")
  await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("e2e-sample-workflow").first()).toBeVisible({ timeout: 10_000 })
})
