import { test, expect } from "@playwright/test"

// Identities page recently had a hydration-mismatch fix (#1066/#1067).
// This anchors a regression: page must load and show its main landmark
// without the SSR/CSR hydration blowing up.
test("agent-identity page renders without hydration errors", async ({ page }) => {
  const pageErrors: string[] = []
  page.on("pageerror", err => pageErrors.push(err.message))

  await page.goto("/agent-identity")
  await expect(page.locator("main, [role=main]")).toBeVisible({ timeout: 10_000 })

  const hydration = pageErrors.filter(m => /hydrat/i.test(m))
  expect(hydration, "hydration errors on /agent-identity").toEqual([])
})
