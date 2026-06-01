/**
 * Security role flow.
 *
 * The security role can view and manage Guard content but cannot perform
 * admin-only actions such as setting spend limits or inviting members.
 *
 * Steps:
 *   1.  Login as security user
 *   2.  Guard loads — not redirected to /dashboard
 *   3.  Activity tab — event log visible
 *   4.  Policies tab — rule list visible
 *   5.  Add rule — security role can create custom rules
 *   6.  Spend tab — spend data visible
 *   7.  Spend controls — Configure button absent or disabled (admin-only)
 *   8.  Settings tab — visible
 *   9.  Invite member — invite form absent or action blocked (admin-only)
 */

import { join } from "path"
import type { RoleResult, TestStep } from "../lib/report.js"
import {
  createBrowser,
  signInWithPassword,
  screenshot,
} from "../lib/stagehand.js"
import { setWorkspaceCookie } from "../lib/conduct.js"

interface UserCreds {
  email: string
  password: string
  clerkId: string
}

interface TestState {
  workspaceId: string
  users: { security: UserCreds; [k: string]: UserCreds }
}

export async function runSecurityFlow(
  state: TestState,
  screenshotDir: string
): Promise<RoleResult> {
  const startedAt = new Date()
  const steps: TestStep[] = []
  const appUrl = (process.env.CONDUCT_APP_URL ?? "http://localhost:3000").replace(/\/$/, "")

  function shotPath(name: string): string {
    return join(screenshotDir, "security", `${name}.png`)
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
    await recordStep("Login as security user", async () => {
      const landedUrl = await signInWithPassword(
        page,
        state.users.security.email,
        state.users.security.password,
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

    // Set workspace cookie
    await setWorkspaceCookie(page, state.workspaceId, appUrl)

    // ── Step 2: Guard loads ──────────────────────────────────────────────────
    await recordStep("Guard loads — not redirected to /dashboard", async () => {
      await page.goto(`${appUrl}/guard`)
      await new Promise((r) => setTimeout(r, 3000))
      const currentUrl = page.url()
      const screenshotPath = await screenshot(page, shotPath("02-guard-loads"))
      const passed = currentUrl.includes("/guard") && !currentUrl.includes("/dashboard")
      return {
        passed,
        note: `URL: ${currentUrl}`,
        screenshotPath,
      }
    })

    // ── Step 3: Activity tab ─────────────────────────────────────────────────
    await recordStep("Activity tab — event log visible", async () => {
      await page.act('Click the "Activity" or "Activity log" tab in the Guard navigation')
      await new Promise((r) => setTimeout(r, 1500))
      const obs = await page.observe(
        "Is there an activity log, event table, or empty-state message visible?"
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
        "Is there a list of policy rules, a policies table, or a no-policies message visible?"
      )
      const screenshotPath = await screenshot(page, shotPath("04-policies-tab"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 5: Add rule (security can create rules) ─────────────────────────
    await recordStep("Security role can open Add rule modal", async () => {
      const obs = await page.observe(
        'Is there an "Add rule" button or link visible on the Policies page?'
      )
      const canSeeButton = (obs as unknown as { found?: boolean }).found !== false
      let modalOpened = false

      if (canSeeButton) {
        await page.act('Click the "Add rule" button or link')
        await new Promise((r) => setTimeout(r, 1000))
        const modalObs = await page.observe(
          "Is a modal or dialog open for adding a new policy rule?"
        )
        modalOpened = (modalObs as unknown as { found?: boolean }).found !== false
        if (modalOpened) {
          await page.act("Close or dismiss the modal by clicking Cancel or the close button")
        }
      }

      const screenshotPath = await screenshot(page, shotPath("05-add-rule"))
      return {
        passed: canSeeButton && modalOpened,
        note: canSeeButton ? (modalOpened ? "Modal opened" : "Button visible but modal did not open") : "Add rule button not found",
        screenshotPath,
      }
    })

    // ── Step 6: Spend tab ────────────────────────────────────────────────────
    await recordStep("Spend tab — spend data visible", async () => {
      await page.goto(`${appUrl}/guard/spend`)
      await new Promise((r) => setTimeout(r, 2000))
      const obs = await page.observe(
        "Is there spend data, cost information, or a spend controls panel visible on this page?"
      )
      const screenshotPath = await screenshot(page, shotPath("06-spend-tab"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 7: Spend controls — Configure absent for security ───────────────
    await recordStep("Spend controls Configure button absent for security role", async () => {
      const obs = await page.observe(
        'Is there a "Configure" button for spend controls on this page?'
      )
      // For security role the Configure button should NOT be present
      // (only admins can modify team spend limits)
      const configurePresent = (obs as unknown as { found?: boolean }).found !== false
      const screenshotPath = await screenshot(page, shotPath("07-spend-controls"))
      return {
        // Passes if Configure is absent (security cannot set limits)
        passed: !configurePresent,
        note: configurePresent
          ? "Configure button visible — security role should not be able to configure spend limits"
          : "Configure button correctly absent for security role",
        screenshotPath,
      }
    })

    // ── Step 8: Settings tab visible ────────────────────────────────────────
    await recordStep("Settings tab — notification prefs visible", async () => {
      await page.goto(`${appUrl}/guard/settings`)
      await new Promise((r) => setTimeout(r, 2000))
      const obs = await page.observe(
        "Is there a settings page with notification preferences, alert config, or team settings visible?"
      )
      const screenshotPath = await screenshot(page, shotPath("08-settings"))
      const passed = (obs as unknown as { found?: boolean }).found !== false
      return { passed, screenshotPath }
    })

    // ── Step 9: Invite member — absent for security ──────────────────────────
    await recordStep("Invite member action absent for security role", async () => {
      const obs = await page.observe(
        'Is there an "Invite member", "Add member", or "Invite" button or form visible on this page?'
      )
      const invitePresent = (obs as unknown as { found?: boolean }).found !== false
      const screenshotPath = await screenshot(page, shotPath("09-invite-absent"))
      return {
        // Passes if invite form is absent (admin-only)
        passed: !invitePresent,
        note: invitePresent
          ? "Invite form is visible — security role should not be able to invite members"
          : "Invite action correctly absent for security role",
        screenshotPath,
      }
    })
  } finally {
    await stagehand.close()
  }

  return {
    role: "security",
    steps,
    startedAt,
    completedAt: new Date(),
  }
}
