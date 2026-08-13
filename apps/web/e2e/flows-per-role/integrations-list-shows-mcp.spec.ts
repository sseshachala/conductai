import { test, expect } from "@playwright/test"

// Seed row (PR-N2 in #1094): e2e-mcp under DEV_WORKSPACE_ID.
// /integrations reads platform.workflows.view (available to all roles);
// the row should appear for every authenticated user.
test("integrations page shows seeded MCP server", async ({ page }) => {
  await page.goto("/integrations")
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText(/e2e-mcp/).first()).toBeVisible({ timeout: 10_000 })
})
