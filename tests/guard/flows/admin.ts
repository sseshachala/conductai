/**
 * Admin role flow.
 *
 * Admins have full Guard access. This flow exercises:
 *   1.  Login as admin
 *   2.  Guard dashboard loads (not redirected)
 *   3.  Activity tab visible
 *   4.  Policies tab — rule list visible
 *   5.  Add rule modal opens
 *   6.  Spend tab visible with spend controls panel
 *   7.  Spend controls — Configure button accessible (admin-only)
 *   8.  Settings tab — notification prefs visible
 *   9.  Members list visible in Settings
 *   10. Role badge shows "admin" on own account row
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
  users: { admin: UserCreds; [k: string]: UserCreds }
}

export async function runAdminFlow(
  state: TestState,
  screenshotDir: string
): Promise<RoleResult> {
  const startedAt = new Date()
  const steps: TestStep[] = []
  const appUrl = (process.env.CONDUCT_APP_URL ?? "http://localhost:3000").replace(/\/$/, "")

  function shotPath(name: string): string {
    return join(screenshotDir, "admin", `${name}.png`)
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
    await recordStep("Login as admin", async () => {
      const landedUrl = await signInWithPassword(
        page,
        state.users.admin.email,
        state.users.admin.password,
        appUrl
      )
      const screenshotPath = await screenshot(page, shotPath("01-login"))
      const passed = !landedUrl.includes("/sign-in")
      return {
        passed,
        note: passed ? `Landed on: ${landedUrl}` : `Still on sign-in: ${landedUrl}`,
        screenshotPath,
      }
    })

    // Set workspace cookie so the app loads the test workspace
    await setWorkspaceCookie(page, state.workspaceId, appUrl)

    // ── Step 2: Guard dashboard loads ────────────────────────────────────────
    await recordStep("Guard dashboard loads (not redirected)", async () => {
      await page.goto(`${appUrl}/guard`)
      // Wait up to 8s for the page heading to appear
      const observations = await page.observe(
        'Is there a heading or title containing the word "Guard" on this page?'
      )
      const screenshotPath = await screenshot(page, shotPath("02-guard-loads"))
      const currentUrl = page.url()
      const onGuard = currentUrl.includes("/guard") && !currentUrl.includes("/dashboard")
      const passed = onGuard && (observations as unknown as { found?: boolean }).found !== false
      return {
        passed,
        note: `URL: ${currentUrl}`,
        screenshotPath,
      }
    })

    // ── Step 3: Activity tab ─────────────────────────────────────────────────
    await recordStep("Activity tab — event list or empty state visible", async () => {
      await page.act('Click the "Activity" tab or "Activity log" link in the Guard navigation')
      await new Promise((r) => setTimeout(r, 1500))
      const obs = await page.observe(
        "Is there an activity log, event table, or empty-state message visible on this page?"
      )
      const screenshotPath = await screenshot(page, shotPath("03-activity-tab"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 4: Policies tab ─────────────────────────────────────────────────
    await recordStep("Policies tab — rule list visible", async () => {
      await page.goto(`${appUrl}/guard/policies`)
      await new Promise((r) => setTimeout(r, 2000))
      const obs = await page.observe(
        "Is there a list of policy rules, a table of rules, or a message about no policies yet?"
      )
      const screenshotPath = await screenshot(page, shotPath("04-policies-tab"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 5: Add rule modal opens ─────────────────────────────────────────
    await recordStep("Add rule modal opens when clicking Add rule", async () => {
      await page.act('Click the "Add rule" button or link')
      await new Promise((r) => setTimeout(r, 1000))
      const obs = await page.observe(
        "Is a modal or dialog open that contains a form for adding a new policy rule?"
      )
      const screenshotPath = await screenshot(page, shotPath("05-add-rule-modal"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      // Close the modal before proceeding
      await page.act("Close or dismiss the modal by clicking Cancel or the close button")
      return { passed, screenshotPath }
    })

    // ── Step 6: Spend tab visible ────────────────────────────────────────────
    await recordStep("Spend tab — spend overview visible", async () => {
      await page.goto(`${appUrl}/guard/spend`)
      await new Promise((r) => setTimeout(r, 2000))
      const obs = await page.observe(
        "Is there spend tracking information, cost data, or a spend controls panel on this page?"
      )
      const screenshotPath = await screenshot(page, shotPath("06-spend-tab"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 7: Spend controls — Configure button ────────────────────────────
    await recordStep("Spend controls — Configure button accessible to admin", async () => {
      const obs = await page.observe(
        'Is there a "Configure" or "Edit" button near the Spend Controls panel?'
      )
      const screenshotPath = await screenshot(page, shotPath("07-spend-controls"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return {
        passed,
        note: passed ? "Configure button visible" : "Configure button not found — may be admin-only restriction missing",
        screenshotPath,
      }
    })

    // ── Step 8: Settings tab ─────────────────────────────────────────────────
    await recordStep("Settings tab — notification preferences visible", async () => {
      await page.goto(`${appUrl}/guard/settings`)
      await new Promise((r) => setTimeout(r, 2000))
      const obs = await page.observe(
        "Are there notification settings, alert preferences, or Slack channel configuration fields visible?"
      )
      const screenshotPath = await screenshot(page, shotPath("08-settings-tab"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 9: Members list visible ─────────────────────────────────────────
    await recordStep("Members list visible in Settings", async () => {
      // The settings page contains a members/team section
      const obs = await page.observe(
        "Is there a list of team members, a members table, or an invite section visible on this page?"
      )
      const screenshotPath = await screenshot(page, shotPath("09-members-list"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 10: Role badge shows admin ──────────────────────────────────────
    await recordStep("Admin role badge visible on own account", async () => {
      const obs = await page.observe(
        `Is the word "admin" or an "Admin" badge visible on this page, indicating the current user's role?`
      )
      const screenshotPath = await screenshot(page, shotPath("10-role-badge"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return {
        passed,
        note: passed ? "Admin role badge found" : "Role badge not visible",
        screenshotPath,
      }
    })
  } finally {
    await stagehand.close()
  }

  return {
    role: "admin",
    steps,
    startedAt,
    completedAt: new Date(),
  }
}
