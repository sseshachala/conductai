// Canonical role list and matching Clerk sandbox test users. Emails must
// exist in the Clerk instance (dashboard → Users) and the same emails must
// have workspace_users rows seeded by apps/api/scripts/seed_e2e_workspace.py.
//
// The Clerk user IDs are surfaced to the API via CLERK_TEST_USER_* env vars
// so the seed script can build the mapping (see the CLI job in web-smoke.yml).

export type Role = "admin" | "security" | "developer" | "viewer"

export const ROLES: Role[] = ["admin", "security", "developer", "viewer"]

export interface RoleAccount {
  email: string
  password: string
}

// One password across the board keeps the config boring. Override via env
// if you rotate — CLERK_TEST_PASSWORD wins if set.
const { env } = process
const DEFAULT_PASSWORD = env.CLERK_TEST_PASSWORD || "E2eTests!2026"

export const ROLE_ACCOUNTS: Record<Role, RoleAccount> = {
  admin:     { email: "admin@example.com",     password: DEFAULT_PASSWORD },
  security:  { email: "security@example.com",  password: DEFAULT_PASSWORD },
  developer: { email: "developer@example.com", password: DEFAULT_PASSWORD },
  viewer:    { email: "viewer@example.com",    password: DEFAULT_PASSWORD },
}

export function storageStatePath(role: Role): string {
  return `.auth/${role}.json`
}
