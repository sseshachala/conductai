import { test, expect } from "@playwright/test"

// Regression harness for the "Invalid workspace ID" flash we shipped a fix
// for earlier (workflows/page.tsx:110). If the useEffect fires before
// activeWorkspace hydrates, an error banner briefly appears then goes away.
// This assertion says: no such banner should ever be visible after load.
test("workflows page never shows Invalid-workspace-ID error banner", async ({ page }) => {
  await page.goto("/workflows")
  await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible({ timeout: 10_000 })

  const banner = page.getByText(/invalid workspace id/i)
  await expect(banner).toHaveCount(0)
})
