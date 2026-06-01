/**
 * Guard test runner — main entry point.
 *
 * Usage:
 *   npm test                    # run all 4 role flows
 *   npm run test:admin          # run admin flow only
 *   npm run test:security       # run security flow only
 *   npm run test:editor         # run editor flow only
 *   npm run test:viewer         # run viewer flow only
 *
 * Or directly:
 *   tsx runner.ts --role admin
 *   tsx runner.ts --role security,editor
 *
 * Prerequisites:
 *   - npm run setup must have completed and written test-state.json
 *   - ANTHROPIC_API_KEY must be set for Stagehand
 *   - CONDUCT_APP_URL must point to the running app
 *
 * Exits 0 if all steps in all tested roles pass, 1 otherwise.
 */

import { readFileSync, existsSync, mkdirSync } from "fs"
import { join, resolve } from "path"
import type { RoleResult } from "./lib/report.js"
import { generateReport } from "./lib/report.js"
import { runAdminFlow } from "./flows/admin.js"
import { runSecurityFlow } from "./flows/security.js"
import { runEditorFlow } from "./flows/editor.js"
import { runViewerFlow } from "./flows/viewer.js"

// ── Types ──────────────────────────────────────────────────────────────────

type RoleKey = "admin" | "security" | "editor" | "viewer"

interface TestState {
  workspaceId: string
  generatedAt: string
  users: Record<
    RoleKey,
    { clerkId: string; email: string; password: string }
  >
}

// ── Helpers ────────────────────────────────────────────────────────────────

function parseRoleArgs(): RoleKey[] {
  const allRoles: RoleKey[] = ["admin", "security", "editor", "viewer"]
  const roleArg = process.argv.find((a) => a.startsWith("--role"))
  if (!roleArg) return allRoles

  const value = roleArg.includes("=")
    ? roleArg.split("=")[1]
    : process.argv[process.argv.indexOf(roleArg) + 1]

  if (!value) return allRoles

  const requested = value
    .split(",")
    .map((r) => r.trim().toLowerCase() as RoleKey)
    .filter((r) => allRoles.includes(r))

  return requested.length > 0 ? requested : allRoles
}

function loadState(statePath: string): TestState {
  if (!existsSync(statePath)) {
    console.error(`\nERROR: ${statePath} not found.`)
    console.error("Run 'npm run setup' first to create test users and workspace.\n")
    process.exit(1)
  }

  try {
    return JSON.parse(readFileSync(statePath, "utf8")) as TestState
  } catch (err) {
    console.error(`\nERROR: Could not parse ${statePath}: ${err}`)
    process.exit(1)
  }
}

function printSummary(results: RoleResult[]): void {
  console.log("\n" + "=".repeat(60))
  console.log("  GUARD TEST SUMMARY")
  console.log("=".repeat(60))

  let totalSteps = 0
  let totalPassed = 0

  for (const result of results) {
    const passed = result.steps.filter((s) => s.passed).length
    const total = result.steps.length
    const status = passed === total ? "PASS" : "FAIL"
    const dur = `${((result.completedAt.getTime() - result.startedAt.getTime()) / 1000).toFixed(1)}s`
    console.log(
      `  ${status.padEnd(4)}  ${result.role.padEnd(10)} ${passed}/${total} steps  (${dur})`
    )

    // Print failed steps
    for (const step of result.steps) {
      if (!step.passed) {
        console.log(`            FAIL: ${step.description}`)
        if (step.note) console.log(`                  ${step.note}`)
      }
    }

    totalSteps += total
    totalPassed += passed
  }

  console.log("-".repeat(60))
  const overallStatus = totalPassed === totalSteps ? "PASS" : "FAIL"
  console.log(`  ${overallStatus}  Total: ${totalPassed}/${totalSteps} steps passed`)
  console.log("=".repeat(60) + "\n")
}

// ── Flow dispatcher ────────────────────────────────────────────────────────

async function runFlow(
  role: RoleKey,
  state: TestState,
  screenshotDir: string
): Promise<RoleResult> {
  console.log(`\n--- Running flow: ${role} ---`)

  switch (role) {
    case "admin":
      return runAdminFlow(state, screenshotDir)
    case "security":
      return runSecurityFlow(state, screenshotDir)
    case "editor":
      return runEditorFlow(state, screenshotDir)
    case "viewer":
      return runViewerFlow(state, screenshotDir)
  }
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  // Validate required env vars
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("ERROR: ANTHROPIC_API_KEY is not set. Stagehand needs it to use Claude vision.")
    process.exit(1)
  }

  const appUrl = process.env.CONDUCT_APP_URL ?? "http://localhost:3000"
  console.log(`\n=== Conduct Guard — UI Test Runner ===`)
  console.log(`App URL: ${appUrl}`)

  // Load test state written by setup.ts
  const statePath = resolve("test-state.json")
  const state = loadState(statePath)
  console.log(`Workspace: ${state.workspaceId} (created ${state.generatedAt})`)

  // Determine which roles to run
  const rolesToTest = parseRoleArgs()
  console.log(`Roles: ${rolesToTest.join(", ")}`)

  // Prepare output directory
  const reportsDir = resolve("reports")
  const screenshotDir = join(reportsDir, "screenshots")
  mkdirSync(screenshotDir, { recursive: true })

  // Run flows sequentially (each flow opens its own browser)
  const results: RoleResult[] = []
  for (const role of rolesToTest) {
    const result = await runFlow(role, state, screenshotDir)
    results.push(result)

    // Print per-role progress
    const passed = result.steps.filter((s) => s.passed).length
    const total = result.steps.length
    const status = passed === total ? "PASS" : "FAIL"
    console.log(`  [${status}] ${role}: ${passed}/${total} steps`)
  }

  // Generate HTML report
  const reportPath = await generateReport(results, reportsDir)
  console.log(`\nReport: ${reportPath}`)

  // Print summary to stdout
  printSummary(results)

  // Exit code reflects overall pass/fail
  const allPassed = results.every((r) => r.steps.every((s) => s.passed))
  process.exit(allPassed ? 0 : 1)
}

main().catch((err) => {
  console.error("\nRunner failed unexpectedly:", err)
  process.exit(1)
})
