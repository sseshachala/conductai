import { test, expect } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname
    let json: unknown = []
    if (path === "/api/projects") json = [{ id: "11111111-1111-4111-8111-111111111111", name: "Preview workspace", owner_id: "preview", is_approved: true }]
    else if (path.endsWith("/my-role")) json = { role: "admin" }
    else if (path.endsWith("/installed")) json = { installed: true }
    else if (path.endsWith("/permissions")) json = { role: "admin", permissions: [] }
    else if (path.endsWith("/agent-identities")) json = [{ id: "agent-preview", name: "Coding tools", source: "conduct_cli", provider: "conduct", recorded_session_count: 1, created_at: "2026-09-14T12:00:00Z" }]
    else if (path.endsWith("/activity-sessions")) json = { sessions: [{ session_id: "session-preview", tools: ["codex-desktop"], first_seen: "2026-09-14T12:00:00Z", last_seen: "2026-09-14T13:00:00Z", event_count: 12, warned_count: 2, blocked_count: 0 }], has_more: false }
    await route.fulfill({ json })
  })
})

for (const width of [320, 390, 768, 1440]) {
  test(`shell stays within ${width}px with a wide activity table`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto("/agent-identity?tab=agent_sessions")
    await expect(page.getByRole("link", { name: "session-" })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width < 768) {
      await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible()
      const table = page.getByRole("region", { name: "Recorded activity sessions" }).locator("table")
      expect(await table.evaluate(el => el.parentElement!.scrollWidth > el.parentElement!.clientWidth)).toBe(true)
    }
    await page.screenshot({ path: test.info().outputPath(`shell-${width}.png`), fullPage: true })
  })
}

test("mobile navigation opens as an overlay and restores keyboard access", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/agent-identity?tab=agent_sessions")
  await page.getByRole("button", { name: "Expand sidebar" }).click()
  const navigation = page.getByRole("dialog", { name: "Main navigation" })
  await expect(navigation).toBeVisible()
  await expect(navigation).toHaveAttribute("aria-modal", "true")
  expect(await page.locator("main").evaluate(el => !!el.closest("[inert]"))).toBe(true)
  await page.keyboard.press("Escape")
  await expect(navigation).not.toBeVisible()
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeFocused()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole("button", { name: "Command palette", exact: true }).click()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.keyboard.press("Escape")
  await page.getByRole("button", { name: "Ask Lens", exact: true }).click()
  await expect(page.getByRole("complementary", { name: "Ask Lens panel" })).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
