import { test, expect } from "@playwright/test"

// Every role should be able to open /dashboard (guarded by
// platform.workflows.view which viewer + up all have). Catches the flip
// side of the RBAC harness: not just "unauthorised gets 403" but
// "authorised roles all still work".
test("dashboard loads regardless of role", async ({ page }) => {
  await page.goto("/dashboard")
  await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible({ timeout: 10_000 })
})
