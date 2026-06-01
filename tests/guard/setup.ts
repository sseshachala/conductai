/**
 * Guard test harness setup script.
 *
 * Run this once before executing the test flows:
 *   npm run setup
 *
 * What it does:
 *   1. Creates 4 Clerk test users (upserts — safe to run again)
 *   2. Obtains a Clerk sign-in token for the admin user
 *   3. Exchanges the token for a Conduct API Bearer token by signing in via
 *      a lightweight fetch to the Clerk frontend API (simulates browser sign-in)
 *   4. Creates (or reuses) a "Guard Test Workspace" via the Conduct API
 *   5. Adds the editor, security, and viewer users as members of that workspace
 *   6. Writes test-state.json with all IDs and credentials for the runner
 *
 * Environment variables required:
 *   CLERK_SECRET_KEY    — Clerk dashboard → API Keys → Secret key
 *   CONDUCT_API_URL     — e.g. http://localhost:8000
 *   CONDUCT_APP_URL     — e.g. http://localhost:3000
 *
 * Note: Conduct API auth requires a Clerk session JWT. The setup script uses
 * the Clerk Management API to create a sign-in token, then redeems it via
 * the Clerk Frontend API to obtain a session JWT usable as a Bearer token.
 */

import { writeFileSync } from "fs"
import { upsertClerkUser } from "./lib/clerk.js"
import { getOrCreateTestWorkspace, addMemberWithRole } from "./lib/conduct.js"
import { createBrowser, signInWithPassword } from "./lib/stagehand.js"

// ── Test user definitions ──────────────────────────────────────────────────

// Acme org: 1 admin, 2 editors (developers), 1 security, 1 viewer
const TEST_USERS = {
  admin: {
    email: "acme.admin@mailinator.com",
    password: "AcmeTest!Admin1",
  },
  dev1: {
    email: "acme.dev1@mailinator.com",
    password: "AcmeTest!Dev1",
    role: "editor" as const,
  },
  dev2: {
    email: "acme.dev2@mailinator.com",
    password: "AcmeTest!Dev2",
    role: "editor" as const,
  },
  security: {
    email: "acme.security@mailinator.com",
    password: "AcmeTest!Sec1",
    role: "security" as const,
  },
  viewer: {
    email: "acme.viewer@mailinator.com",
    password: "AcmeTest!View1",
    role: "viewer" as const,
  },
} as const

const WORKSPACE_NAME = "Acme"

type RoleKey = keyof typeof TEST_USERS

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Signs into the Conduct app as admin via a real browser (Stagehand/Chromium).
 * Clerk handles all cookie state inside the browser — no manual token needed.
 * Extracts the Clerk session JWT from the browser's window.__clerk_session.
 *
 * Falls back to CONDUCT_ADMIN_TOKEN env var if set (useful in CI).
 */
