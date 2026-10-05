import { test, expect } from "@playwright/test"

test("new workflow page loads a valid default playbook", async ({ page }) => {
  const playbook = page.waitForResponse(response =>
    new URL(response.url()).pathname === "/workflows/playbooks/autopilot_full" &&
    response.request().method() === "GET",
  )
  await page.goto("/workflows/new")
  expect((await playbook).status()).toBe(200)
  await expect(page.getByRole("heading", { name: "New workflow" })).toBeVisible()
  await expect(page.getByRole("button", { name: /^Autopilot ·/ })).toBeVisible()
})
