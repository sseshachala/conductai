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

// ── Browser-based workspace setup ─────────────────────────────────────────

/**
 * Signs in as admin in a real browser, then makes all Conduct API calls
 * from inside page.evaluate() using the live Clerk session.
 * No JWT extraction — the browser owns the session throughout.
 */
async function setupWorkspaceViaBrowser(
  clerkIds: Record<RoleKey, string>
): Promise<string> {
  const appUrl = (process.env.CONDUCT_APP_URL ?? "http://localhost:3000").replace(/\/$/, "")
  const apiUrl = (process.env.CONDUCT_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

  console.log("  [browser] opening browser, signing in as admin…")
  const { stagehand, page } = await createBrowser(true)

  try {
    await signInWithPassword(page, TEST_USERS.admin.email, TEST_USERS.admin.password, appUrl)

    // Wait for Clerk to fully hydrate (session + token ready)
    await page.waitForTimeout(3000)

    // All API calls happen inside page.evaluate() — Clerk session is live here
    const result = await page.evaluate(
      async ({ apiUrl, workspaceName, members }) => {
        const win = window as typeof window & {
          Clerk?: { session?: { getToken(): Promise<string | null> } }
        }

        async function authFetch(path: string, opts: RequestInit = {}) {
          const token = await win.Clerk?.session?.getToken()
          if (!token) throw new Error("No Clerk session token available")
          const res = await fetch(`${apiUrl}${path}`, {
            ...opts,
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
              ...(opts.headers ?? {}),
            },
          })
          const body = await res.json().catch(() => ({}))
          if (!res.ok) throw new Error(`HTTP ${res.status} ${JSON.stringify(body)}`)
          return body
        }

        // Get or create the Acme workspace
        const projects = await authFetch("/projects")
        let workspaceId: string | null = null
        if (Array.isArray(projects)) {
          const existing = projects.find((p: { name: string }) => p.name === workspaceName)
          if (existing) workspaceId = existing.id
        }
        if (!workspaceId) {
          const created = await authFetch("/projects", {
            method: "POST",
            body: JSON.stringify({ name: workspaceName }),
          })
          workspaceId = created.id
        }

        // Add each member with their role
        const memberResults: string[] = []
        for (const { clerkId, role } of members) {
          try {
            await authFetch(`/projects/${workspaceId}/members`, {
              method: "POST",
              body: JSON.stringify({ clerk_user_id: clerkId, role }),
            })
            memberResults.push(`ok:${role}`)
          } catch (e) {
            memberResults.push(`warn:${role}:${e instanceof Error ? e.message : String(e)}`)
          }
        }

        return { workspaceId, memberResults }
      },
      {
        apiUrl,
        workspaceName: WORKSPACE_NAME,
        members: [
          { clerkId: clerkIds.dev1,     role: "editor" },
          { clerkId: clerkIds.dev2,     role: "editor" },
          { clerkId: clerkIds.security, role: "security" },
          { clerkId: clerkIds.viewer,   role: "viewer" },
        ],
      }
    )

    for (const r of result.memberResults) {
      if (r.startsWith("ok:")) console.log(`  [ok] added ${r.slice(3)}`)
      else console.warn(`  [warn] ${r.slice(5)}`)
    }

    return result.workspaceId as string
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

  // Steps 2-4: Sign in as admin in browser, create workspace, assign roles
  console.log("\n2. Signing in as admin + creating Acme workspace + assigning roles…")
  let workspaceId: string
  try {
    workspaceId = await setupWorkspaceViaBrowser(clerkIds)
    console.log(`  [ok] workspace ready: ${workspaceId}`)
  } catch (err) {
    console.error("  ERROR:", err instanceof Error ? err.message : err)
    process.exit(1)
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
  console.log("\n3. Wrote test-state.json")
  console.log("\n=== Setup complete. Run: npm test ===\n")
}

main().catch((err) => {
  console.error("\nSetup failed:", err)
  process.exit(1)
})
