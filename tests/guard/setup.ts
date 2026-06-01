/**
 * Guard test harness setup script.
 *
 * Run this once before executing the test flows:
 *   npm run setup
 *
 * What it does:
 *   1. Creates 5 Clerk test users (upserts — safe to run again)
 *   2. Creates (or reuses) the Acme workspace and assigns roles via the
 *      test-only /test/workspace-setup endpoint (no browser auth required)
 *   3. Writes test-state.json with all IDs and credentials for the runner
 *
 * Environment variables required:
 *   CLERK_SECRET_KEY    — Clerk dashboard → API Keys → Secret key
 *   CONDUCT_API_URL     — e.g. http://localhost:8000
 *   TEST_SECRET         — shared secret configured on the API server
 */

import { writeFileSync } from "fs"
import { upsertClerkUser } from "./lib/clerk.js"

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

// ── Test API workspace setup ───────────────────────────────────────────────

async function setupWorkspace(clerkIds: Record<RoleKey, string>): Promise<string> {
  const apiUrl = (process.env.CONDUCT_API_URL ?? "http://localhost:8000").replace(/\/$/, "")
  const testSecret = process.env.TEST_SECRET
  if (!testSecret) throw new Error("TEST_SECRET env var is required for test setup")

  const res = await fetch(`${apiUrl}/test/workspace-setup`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Test-Secret": testSecret,
    },
    body: JSON.stringify({
      workspace_name: WORKSPACE_NAME,
      admin_clerk_user_id: clerkIds.admin,
      members: [
        { clerk_user_id: clerkIds.dev1,      role: "editor" },
        { clerk_user_id: clerkIds.dev2,      role: "editor" },
        { clerk_user_id: clerkIds.security,  role: "security" },
        { clerk_user_id: clerkIds.viewer,    role: "viewer" },
      ],
    }),
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Workspace setup failed: HTTP ${res.status} — ${body}`)
  }

  const data = await res.json() as { workspace_id: string; created: boolean }
  console.log(`  [ok] workspace ${data.created ? "created" : "reused"}: ${data.workspace_id}`)
  return data.workspace_id
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

  // Step 2: Create workspace and assign roles via test API
  console.log("\n2. Creating Acme workspace via test API…")
  let workspaceId: string
  try {
    workspaceId = await setupWorkspace(clerkIds)
  } catch (err) {
    console.error("  ERROR:", err instanceof Error ? err.message : err)
    process.exit(1)
  }

  // Step 3: Write test-state.json
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
  console.log("\n3. Wrote test-state.json")
  console.log("\n=== Setup complete. Run: npm test ===\n")
}

main().catch((err) => {
  console.error("\nSetup failed:", err)
  process.exit(1)
})
