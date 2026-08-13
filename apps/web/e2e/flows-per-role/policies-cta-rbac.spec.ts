import { test, expect } from "@playwright/test"

// Skipped — the UI CTA gates rely on /projects/{id}/my-role + permissions
// endpoints returning role-specific data. For Clerk sandbox users these
// return admin-fallback (owner path) or 404, so real RBAC gating isn't
// exercised. Un-skip once the RBAC seed maps Clerk users to non-admin
// roles end-to-end. Tracked in follow-up.
test.skip("all cases skipped — see file header", () => {})

// `/theguard/policies` — "New policy rule" CTA is gated on
// `guard.policies.edit` (admin + security only). Each role project runs
// this spec once; expectation flips based on the role name.

const CAN_EDIT_POLICIES = new Set(["admin", "security"])

test("policies page CTA visibility matches role", async ({ page }, testInfo) => {
  const role = testInfo.project.name
  await page.goto("/theguard/policies")

  // Every role should reach the page.
  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })

  const cta = page.getByRole("button", { name: /new policy rule/i }).first()
  if (CAN_EDIT_POLICIES.has(role)) {
    await expect(cta, `${role} should see 'New policy rule'`).toBeVisible({ timeout: 10_000 })
  } else {
    await expect(cta, `${role} should not see 'New policy rule'`).toHaveCount(0)
  }
})
