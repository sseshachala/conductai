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
import { upsertClerkUser, createSignInToken, findClerkUserByEmail } from "./lib/clerk.js"
import { getOrCreateTestWorkspace, addMemberWithRole } from "./lib/conduct.js"

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
 * Obtains a Bearer JWT from the Conduct API using the Clerk Frontend API.
 *
 * Flow:
 *   1. Use the Clerk Management API to create a sign-in token (backend secret)
 *   2. POST the token to the Clerk Frontend API (/v1/client/sign_ins) to
 *      simulate a "magic link" sign-in and receive a session JWT
 *
 * The session JWT is what the Conduct API accepts as an Authorization header.
 *
 * If CONDUCT_ADMIN_TOKEN is set in the environment, that value is used
 * directly (useful in CI where a long-lived token is available).
 */
async function getConductBearerToken(clerkUserId: string): Promise<string> {
  // Allow overriding with a pre-baked token in CI
  if (process.env.CONDUCT_ADMIN_TOKEN) {
    return process.env.CONDUCT_ADMIN_TOKEN
  }

  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const frontendApiHost = process.env.CLERK_FRONTEND_API_URL

  if (!publishableKey && !frontendApiHost) {
    throw new Error(
      "Cannot obtain a Conduct Bearer token: set either CONDUCT_ADMIN_TOKEN " +
        "(pre-baked JWT) or both NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and " +
        "CLERK_FRONTEND_API_URL so we can exchange a sign-in token."
    )
  }

  // Derive the Clerk frontend API URL from the publishable key if not explicit.
  // The publishable key encodes the instance domain:
  //   pk_test_<base64(domain)>  →  https://<domain>
  let clerkFrontendUrl = frontendApiHost
  if (!clerkFrontendUrl && publishableKey) {
    const encoded = publishableKey.split("_")[2]?.replace(/\.$/, "") ?? ""
    try {
      const decoded = Buffer.from(encoded, "base64").toString("utf8")
      // decoded is like "clerk.yourapp.com$"
      const domain = decoded.replace(/\$$/, "")
      clerkFrontendUrl = `https://${domain}`
    } catch {
      throw new Error("Could not decode NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY to derive Clerk frontend URL")
    }
  }

  // Create a short-lived sign-in token via Management API
  const signInToken = await createSignInToken(clerkUserId)

  // Redeem the sign-in token using the Clerk Frontend API
  const redeemRes = await fetch(
    `${clerkFrontendUrl}/v1/client/sign_ins?__clerk_ticket=${signInToken}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ strategy: "ticket", ticket: signInToken }).toString(),
    }
  )

  if (!redeemRes.ok) {
    const body = await redeemRes.text()
    throw new Error(
      `Failed to redeem Clerk sign-in token: HTTP ${redeemRes.status} — ${body}`
    )
  }

  const clerkData = await redeemRes.json()
  // The JWT is in client.sessions[0].last_active_token.jwt
  const jwt =
    clerkData?.client?.sessions?.[0]?.last_active_token?.jwt ??
    clerkData?.response?.last_active_token?.jwt

  if (!jwt) {
    throw new Error(
      "Clerk did not return a session JWT after sign-in token redemption. " +
        "Check CLERK_FRONTEND_API_URL and that the publishable key matches your instance."
    )
  }

  return jwt as string
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

  // Step 2: Obtain an admin Bearer token for the Conduct API
  console.log("\n2. Obtaining admin Bearer token for Conduct API…")
  let adminToken: string

  try {
    adminToken = await getConductBearerToken(clerkIds.admin)
    console.log("  [auth] obtained Bearer token")
  } catch (err) {
    console.error("  [auth] ERROR:", err instanceof Error ? err.message : err)
    console.error(
      "\n  Hint: If running locally with Clerk disabled (no publishable key),\n" +
        "  set CONDUCT_ADMIN_TOKEN=<your-dev-token> and re-run setup.\n"
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
