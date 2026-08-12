import { test, expect } from "@playwright/test"

// Per-role RBAC assertion — the /workflows page's "+ New agent" CTA is
// gated on `platform.workflows.edit` (admin + developer only). This test
// runs once per role project; the expectation flips based on the role
// name the project supplies.

const CAN_CREATE = new Set(["admin", "developer"])

test("agents page CTA visibility matches role", async ({ page }, testInfo) => {
  const role = testInfo.project.name
  await page.goto("/workflows")

  await expect(page.getByRole("heading", { name: /agents/i })).toBeVisible({ timeout: 10_000 })

  const cta = page.getByRole("link", { name: /new agent/i }).first()
  if (CAN_CREATE.has(role)) {
    await expect(cta, `${role} should see New agent CTA`).toBeVisible()
  } else {
    await expect(cta, `${role} should not see New agent CTA`).toHaveCount(0)
  }
})
