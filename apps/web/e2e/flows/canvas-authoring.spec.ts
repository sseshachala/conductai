import { test, expect } from "@playwright/test"

// #2315 — canvas authoring interactions against the seeded e2e workflow
// (apps/api/scripts/seed_e2e_workspace.py → E2E_WORKFLOW_ID, DEV workspace).
const DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
const E2E_WORKFLOW_ID = "22222222-2222-2222-2222-000000000001"

test("canvas: minimap toggle, block search, sticky note, version history", async ({ page, context }) => {
  await context.addCookies([
    { name: "delegator_project_id", value: DEV_WORKSPACE_ID, url: "http://localhost:3000" },
  ])
  await page.goto(`/workflows/${E2E_WORKFLOW_ID}`)
  const controls = page.getByRole("toolbar", { name: "Canvas controls" })
  await expect(controls).toBeVisible({ timeout: 15_000 })

  // Minimap — on by default, toggle hides it
  await expect(page.getByLabel("Canvas minimap")).toBeVisible()
  await controls.getByRole("button", { name: "Hide minimap" }).click()
  await expect(page.getByLabel("Canvas minimap")).toHaveCount(0)
  await controls.getByRole("button", { name: "Show minimap" }).click()

  // Cmd/Ctrl+P search is keyboard-reachable and Esc closes it
  await page.keyboard.press("ControlOrMeta+p")
  const search = page.getByRole("dialog", { name: "Find block" })
  await expect(search).toBeVisible()
  await expect(search.getByRole("combobox")).toBeFocused()
  await page.keyboard.press("Escape")
  await expect(search).toHaveCount(0)

  // Sticky note — added, edited, autosaved (PUT carries it under graph.annotations)
  const saved = page.waitForResponse(r =>
    r.request().method() === "PUT" &&
    new URL(r.url()).pathname.endsWith(`/workflows/${E2E_WORKFLOW_ID}`) &&
    (r.request().postData() ?? "").includes("this exists"),
  )
  await controls.getByRole("button", { name: "Add note" }).click()
  const note = page.getByRole("note")
  await expect(note).toBeVisible()
  await note.dblclick()
  await page.getByLabel("Note text (Markdown)").fill("**Why** this exists")
  await page.getByLabel("Note title").click() // focus stays inside the note → still editing
  await expect(page.getByLabel("Note text (Markdown)")).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(note.locator("strong", { hasText: "Why" })).toBeVisible()
  const put = await saved
  expect(put.status()).toBe(200)
  const body = JSON.parse(put.request().postData() ?? "{}")
  expect(body.graph.annotations).toHaveLength(1)
  expect(body.graph.nodes.some((n: { type?: string }) => n.type === "annotation")).toBe(false)

  // History lists the autosaved version with its note
  await page.getByRole("button", { name: "History", exact: true }).click()
  const versions = page.getByRole("complementary", { name: "Versions" })
  await expect(versions.getByText(/1 note\b/).first()).toBeVisible({ timeout: 10_000 })
})
