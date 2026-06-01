/**
 * Clerk Management API helpers.
 *
 * Requires CLERK_SECRET_KEY in the environment.
 * All requests go to https://api.clerk.com/v1 using the backend secret key.
 */

const CLERK_API = "https://api.clerk.com/v1"

function clerkHeaders(): Record<string, string> {
  const key = process.env.CLERK_SECRET_KEY
  if (!key) throw new Error("CLERK_SECRET_KEY is not set in the environment")
  return {
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  }
}

export interface ClerkUser {
  id: string
  email: string
  password: string
}

/**
 * Creates a Clerk user with the given email and password.
 * Returns the Clerk user ID (e.g. "user_abc123").
 */
export async function createClerkUser(
  email: string,
  password: string
): Promise<string> {
  const res = await fetch(`${CLERK_API}/users`, {
    method: "POST",
    headers: clerkHeaders(),
    body: JSON.stringify({
      email_address: [email],
      password,
      skip_password_checks: false,
      skip_password_requirement: false,
    }),
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Failed to create Clerk user ${email}: HTTP ${res.status} — ${body}`)
  }

  const data = await res.json()
  return data.id as string
}

/**
 * Deletes a Clerk user by their user ID.
 * Idempotent — ignores 404 (already deleted).
 */
export async function deleteClerkUser(clerkUserId: string): Promise<void> {
  const res = await fetch(`${CLERK_API}/users/${clerkUserId}`, {
    method: "DELETE",
    headers: clerkHeaders(),
  })

  if (res.status === 404) return // already gone
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Failed to delete Clerk user ${clerkUserId}: HTTP ${res.status} — ${body}`)
  }
}

/**
 * Creates a sign-in token for the given user ID.
 * Returns a short-lived token that can be redeemed in the browser via
 * the Clerk hosted sign-in or the __clerk_ticket query parameter.
 *
 * Note: Clerk sign-in tokens are linked to a user ID, not credentials.
 * To get a user ID from email, first call findClerkUserByEmail().
 */
export async function createSignInToken(clerkUserId: string): Promise<string> {
  const res = await fetch(`${CLERK_API}/sign_in_tokens`, {
    method: "POST",
    headers: clerkHeaders(),
    body: JSON.stringify({
      user_id: clerkUserId,
      expires_in_seconds: 300, // 5 minutes — enough for a single test flow
    }),
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to create sign-in token for ${clerkUserId}: HTTP ${res.status} — ${body}`
    )
  }

  const data = await res.json()
  return data.token as string
}

/**
 * Lists Clerk users whose primary email starts with the given prefix.
 * Useful for finding existing test users before creating duplicates.
 */
export async function listClerkUsers(emailPrefix: string): Promise<ClerkUser[]> {
  const params = new URLSearchParams({ email_address: emailPrefix, limit: "50" })
  const res = await fetch(`${CLERK_API}/users?${params}`, {
    headers: clerkHeaders(),
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Failed to list Clerk users: HTTP ${res.status} — ${body}`)
  }

  const data = await res.json()
  // Clerk returns an array directly for this endpoint
  const users = Array.isArray(data) ? data : (data.data ?? [])

  return users.map((u: { id: string; email_addresses: Array<{ email_address: string }> }) => ({
    id: u.id,
    email: u.email_addresses?.[0]?.email_address ?? "",
    password: "", // passwords are write-only — not returned by the API
  }))
}

/**
 * Finds a Clerk user by exact email address.
 * Returns null if not found.
 */
export async function findClerkUserByEmail(email: string): Promise<ClerkUser | null> {
  const users = await listClerkUsers(email)
  const match = users.find((u) => u.email === email)
  return match ?? null
}

/**
 * Creates a Clerk user only if one with that email does not already exist.
 * Returns the Clerk user ID in either case.
 */
export async function upsertClerkUser(
  email: string,
  password: string
): Promise<string> {
  const existing = await findClerkUserByEmail(email)
  if (existing) {
    console.log(`  [clerk] user already exists: ${email} (${existing.id})`)
    return existing.id
  }
  const id = await createClerkUser(email, password)
  console.log(`  [clerk] created user: ${email} (${id})`)
  return id
}
