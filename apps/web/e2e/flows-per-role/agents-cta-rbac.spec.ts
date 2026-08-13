import { test, expect } from "@playwright/test"

// Skipped — the UI CTA gates rely on /projects/{id}/my-role + permissions
// endpoints returning role-specific data. For Clerk sandbox users these
// return admin-fallback (owner path) or 404, so real RBAC gating isn't
// exercised. Un-skip once the RBAC seed maps Clerk users to non-admin
// roles end-to-end. Tracked in follow-up.
test.skip("all cases skipped — see file header", () => {})

// Per-role RBAC assertion — the /workflows page's "+ New agent" CTA is
// gated on `platform.workflows.edit` (admin + developer only). This test
// runs once per role project; the expectation flips based on the role
// name the project supplies.

const CAN_CREATE = new Set(["admin", "developer"])

test.skip("agents page CTA visibility matches role", async ({ page }, testInfo) => {
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
