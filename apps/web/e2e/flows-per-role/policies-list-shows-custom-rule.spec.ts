import { test, expect } from "@playwright/test"

// Seed row (PR-N2 in #1094): custom rule e2e-block-rm-rf.
// Pin the workspace cookie to DEV_WORKSPACE_ID — see agents-list spec
// for the rationale.
const DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

test("policies list shows seeded custom rule", async ({ page, context }) => {
  await context.addCookies([
    { name: "delegator_project_id", value: DEV_WORKSPACE_ID, url: "http://localhost:3000" },
  ])
  await page.goto("/theguard/policies")
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText(/e2e-block-rm-rf/).first()).toBeVisible({ timeout: 10_000 })
})
