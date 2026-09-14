import { test, expect } from "@playwright/test"

// `/theguard/policies` — "Add rule" CTA is gated on
// `guard.policies.edit` (admin + security only). Each role project runs
// this spec once; expectation flips based on the role name.

const CAN_EDIT_POLICIES = new Set(["admin", "security"])

test("policies page CTA visibility matches role", async ({ page }, testInfo) => {
  const role = testInfo.project.name
  await page.goto("/theguard/policies")

  await expect(page.getByText(/Rules sync to every developer/)).toBeVisible({ timeout: 10_000 })

  const cta = page.getByRole("button", { name: /add rule/i }).first()
  if (CAN_EDIT_POLICIES.has(role)) {
    await expect(cta, `${role} should see 'Add rule'`).toBeVisible({ timeout: 10_000 })
  } else {
    await expect(cta, `${role} should not see 'Add rule'`).toHaveCount(0)
  }
})
