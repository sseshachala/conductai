import { test, expect } from "@playwright/test"

// Guard section is a whole app-within-an-app. If /theguard SSR breaks or the
// left-nav Policies link points somewhere wrong, this fails loudly.
test("guard section navigates to policies", async ({ page }) => {
  await page.goto("/theguard")

  const policies = page.getByRole("link", { name: /policies/i }).first()
  await expect(policies).toBeVisible({ timeout: 10_000 })
  await policies.click()

  await expect(page).toHaveURL(/\/theguard\/policies(\/.*)?$/)
})
