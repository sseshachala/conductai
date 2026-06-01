/**
 * Guard test harness teardown script.
 *
 * Run this after you are done testing to clean up Clerk test users:
 *   npm run teardown
 *
 * What it does:
 *   1. Reads test-state.json for the list of Clerk user IDs
 *   2. Deletes each user from Clerk via the Management API
 *   3. Optionally removes test-state.json (pass --clean to enable)
 *
 * It does NOT delete the test workspace from Conduct — workspaces must
 * be removed manually if desired, as they may hold useful audit data.
 *
 * Environment variables required:
 *   CLERK_SECRET_KEY — Clerk dashboard → API Keys → Secret key
 */

import { existsSync, readFileSync, rmSync } from "fs"
import { deleteClerkUser } from "./lib/clerk.js"

// ── Helpers ────────────────────────────────────────────────────────────────

interface TestState {
  workspaceId: string
  users: Record<string, { clerkId: string; email: string }>
}

function loadState(): TestState | null {
  if (!existsSync("test-state.json")) return null
  try {
    return JSON.parse(readFileSync("test-state.json", "utf8")) as TestState
  } catch {
    return null
  }
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== Conduct Guard — Test Teardown ===\n")

  const state = loadState()
  if (!state) {
    console.log("No test-state.json found — nothing to tear down.")
    return
  }

  const clean = process.argv.includes("--clean")

  console.log("1. Deleting Clerk test users…")
  for (const [role, user] of Object.entries(state.users)) {
    try {
      await deleteClerkUser(user.clerkId)
      console.log(`  [clerk] deleted ${role}: ${user.email} (${user.clerkId})`)
    } catch (err) {
      console.warn(
        `  [warn] Could not delete ${role} (${user.clerkId}): ${
          err instanceof Error ? err.message : err
        }`
      )
    }
  }

  if (clean) {
    rmSync("test-state.json", { force: true })
    console.log("\n2. Removed test-state.json")
  } else {
    console.log("\n(Pass --clean to also remove test-state.json)")
  }

  console.log("\n=== Teardown complete ===")
}

main().catch((err) => {
  console.error("\nTeardown failed:", err)
  process.exit(1)
})
