import { test, expect } from "@playwright/test"

// Deep smoke — dashboard shell renders with its title landmark.
// Runs as backend dev-mode admin, seeded workspace exists.
test("dashboard loads and shows title", async ({ page }) => {
  await page.goto("/dashboard")
  await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible({ timeout: 10_000 })
})
