// Canonical role list and matching Clerk sandbox test users. Emails must
// exist in the Clerk instance (dashboard → Users) and the same emails must
// have workspace_users rows seeded by apps/api/scripts/seed_e2e_workspace.py.
//
// Passwords are per-role, loaded from env (from .env.test locally, from GH
// secrets in CI). Env var name is just the role name so it matches the
// user-visible .env.test format.

export type Role = "admin" | "security" | "developer" | "viewer"

export const ROLES: Role[] = ["admin", "security", "developer", "viewer"]

export interface RoleAccount {
  email: string
  password: string
}

const { env } = process

function passwordFor(role: Role): string {
  const pw = env[role]
  if (!pw) {
    throw new Error(
      `Missing Clerk sandbox password for role '${role}'. Set env var '${role}' ` +
      `in .env.test (local) or GH secret CLERK_TEST_PASSWORD_${role.toUpperCase()} (CI).`
    )
  }
  return pw
}

export const ROLE_ACCOUNTS: Record<Role, RoleAccount> = {
  admin:     { email: "admin@example.com",     password: passwordFor("admin") },
  security:  { email: "security@example.com",  password: passwordFor("security") },
  developer: { email: "developer@example.com", password: passwordFor("developer") },
  viewer:    { email: "viewer@example.com",    password: passwordFor("viewer") },
}

export function storageStatePath(role: Role): string {
  return `.auth/${role}.json`
}
