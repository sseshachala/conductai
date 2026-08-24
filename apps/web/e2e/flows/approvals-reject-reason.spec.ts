import { test, expect, type Page } from "@playwright/test"

// Covers the humanised-copy commit on /theguard/approvals:
//   1. Reject button is disabled until the reason input has non-empty text.
//   2. "expires in expired" is fixed — an already-expired countdown shows
//      just "expired", not the doubled phrase.
//
// We mock the API list endpoint so this doesn't need a seeded DB or a
// live Guard runtime — the intent is purely to verify frontend UX for
// the copy fix.

const FROZEN_NOW = new Date("2026-08-24T15:00:00.000Z").toISOString()
// One minute in the past — timeUntil() returns "expired".
const EXPIRED_TIMEOUT = new Date("2026-08-24T14:59:00.000Z").toISOString()
// Thirty minutes in the future — timeUntil() returns "30m".
const FUTURE_TIMEOUT = new Date("2026-08-24T15:30:00.000Z").toISOString()

const pendingApproval = (overrides: Record<string, unknown> = {}) => ({
  id: "req-mock-1",
  workspace_id: "ws-mock",
  rule_id: "hipaa_phi_export_requires_approval",
  rule_message: "PHI export requires approval",
  tool_name: "bash",
  requester_email: "alice@example.com",
  requester_user_id: "user_alice",
  surface: "claude_code",
  source_run_id: null,
  approval_type: "any_authorized",
  status: "pending",
  created_at: FROZEN_NOW,
  timeout_at: FUTURE_TIMEOUT,
  decided_at: null,
  decided_by_email: null,
  decided_by_user_id: null,
  decided_reason: null,
  latency_ms: null,
  tool_input: { command: "echo hello" },
  ...overrides,
})

async function mockApprovals(page: Page, items: unknown[]) {
  await page.route(/\/guard\/approvals(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ workspace_id: "ws-mock", items }),
    })
  })
}

test.describe("/theguard/approvals — humanised copy", () => {
  test("Reject button is disabled until reason is typed", async ({ page }) => {
    await mockApprovals(page, [pendingApproval()])
    await page.goto("/theguard/approvals")

    const rejectBtn = page.getByRole("button", { name: /^Reject$/ })
    await expect(rejectBtn).toBeVisible({ timeout: 10_000 })
    await expect(rejectBtn).toBeDisabled()

    const reasonInput = page.getByPlaceholder(/Reason \(required to reject\)/i)
    await reasonInput.fill("not authorised for prod")
    await expect(rejectBtn).toBeEnabled()

    // Clearing the reason re-disables Reject.
    await reasonInput.fill("   ")
    await expect(rejectBtn).toBeDisabled()
  })

  test("expired countdown reads 'expired' not 'expires in expired'", async ({ page }) => {
    await mockApprovals(page, [pendingApproval({ timeout_at: EXPIRED_TIMEOUT })])
    await page.goto("/theguard/approvals")

    // Should show 'expired' by itself.
    await expect(page.getByText(/^expired$/)).toBeVisible({ timeout: 10_000 })
    // Should NOT show the doubled phrase.
    await expect(page.getByText(/expires in expired/i)).toHaveCount(0)
  })
})
