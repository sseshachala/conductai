import { test, expect } from "@playwright/test"

// Seed row (PR-N2 in #1094): e2e-mcp under DEV_WORKSPACE_ID.
// Pin the workspace cookie to DEV — see agents-list spec for rationale.
const DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

test("integrations page shows seeded MCP server", async ({ page, context }) => {
  await context.addCookies([
    { name: "delegator_project_id", value: DEV_WORKSPACE_ID, url: "http://localhost:3000" },
  ])
  await page.goto("/integrations")
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText(/e2e-mcp/).first()).toBeVisible({ timeout: 10_000 })
})