async function getConductBearerToken(email: string, password: string): Promise<string> {
  if (process.env.CONDUCT_ADMIN_TOKEN) {
    return process.env.CONDUCT_ADMIN_TOKEN
  }

  const appUrl = (process.env.CONDUCT_APP_URL ?? "http://localhost:3000").replace(/\/$/, "")
  const apiUrl = (process.env.CONDUCT_API_URL ?? "http://localhost:8000").replace(/\/$/, "")
  console.log("  [auth] opening browser to sign in as admin…")

  const { stagehand, page } = await createBrowser(true)
  let capturedToken: string | null = null

  try {
    // Intercept any request to the Conduct API and capture the Authorization header.
    // This is more reliable than reading Clerk internals from the window object.
    await page.route(`${apiUrl}/**`, async (route) => {
      const headers = route.request().headers()
      const auth = headers["authorization"] ?? headers["Authorization"]
      if (auth?.startsWith("Bearer ") && !capturedToken) {
        capturedToken = auth.slice(7)
        console.log("  [auth] captured Bearer token from API request")
      }
      await route.continue()
    })

    // Sign in — the app will immediately make API calls with the JWT
    await signInWithPassword(page, email, password, appUrl)

    // Wait up to 10 s for the app to make an authenticated API call
    const deadline = Date.now() + 10_000
    while (!capturedToken && Date.now() < deadline) {
      await page.waitForTimeout(300)
    }

    if (!capturedToken) {
      throw new Error(
        "No authenticated API request observed after sign-in. " +
        "Check CONDUCT_APP_URL and CONDUCT_API_URL are correct, and that the app " +
        "makes API calls on load (it should hit /projects on the Guard dashboard)."
      )
    }

    return capturedToken
  } finally {
    await stagehand.close()
  }
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== Conduct Guard — Test Setup ===\n")

  // Step 1: Create Clerk users
  console.log("1. Creating Clerk test users…")
  const clerkIds: Record<RoleKey, string> = {} as Record<RoleKey, string>

  for (const [role, creds] of Object.entries(TEST_USERS) as [RoleKey, typeof TEST_USERS[RoleKey]][]) {
    clerkIds[role] = await upsertClerkUser(creds.email, creds.password)
  }

  // Step 2: Obtain an admin Bearer token via browser sign-in
  console.log("\n2. Obtaining admin Bearer token via browser sign-in…")
  let adminToken: string

  try {
    adminToken = await getConductBearerToken(TEST_USERS.admin.email, TEST_USERS.admin.password)
  } catch (err) {
    console.error("  [auth] ERROR:", err instanceof Error ? err.message : err)
    console.error(
      "\n  Hint: Set CONDUCT_ADMIN_TOKEN=<jwt> to skip browser sign-in.\n" +
        "  Get the JWT from browser DevTools → Network → any /projects call → Authorization header.\n"
    )
    process.exit(1)
  }

  // Step 3: Create or reuse the Acme workspace
  console.log("\n3. Creating Acme workspace…")
  const workspaceId = await getOrCreateTestWorkspace(adminToken, WORKSPACE_NAME)

  // Step 4: Add members with their roles
  console.log("\n4. Assigning roles in workspace…")

  const nonAdminUsers: [Exclude<RoleKey, "admin">, string, string][] = [
    ["dev1",     clerkIds.dev1,     "editor"],
    ["dev2",     clerkIds.dev2,     "editor"],
    ["security", clerkIds.security, "security"],
    ["viewer",   clerkIds.viewer,   "viewer"],
  ]

  for (const [key, clerkId, role] of nonAdminUsers) {
    try {
      await addMemberWithRole(adminToken, workspaceId, clerkId, role as "editor" | "security" | "viewer")
      console.log(`  [ok] ${key} added as ${role}`)
    } catch (err) {
      console.warn(`  [warn] Could not add ${key}: ${err instanceof Error ? err.message : err}`)
    }
  }

  // Step 5: Write test-state.json
  const state = {
    workspaceId,
    org: WORKSPACE_NAME,
    generatedAt: new Date().toISOString(),
    users: {
      admin: {
        clerkId: clerkIds.admin,
        email: TEST_USERS.admin.email,
        password: TEST_USERS.admin.password,
        role: "admin",
      },
      dev1: {
        clerkId: clerkIds.dev1,
        email: TEST_USERS.dev1.email,
        password: TEST_USERS.dev1.password,
        role: "editor",
      },
      dev2: {
        clerkId: clerkIds.dev2,
        email: TEST_USERS.dev2.email,
        password: TEST_USERS.dev2.password,
        role: "editor",
      },
      security: {
        clerkId: clerkIds.security,
        email: TEST_USERS.security.email,
        password: TEST_USERS.security.password,
        role: "security",
      },
      viewer: {
        clerkId: clerkIds.viewer,
        email: TEST_USERS.viewer.email,
        password: TEST_USERS.viewer.password,
        role: "viewer",
      },
    },
  }

  writeFileSync("test-state.json", JSON.stringify(state, null, 2), "utf8")
  console.log("\n5. Wrote test-state.json")
  console.log("\n=== Setup complete. Run: npm test ===\n")
}

main().catch((err) => {
  console.error("\nSetup failed:", err)
  process.exit(1)
})
