// Shared accounts, Clerk/API helpers and per-test hooks for the security
// journey specs (journeys.*.spec.ts).
import { randomBytes } from "node:crypto"
import { test, expect, type Browser, type Page } from "@playwright/test"
import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright"
import { expectMcpInvocation } from "./mcp"

export type Account = { id: string; email: string; password: string }
export type Workspace = { id: string; name: string; owner_id: string }
export type Environment = { id: string; name: string }
export type Identity = { id: string; name: string }
export const createdUsers = new Set<string>()
export const attemptedEmails = new Set<string>()
export const prefix = `conduct-e2e-${Date.now()}-${randomBytes(4).toString("hex")}`
export const base = "http://localhost:3100"

export async function clerk(path: string, method: string, body?: unknown) {
  const response = await fetch(`https://api.clerk.com/v1${path}`, {
    signal: AbortSignal.timeout(20_000),
    method,
    headers: { Authorization: `Bearer ${process.env.CLERK_SECRET_KEY}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    const codes = (detail.errors ?? []).map((e: { code?: string }) => e.code ?? "unknown").filter((code: string) => /^[a-z_]+$/.test(code)).join(",")
    throw new Error(`Clerk test setup/cleanup failed: ${method} ${path.split("/")[1]} (${response.status}; ${codes})`)
  }
  return response.status === 204 ? null : response.json()
}

export async function account(role: string): Promise<Account> {
  const localPart = `${prefix}-${role}-${randomBytes(3).toString("hex")}+clerk_test`
  if (localPart.length > 64) throw new Error('Synthetic email local part is too long; shorten the fixture role')
  const email = `${localPart}@example.com`
  attemptedEmails.add(email)
  const password = randomBytes(24).toString("base64url") + "aA1!"
  const result = await clerk("/users", "POST", { email_address: [email], password })
  createdUsers.add(result.id)
  return { id: result.id, email, password }
}

export async function login(browser: Browser, user: Account, invitedWorkspace?: string) {
  const context = await browser.newContext({ baseURL: base })
  context.setDefaultTimeout(20_000)
  context.setDefaultNavigationTimeout(30_000)
  const page = await context.newPage()
  const authSteps: { step: string; status: number }[] = []
  const browserErrors: string[] = []
  page.on("pageerror", error => {
    // Only retain error names; messages can contain authentication URLs.
    browserErrors.push(error.name)
  })
  page.on("response", response => {
    const path = new URL(response.url()).pathname
    const step = path.startsWith('/v1/') ? path.replace(/\b(?:sess|user|org|orginv|sia|client)_[\w]+\b/g, ':id') : undefined
    if (step) authSteps.push({ step, status: response.status() })
  })
  try {
    await setupClerkTestingToken({ page })
    await page.goto("/sign-in")
    await page.getByLabel(/email address/i).fill(user.email)
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    await page.locator('input[name="password"]').fill(user.password)
    const prepared = page.waitForResponse(response => {
      const path = new URL(response.url()).pathname
      return /\/(prepare_second_factor|prepare_first_factor|send_email_code)$/.test(path) && response.request().method() === "POST"
    }, { timeout: 15_000 }).catch(() => null)
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    const otp = page.locator('input[autocomplete="one-time-code"]')
    await expect.poll(async () => {
      if (await otp.first().isVisible()) return true
      return page.evaluate(() => Boolean((window as any).Clerk?.session)).catch(() => false)
    }, { timeout: 20_000 }).toBe(true)
    if (await otp.first().isVisible()) {
      const sent = await prepared
      if (!sent?.ok()) throw new Error("Clerk did not confirm verification-code preparation")
      await verifyCode(page)
    }
    await expect.poll(async () => page.evaluate(() => Boolean((window as any).Clerk?.session)).catch(() => false), { timeout: 20_000 }).toBe(true)
    await finishClerkOnboarding(page, user.id, invitedWorkspace)
    return { context, page }
  } catch {
    const visible = await page.locator("body").innerText().catch(() => "unavailable")
    console.log("Login screen diagnostic:", visible.slice(0, 800))
    console.log("Authentication response statuses:", JSON.stringify(authSteps))
    console.log("Browser error names:", JSON.stringify(browserErrors))
    const state = await page.evaluate(() => {
      const clerk = (window as any).Clerk
      return {
        sessionStatus: clerk?.session?.status,
        task: clerk?.session?.currentTask?.key,
        hasActiveOrganization: Boolean(clerk?.organization),
        visibility: document.visibilityState,
        focused: document.hasFocus(),
        buttons: Array.from(document.querySelectorAll('button')).map(button => ({
          text: button.textContent?.trim().slice(0, 100), disabled: button.disabled,
        })),
      }
    }).catch(() => null)
    console.log('Clerk onboarding diagnostic:', JSON.stringify(state))
    await context.close().catch(() => {})
    throw new Error("Synthetic account browser login failed; credentials omitted from diagnostics")
  }
}

export async function verifyCode(page: Page) {
  const otp = page.locator('input[autocomplete="one-time-code"]')
  await expect(otp.first()).toBeVisible()
  if (await otp.count() === 1) await otp.fill("424242")
  else for (let i = 0; i < 6; i++) await otp.nth(i).fill("424242"[i])
}

export async function finishClerkOnboarding(page: Page, userId: string, invitedWorkspace?: string) {
  const organizationName = page.getByLabel('Name', { exact: true })
  const join = page.getByRole('button', { name: 'Join', exact: true })
  const existingOrganization = page.getByText(`${prefix}-onboarding-${userId}`, { exact: true })
  await expect.poll(async () => {
    const path = new URL(page.url()).pathname
    return !/^\/sign-(in|up)/.test(path) || await organizationName.isVisible() || await join.isVisible() || await existingOrganization.isVisible()
  }, { timeout: 20_000 }).toBe(true)
  if (await join.isVisible()) {
    if (!invitedWorkspace) throw new Error('Unexpected organization invitation during login')
    await expect(page.getByText(invitedWorkspace, { exact: true })).toBeVisible()
    await join.click()
    await expect(join).not.toBeVisible()
    if (/^\/sign-(in|up)/.test(new URL(page.url()).pathname)) {
      // Clerk includes the logo's alt text in the button's accessible name.
      // Match its exact visible label inside a button, not the invitation card.
      const organization = page.getByRole('button').filter({
        has: page.getByText(invitedWorkspace, { exact: true }),
      })
      await expect(organization).toHaveCount(1)
      await organization.click()
    }
  } else if (await existingOrganization.isVisible()) {
    await existingOrganization.click()
  } else if (await organizationName.isVisible()) {
    await organizationName.fill(`${prefix}-onboarding-${userId}`)
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
  }
  await page.waitForURL(url => !/^\/sign-(in|up)/.test(url.pathname), { waitUntil: 'domcontentloaded' })
}

export async function jwt(page: Page) {
  let token: string | null = null
  await expect.poll(async () => {
    token = await page.evaluate(async () => {
      const session = (window as any).Clerk?.session
      if (!session) return null
      let timer: ReturnType<typeof setTimeout> | undefined
      try {
        return await Promise.race([
          session.getToken({ skipCache: true }),
          new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 5_000) }),
        ])
      } finally { clearTimeout(timer) }
    }).catch(() => null)
    return Boolean(token)
  }, { timeout: 20_000, message: 'Clerk must issue a session token after navigation' }).toBe(true)
  if (!token) throw new Error("Clerk session did not issue a token")
  return token
}

export async function api(page: Page, path: string, method = "GET", body?: unknown, workspace?: string) {
  try { return await page.request.fetch(`${base}/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${await jwt(page)}`, ...(workspace ? { "X-Workspace-Id": workspace } : {}) },
    data: body,
  }) } catch { throw new Error(`Authenticated API transport failed (${method}); credentials omitted`) }
}

export async function workspace(page: Page, name: string) {
  const response = await api(page, "/projects", "POST", { name: `${prefix}-${name}` })
  expect(response.status()).toBe(201)
  return response.json() as Promise<Workspace>
}

export async function projects(page: Page): Promise<Workspace[]> {
  const response = await api(page, '/projects')
  expect(response.status()).toBe(200)
  return response.json()
}

export async function expectRole(page: Page, workspaceId: string, role: string) {
  const response = await api(page, `/projects/${workspaceId}/my-role`, 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  expect((await response.json()).role).toBe(role)
}

export async function members(page: Page, workspaceId: string) {
  const response = await api(page, `/projects/${workspaceId}/members`, 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as { clerk_user_id: string; role: string }[])
    .map(({ clerk_user_id, role }) => ({ clerk_user_id, role }))
    .sort((a, b) => a.clerk_user_id.localeCompare(b.clerk_user_id))
}

export async function environments(page: Page, workspaceId: string): Promise<Environment[]> {
  const response = await api(page, '/environments', 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Environment[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

export async function identities(page: Page, workspaceId: string): Promise<Identity[]> {
  const response = await api(page, `/workspaces/${workspaceId}/agent-identities`, 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Identity[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

export async function exchange(page: Page, workspaceId: string) {
  const subjectToken = await jwt(page)
  try {
    return await page.request.post(`${base}/api/oauth/token`, { form: {
      grant_type: 'urn:ietf:params:oauth:grant-type:token-exchange',
      subject_token: subjectToken, subject_token_type: 'urn:ietf:params:oauth:token-type:jwt', resource: workspaceId,
    } })
  } catch { throw new Error('OAuth transport failed; credentials omitted') }
}

export async function expectUsableToken(page: Page, workspaceId: string) {
  const response = await exchange(page, workspaceId)
  expect(response.status()).toBe(200)
  const issued = await response.json()
  expect(issued.workspace_id).toBe(workspaceId)
  // Assert booleans so a malformed credential cannot appear in test output.
  expect(typeof issued.access_token === 'string' && issued.access_token.startsWith('cond_agt_')).toBe(true)
  expect(typeof issued.refresh_token === 'string' && issued.refresh_token.startsWith('cond_ref_')).toBe(true)
  await expectMcpInvocation(page, `${base}/api/mcp?workspace_id=${workspaceId}`, issued.access_token)
}

export async function guardEvent(page: Page, accessToken: string, body: Record<string, unknown>) {
  return page.request.post(`${base}/api/guard/events`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: body,
  })
}

export async function signOut(page: Page) {
  await page.evaluate(() => (window as any).Clerk.signOut())
  await page.goto('/workflows')
  await expect(page).toHaveURL(/\/sign-in/)
}

export async function openWorkspaceMenu(page: Page) {
  await expect.poll(async () => (await page.context().cookies()).some(c => c.name === 'delegator_project_name')).toBe(true)
  const cookie = (await page.context().cookies()).find(c => c.name === 'delegator_project_name')!
  await page.getByText(decodeURIComponent(cookie.value), { exact: true }).first().click()
  await expect(page.getByRole('button', { name: 'New workspace' })).toBeVisible()
}

export async function switchWorkspace(page: Page, target: Workspace) {
  await openWorkspaceMenu(page)
  await page.getByText(target.name, { exact: true }).last().click()
  await expect.poll(async () => (await page.context().cookies()).find(c => c.name === 'delegator_project_id')?.value).toBe(target.id)
}

/**
 * Registers the database-role preflight, CSP diagnostics and Clerk cleanup
 * hooks on the calling spec file. Call once at the top level of each spec.
 */
export function registerJourneyHooks(): void {
  test.beforeAll(async ({ request }) => {
    const response = await request.get('/api/__e2e/database')
    expect(response.status()).toBe(200)
    const ownerMode = process.env.E2E_DATABASE_MODE === 'owner'
    expect(await response.json()).toEqual({
      role: ownerMode ? 'conduct_e2e_owner' : 'conduct_e2e_app',
      superuser: false, bypassrls: false, audit_rls_active: !ownerMode,
    })
    await clerkSetup({ dotenv: false })
  })
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      (window as any).__cspViolations = []
      document.addEventListener("securitypolicyviolation", event => {
        const uri = event.blockedURI
        let host = "inline-or-other"
        try { host = new URL(uri).hostname } catch { /* Not a network URL. */ }
        ;(window as any).__cspViolations.push({ directive: event.effectiveDirective, host })
      })
    })
  })
  test.afterEach(async ({ page }, info) => {
    if (info.status !== info.expectedStatus) {
      const violations = await page.evaluate(() => (window as any).__cspViolations ?? []).catch(() => [])
      console.log("CSP diagnostic (no credentials):", JSON.stringify(violations))
    }
  })
  test.afterEach(async () => {
    // Attempt every cleanup even when one deletion fails, then fail visibly.
    const errors: unknown[] = []
    for (const email of attemptedEmails) {
      try {
        const users = await clerk(`/users?email_address=${encodeURIComponent(email)}`, "GET")
        for (const user of users) createdUsers.add(user.id)
      } catch (error) { errors.push(error) }
    }
    // Discover only organizations attached to this run's synthetic users.
    const createdOrgs = new Set<string>()
    for (const id of createdUsers) {
      try {
        for (let offset = 0; ; offset += 100) {
          const memberships = await clerk(`/users/${id}/organization_memberships?limit=100&offset=${offset}`, "GET")
          for (const membership of memberships.data) {
            const org = membership.organization
            if (org.name?.startsWith(`${prefix}-`)) createdOrgs.add(org.id)
          }
          if (memberships.data.length < 100) break
        }
      } catch (error) { errors.push(error) }
    }
    for (const id of createdOrgs) {
      try { await clerk(`/organizations/${id}`, "DELETE") } catch (error) { errors.push(error) }
    }
    for (const id of createdUsers) {
      try { await clerk(`/users/${id}`, "DELETE") } catch (error) { errors.push(error) }
    }
    if (errors.length) throw new Error(`${errors.length} Clerk test cleanup operations failed; reconcile the ${prefix} test users/organizations`)
    console.log(`Cleaned up ${createdUsers.size} synthetic Clerk users and ${createdOrgs.size} test organizations`)
    createdUsers.clear()
    attemptedEmails.clear()
  })
}
