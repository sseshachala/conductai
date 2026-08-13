import { test, expect } from "@playwright/test"

// Seed row (PR-N2 in #1094): e2e-sample-workflow under DEV_WORKSPACE_ID.
// Every authenticated role should see it in /workflows.
//
// Clerk sandbox users may have been auto-added to an "Engineering"
// workspace on first sign-in (list_projects auto-creates when none
// exist). WorkspaceContext picks `data[0]` (newest) so activeWorkspace
// can land on the auto-created workspace instead of DEV. Pin the cookie
// to DEV before navigating so X-Workspace-ID matches the seed target.
const DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

test("agents list shows seeded workflow", async ({ page, context }) => {
  await context.addCookies([
    { name: "delegator_project_id", value: DEV_WORKSPACE_ID, url: "http://localhost:3000" },
  ])
  await page.goto("/workflows")
  await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("e2e-sample-workflow").first()).toBeVisible({ timeout: 10_000 })
})
