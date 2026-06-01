/**
 * Conduct API helpers.
 *
 * Requires CONDUCT_API_URL in the environment (default: http://localhost:8000).
 * All mutation calls require a Bearer token obtained from Clerk.
 */

export type GuardRole = "admin" | "editor" | "security" | "viewer"

function apiBase(): string {
  return (process.env.CONDUCT_API_URL ?? "http://localhost:8000").replace(/\/$/, "")
}

function authHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  }
}

/**
 * Creates a new workspace (project) named "Guard Test Workspace".
 * If one already exists with that name, returns its ID instead.
 * Returns the workspace ID string.
 */
export async function getOrCreateTestWorkspace(adminToken: string, name = "Acme"): Promise<string> {
  const base = apiBase()

  // List existing projects first so we can reuse one if it exists
  const listRes = await fetch(`${base}/projects`, {
    headers: authHeaders(adminToken),
  })

  if (listRes.ok) {
    const projects = await listRes.json()
    const existing = Array.isArray(projects)
      ? projects.find((p: { name: string }) => p.name === name)
      : null
    if (existing) {
      console.log(`  [conduct] reusing workspace: ${existing.id}`)
      return existing.id as string
    }
  }

  const createRes = await fetch(`${base}/projects`, {
    method: "POST",
    headers: authHeaders(adminToken),
    body: JSON.stringify({ name }),
  })

  if (!createRes.ok) {
    const body = await createRes.text()
    throw new Error(`Failed to create workspace: HTTP ${createRes.status} — ${body}`)
  }

  const project = await createRes.json()
  console.log(`  [conduct] created workspace: ${project.id}`)
  return project.id as string
}

/**
 * Adds a member to a workspace with the given role.
 * Uses the /projects/{workspaceId}/members endpoint.
 * Idempotent — updates role if member already exists.
 */
export async function addMemberWithRole(
  adminToken: string,
  workspaceId: string,
  clerkUserId: string,
  role: GuardRole
): Promise<void> {
  const base = apiBase()

  const res = await fetch(`${base}/projects/${workspaceId}/members`, {
    method: "POST",
    headers: authHeaders(adminToken),
    body: JSON.stringify({ clerk_user_id: clerkUserId, role }),
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to add member ${clerkUserId} as ${role}: HTTP ${res.status} — ${body}`
    )
  }

  console.log(`  [conduct] added member ${clerkUserId} as ${role} to workspace ${workspaceId}`)
}

/**
 * Sets the delegator_project_id cookie on the page so the app loads the
 * correct workspace without going through the workspace switcher UI.
 *
 * Call this after login, before navigating to /guard.
 */
export async function setWorkspaceCookie(
  // Accept any page-like object with setCookie support
  page: { context: () => { addCookies: (cookies: unknown[]) => Promise<void> } },
  workspaceId: string,
  appUrl: string
): Promise<void> {
  const url = new URL(appUrl)
  await page.context().addCookies([
    {
      name: "delegator_project_id",
      value: workspaceId,
      domain: url.hostname,
      path: "/",
      httpOnly: false,
      secure: url.protocol === "https:",
      sameSite: "Lax" as const,
    },
  ])
}

/**
 * Fetches the member list for a workspace and returns the role for a given Clerk user ID.
 * Returns null if the user is not a member.
 */
export async function getMemberRole(
  token: string,
  workspaceId: string,
  clerkUserId: string
): Promise<GuardRole | null> {
  const base = apiBase()

  const res = await fetch(`${base}/projects/${workspaceId}/members`, {
    headers: authHeaders(token),
  })

  if (!res.ok) return null

  const members = await res.json()
  if (!Array.isArray(members)) return null

  const member = members.find(
    (m: { clerk_user_id: string; role: string }) => m.clerk_user_id === clerkUserId
  )
  return (member?.role as GuardRole) ?? null
}
