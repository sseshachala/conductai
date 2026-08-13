import { test, expect } from "@playwright/test"

// Skipped — the UI CTA gates rely on /projects/{id}/my-role + permissions
// endpoints returning role-specific data. For Clerk sandbox users these
// return admin-fallback (owner path) or 404, so real RBAC gating isn't
// exercised. Un-skip once the RBAC seed maps Clerk users to non-admin
// roles end-to-end. Tracked in follow-up.
test.skip("all cases skipped — see file header", () => {})

// `/agent-identity` — "+ Create token" CTA is admin-only. Non-admin roles
// see the identities table read-only. Complements the platform.members.manage
// gate on the invite endpoint.

const CAN_CREATE_TOKEN = new Set(["admin"])

test.skip("agent-identity page 'Create token' visibility matches role", async ({ page }, testInfo) => {
  const role = testInfo.project.name
  await page.goto("/agent-identity")

  await expect(page.locator("main, [role=main], body").first()).toBeVisible({ timeout: 10_000 })

  const cta = page.getByRole("button", { name: /create token/i }).first()
  if (CAN_CREATE_TOKEN.has(role)) {
    await expect(cta, `${role} should see 'Create token'`).toBeVisible({ timeout: 10_000 })
  } else {
    await expect(cta, `${role} should not see 'Create token'`).toHaveCount(0)
  }
})
