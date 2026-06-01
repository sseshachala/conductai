/**
 * Editor role flow.
 *
 * Editors have no access to Guard. When they navigate to /guard they should
 * be redirected to /dashboard. Guard should also be absent from the sidebar.
 *
 * Steps:
 *   1.  Login as editor
 *   2.  Navigate to /guard — verify redirect to /dashboard
 *   3.  Screenshot the dashboard they landed on
 *   4.  Verify Guard is NOT listed in the sidebar navigation
 *   5.  Attempt direct URL /guard/policies — verify redirected away
 *   6.  Attempt direct URL /guard/spend — verify redirected away
 */

import { join } from "path"
import type { RoleResult, TestStep } from "../lib/report.js"
import {
  createBrowser,
  signInWithPassword,
  screenshot,
  waitForUrlChange,
} from "../lib/stagehand.js"
import { setWorkspaceCookie } from "../lib/conduct.js"

interface UserCreds {
  email: string
  password: string
  clerkId: string
}

interface TestState {
  workspaceId: string
  users: { editor: UserCreds; [k: string]: UserCreds }
}

export async function runEditorFlow(
  state: TestState,
  screenshotDir: string
): Promise<RoleResult> {
  const startedAt = new Date()
  const steps: TestStep[] = []
  const appUrl = (process.env.CONDUCT_APP_URL ?? "http://localhost:3000").replace(/\/$/, "")

  function shotPath(name: string): string {
    return join(screenshotDir, "editor", `${name}.png`)
  }

  async function recordStep(
    description: string,
    fn: () => Promise<{ passed: boolean; note?: string; screenshotPath?: string }>
  ): Promise<void> {
    try {
      const result = await fn()
      steps.push({ description, ...result })
    } catch (err) {
      steps.push({
        description,
        passed: false,
        note: err instanceof Error ? err.message : String(err),
      })
    }
  }

  const { stagehand, page } = await createBrowser(true)

  try {
    // ── Step 1: Login ────────────────────────────────────────────────────────
    await recordStep("Login as editor", async () => {
      const landedUrl = await signInWithPassword(
        page,
        state.users.editor.email,
        state.users.editor.password,
        appUrl
      )
      const screenshotPath = await screenshot(page, shotPath("01-login"))
      const passed = !landedUrl.includes("/sign-in")
      return {
        passed,
        note: `Landed on: ${landedUrl}`,
        screenshotPath,
      }
    })

    // Set workspace cookie so the app knows which workspace the editor belongs to
    await setWorkspaceCookie(page, state.workspaceId, appUrl)

    // ── Step 2: Navigate to /guard — expect redirect ─────────────────────────
    await recordStep("Navigate to /guard — redirected to /dashboard", async () => {
      const guardUrl = `${appUrl}/guard`
      await page.goto(guardUrl)
      // The app fetches role via /projects/{id}/members and then calls router.replace
      // Give it up to 8s to redirect
      await new Promise((r) => setTimeout(r, 4000))
      const currentUrl = page.url()
      const screenshotPath = await screenshot(page, shotPath("02-guard-redirect"))
      const redirected = currentUrl.includes("/dashboard") && !currentUrl.includes("/guard")
      return {
        passed: redirected,
        note: redirected
          ? `Correctly redirected to: ${currentUrl}`
          : `Still on: ${currentUrl} — expected redirect to /dashboard`,
        screenshotPath,
      }
    })

    // ── Step 3: Screenshot the dashboard ────────────────────────────────────
    await recordStep("Dashboard is displayed after redirect", async () => {
      const obs = await page.observe(
        "Is a dashboard, run feed, playbook list, or main application content visible (not a Guard page)?"
      )
      const screenshotPath = await screenshot(page, shotPath("03-dashboard"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return {
        passed,
        note: `URL: ${page.url()}`,
        screenshotPath,
      }
    })

    // ── Step 4: Guard absent from sidebar ────────────────────────────────────
    await recordStep("Guard is absent from sidebar navigation for editor", async () => {
      const obs = await page.observe(
        'Is the word "Guard" present in the sidebar navigation links?'
      )
      const guardInSidebar = (obs as unknown as { found?: boolean }).found !== false
      const screenshotPath = await screenshot(page, shotPath("04-no-guard-sidebar"))
      return {
        // Passes if Guard is NOT in the sidebar (editors should not see it)
        passed: !guardInSidebar,
        note: guardInSidebar
          ? "Guard link is in the sidebar — should be hidden for editor role"
          : "Guard correctly absent from sidebar for editor",
        screenshotPath,
      }
    })

    // ── Step 5: Direct /guard/policies also redirects ────────────────────────
    await recordStep("Direct /guard/policies URL — redirected for editor", async () => {
      await page.goto(`${appUrl}/guard/policies`)
      await new Promise((r) => setTimeout(r, 4000))
      const currentUrl = page.url()
      const screenshotPath = await screenshot(page, shotPath("05-policies-redirect"))
      const redirected = !currentUrl.includes("/guard/policies")
      return {
        passed: redirected,
        note: redirected
          ? `Redirected to: ${currentUrl}`
          : `Policies page loaded — should have redirected for editor role`,
        screenshotPath,
      }
    })

    // ── Step 6: Direct /guard/spend also redirects ───────────────────────────
    await recordStep("Direct /guard/spend URL — redirected for editor", async () => {
      await page.goto(`${appUrl}/guard/spend`)
      await new Promise((r) => setTimeout(r, 4000))
      const currentUrl = page.url()
      const screenshotPath = await screenshot(page, shotPath("06-spend-redirect"))
      const redirected = !currentUrl.includes("/guard/spend")
      return {
        passed: redirected,
        note: redirected
          ? `Redirected to: ${currentUrl}`
          : `Spend page loaded — should have redirected for editor role`,
        screenshotPath,
      }
    })
  } finally {
    await stagehand.close()
  }

  return {
    role: "editor",
    steps,
    startedAt,
    completedAt: new Date(),
  }
}
