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
import { chromium } from "playwright"
import { upsertClerkUser, createSignInToken } from "./lib/clerk.js"

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
 * Signs in as admin via Clerk sign-in token (bypasses 2FA), captures the
 * Bearer JWT from the first API request the Guard page makes, then uses
 * that token in plain Node.js fetch calls to create the workspace and members.
 * No page.evaluate() — avoids all TypeScript/esbuild browser injection issues.
 */
async function setupWorkspaceViaBrowser(
  clerkIds: Record<RoleKey, string>
): Promise<string> {
  const appUrl = (process.env.CONDUCT_APP_URL ?? "http://localhost:3000").replace(/\/$/, "")
  const apiUrl = (process.env.CONDUCT_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

  console.log("  [browser] opening browser to capture auth token…")
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
  const page = await context.newPage()
  let capturedToken: string | null = null

  try {
    // Intercept ALL outgoing requests and grab the first Bearer token we see
    await page.route("**/*", async (route) => {
      const auth = route.request().headers()["authorization"] ?? ""
      if (auth.startsWith("Bearer ") && !capturedToken) {
        capturedToken = auth.slice(7)
        console.log("  [auth] Bearer token captured from network request")
      }
      await route.continue()
    })

    // Clerk sign-in token bypasses 2FA — navigate browser to the ticket URL
    const { url: ticketUrl } = await createSignInToken(clerkIds.admin, `${appUrl}/guard`)
    console.log("  [auth] navigating to Clerk ticket URL (bypasses 2FA)…")
    await page.goto(ticketUrl, { waitUntil: "networkidle" })

    // Wait up to 15 s for the Guard page to make an authenticated API call
    const deadline = Date.now() + 15_000
    while (!capturedToken && Date.now() < deadline) {
      await page.waitForTimeout(300)
    }
    if (!capturedToken) throw new Error(
      "No Bearer token observed after sign-in. " +
      "Check CONDUCT_APP_URL and that the Guard page makes API calls on load."
    )
  } finally {
    await browser.close()
  }

  // ── All remaining steps use plain Node.js fetch with the captured token ──

  async function apiFetch(path: string, opts: RequestInit = {}): Promise<unknown> {
    const res = await fetch(`${apiUrl}${path}`, {
      ...opts,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${capturedToken}`,
        ...(opts.headers ?? {}),
      },
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(`HTTP ${res.status} on ${path}: ${JSON.stringify(body)}`)
    return body
  }

  // Create or reuse the Acme workspace
  console.log("\n3. Creating Acme workspace…")
  const projects = await apiFetch("/projects") as Array<{ id: string; name: string }>
  let workspaceId: string | null = null
  if (Array.isArray(projects)) {
    const existing = projects.find((p) => p.name === WORKSPACE_NAME)
    if (existing) {
      workspaceId = existing.id
      console.log(`  [ok] reusing existing workspace: ${workspaceId}`)
    }
  }
  if (!workspaceId) {
    const created = await apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify({ name: WORKSPACE_NAME }),
    }) as { id: string }
    workspaceId = created.id
    console.log(`  [ok] created workspace: ${workspaceId}`)
  }

  // Add members
  console.log("\n4. Assigning roles…")
  for (const [key, clerkId, role] of [
    ["dev1",     clerkIds.dev1,     "editor"],
    ["dev2",     clerkIds.dev2,     "editor"],
    ["security", clerkIds.security, "security"],
    ["viewer",   clerkIds.viewer,   "viewer"],
  ] as [string, string, string][]) {
    try {
      await apiFetch(`/projects/${workspaceId}/members`, {
        method: "POST",
        body: JSON.stringify({ clerk_user_id: clerkId, role }),
      })
      console.log(`  [ok] ${key} → ${role}`)
    } catch (err) {
      console.warn(`  [warn] ${key}: ${err instanceof Error ? err.message : err}`)
    }
  }

  return workspaceId
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
