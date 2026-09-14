import { randomBytes } from "node:crypto"
import { test, expect, type Browser, type BrowserContext, type Page } from "@playwright/test"
import { clerkSetup, setupClerkTestingToken } from "@clerk/testing/playwright"

type Account = { id: string; email: string; password: string }
type Workspace = { id: string; name: string; owner_id: string }
type Environment = { id: string; name: string }
type Identity = { id: string; name: string }
const createdUsers = new Set<string>()
const attemptedEmails = new Set<string>()
const prefix = `conduct-e2e-${Date.now()}-${randomBytes(4).toString("hex")}`
const base = "http://localhost:3100"

async function clerk(path: string, method: string, body?: unknown) {
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

async function account(role: string): Promise<Account> {
  const localPart = `${prefix}-${role}-${randomBytes(3).toString("hex")}+clerk_test`
  if (localPart.length > 64) throw new Error('Synthetic email local part is too long; shorten the fixture role')
  const email = `${localPart}@example.com`
  attemptedEmails.add(email)
  const password = randomBytes(24).toString("base64url") + "aA1!"
  const result = await clerk("/users", "POST", { email_address: [email], password })
  createdUsers.add(result.id)
  return { id: result.id, email, password }
}

async function login(browser: Browser, user: Account, invitedWorkspace?: string) {
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

async function verifyCode(page: Page) {
  const otp = page.locator('input[autocomplete="one-time-code"]')
  await expect(otp.first()).toBeVisible()
  if (await otp.count() === 1) await otp.fill("424242")
  else for (let i = 0; i < 6; i++) await otp.nth(i).fill("424242"[i])
}

async function finishClerkOnboarding(page: Page, userId: string, invitedWorkspace?: string) {
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

async function jwt(page: Page) {
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

async function api(page: Page, path: string, method = "GET", body?: unknown, workspace?: string) {
  try { return await page.request.fetch(`${base}/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${await jwt(page)}`, ...(workspace ? { "X-Workspace-Id": workspace } : {}) },
    data: body,
  }) } catch { throw new Error(`Authenticated API transport failed (${method}); credentials omitted`) }
}

async function workspace(page: Page, name: string) {
  const response = await api(page, "/projects", "POST", { name: `${prefix}-${name}` })
  expect(response.status()).toBe(201)
  return response.json() as Promise<Workspace>
}

async function projects(page: Page): Promise<Workspace[]> {
  const response = await api(page, '/projects')
  expect(response.status()).toBe(200)
  return response.json()
}

async function expectRole(page: Page, workspaceId: string, role: string) {
  const response = await api(page, `/projects/${workspaceId}/my-role`, 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  expect((await response.json()).role).toBe(role)
}

async function members(page: Page, workspaceId: string) {
  const response = await api(page, `/projects/${workspaceId}/members`, 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as { clerk_user_id: string; role: string }[])
    .map(({ clerk_user_id, role }) => ({ clerk_user_id, role }))
    .sort((a, b) => a.clerk_user_id.localeCompare(b.clerk_user_id))
}

async function environments(page: Page, workspaceId: string): Promise<Environment[]> {
  const response = await api(page, '/environments', 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Environment[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function identities(page: Page, workspaceId: string): Promise<Identity[]> {
  const response = await api(page, `/workspaces/${workspaceId}/agent-identities`, 'GET', undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Identity[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function exchange(page: Page, workspaceId: string) {
  const subjectToken = await jwt(page)
  try {
    return await page.request.post(`${base}/api/oauth/token`, { form: {
      grant_type: 'urn:ietf:params:oauth:grant-type:token-exchange',
      subject_token: subjectToken, subject_token_type: 'urn:ietf:params:oauth:token-type:jwt', resource: workspaceId,
    } })
  } catch { throw new Error('OAuth transport failed; credentials omitted') }
}

async function expectUsableToken(page: Page, workspaceId: string) {
  const response = await exchange(page, workspaceId)
  expect(response.status()).toBe(200)
  const issued = await response.json()
  expect(issued.workspace_id).toBe(workspaceId)
  // Assert booleans so a malformed credential cannot appear in test output.
  expect(typeof issued.access_token === 'string' && issued.access_token.startsWith('cond_agt_')).toBe(true)
  expect(typeof issued.refresh_token === 'string' && issued.refresh_token.startsWith('cond_ref_')).toBe(true)
  let mcp
  try {
    mcp = await page.request.post(`${base}/api/guard/mcp?workspace_id=${workspaceId}`, {
      headers: { Authorization: `Bearer ${issued.access_token}` },
      data: { jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} },
    })
  } catch { throw new Error('MCP transport failed; credentials omitted') }
  expect(mcp.status()).toBe(200)
  expect(Array.isArray((await mcp.json()).result?.tools)).toBe(true)
}

async function guardEvent(page: Page, accessToken: string, body: Record<string, unknown>) {
  return page.request.post(`${base}/api/guard/events`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: body,
  })
}

async function signOut(page: Page) {
  await page.evaluate(() => (window as any).Clerk.signOut())
  await page.goto('/workflows')
  await expect(page).toHaveURL(/\/sign-in/)
}

async function openWorkspaceMenu(page: Page) {
  await expect.poll(async () => (await page.context().cookies()).some(c => c.name === 'delegator_project_name')).toBe(true)
  const cookie = (await page.context().cookies()).find(c => c.name === 'delegator_project_name')!
  await page.getByText(decodeURIComponent(cookie.value), { exact: true }).first().click()
  await expect(page.getByRole('button', { name: 'New workspace' })).toBeVisible()
}

async function switchWorkspace(page: Page, target: Workspace) {
  await openWorkspaceMenu(page)
  await page.getByText(target.name, { exact: true }).last().click()
  await expect.poll(async () => (await page.context().cookies()).find(c => c.name === 'delegator_project_id')?.value).toBe(target.id)
}

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

test("@smoke ingress discards forged client IP headers and API requires authentication", async ({ request }) => {
  const plain = await request.get("/api/__e2e/peer")
  expect(plain.status()).toBe(200)
  const expected = (await plain.json()).effective
  for (const forwarded of ["198.51.100.77", "198.51.100.77, 10.0.0.5", ",,,", "not-an-ip"]) {
    const response = await request.get("/api/__e2e/peer", { headers: { "X-Forwarded-For": forwarded } })
    expect(response.status()).toBe(200)
    expect((await response.json()).effective).toBe(expected)
  }
  expect((await request.get("/api/projects")).status()).toBe(401)
})

test("@baseline signup provisions owner membership before usable token issuance", async ({ page }) => {
  await page.context().addCookies([{ name: 'delegator_project_id', value: '00000000-0000-0000-0000-000000000001', url: base }])
  let projectRequests = 0
  const authenticatedProjectRequests: boolean[] = []
  await page.route('**/api/projects', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    authenticatedProjectRequests.push(Boolean(route.request().headers().authorization))
    if (++projectRequests === 1) return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Session refreshing"}' })
    return route.continue()
  })
  const trialLoaded = page.waitForResponse(response => new URL(response.url()).pathname === '/api/guard/trial/session', { timeout: 90_000 })
  const email = `${prefix}-signup+clerk_test@example.com`
  attemptedEmails.add(email)
  const password = randomBytes(24).toString("base64url") + "aA1!"
  await setupClerkTestingToken({ page })
  await page.goto("/sign-up")
  await page.getByLabel(/email address/i).fill(email)
  try { await page.locator('input[name="password"]').fill(password) }
  catch { throw new Error("Signup password field unavailable; credentials omitted") }
  await page.getByRole("button", { name: "Continue", exact: true }).click()
  await verifyCode(page)
  await expect.poll(async () => page.evaluate(() => (window as any).Clerk?.user?.id || null)).not.toBeNull()
  const id = await page.evaluate(() => (window as any).Clerk.user.id)
  createdUsers.add(id)
  await finishClerkOnboarding(page, id)
  const trialResponse = await trialLoaded
  expect(trialResponse.status()).toBe(200)
  expect(Boolean((await trialResponse.json()).token)).toBe(true)
  for (const title of ['Allow', 'Warn', 'Block', 'Prove']) {
    await expect(page.getByText(title, { exact: true })).toBeVisible()
  }
  expect(authenticatedProjectRequests.length).toBeGreaterThanOrEqual(2)
  expect(authenticatedProjectRequests.every(Boolean)).toBe(true)
  await expect(page.getByText(/session load failed/i)).not.toBeVisible()
  const workspaces = await projects(page)
  expect(workspaces.length).toBeGreaterThan(0)
  expect(workspaces.every(project => project.owner_id === id)).toBe(true)
  const ws = workspaces[0]
  await expectRole(page, ws.id, 'admin')
  const before = await members(page, ws.id)
  expect(before).toEqual([{ clerk_user_id: id, role: 'admin' }])
  await expectUsableToken(page, ws.id)
  expect(await members(page, ws.id)).toEqual(before)
})

test('@baseline returning-user login preserves membership and token access', async ({ browser }) => {
  const owner = await account('returning')
  const contexts: BrowserContext[] = []
  try {
    const first = await login(browser, owner); contexts.push(first.context)
    const ws = await workspace(first.page, 'returning')
    const before = await members(first.page, ws.id)
    await expectRole(first.page, ws.id, 'admin')
    await expectUsableToken(first.page, ws.id)
    await signOut(first.page)
    const next = await login(browser, owner); contexts.push(next.context)
    expect((await projects(next.page)).some(p => p.id === ws.id)).toBe(true)
    expect(await members(next.page, ws.id)).toEqual(before)
    await expectUsableToken(next.page, ws.id)
    expect(await members(next.page, ws.id)).toEqual(before)
    await signOut(next.page)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@baseline workspace creation through UI provisions admin without losing existing access', async ({ browser }) => {
  const owner = await account('creator')
  const session = await login(browser, owner)
  try {
    const original = (await projects(session.page))[0]
    const before = await members(session.page, original.id)
    await session.page.goto('/workflows')
    await openWorkspaceMenu(session.page)
    await session.page.getByRole('button', { name: 'New workspace' }).click()
    const name = `${prefix}-created-in-ui`
    await session.page.getByPlaceholder('Workspace name', { exact: true }).fill(name)
    const created = session.page.waitForResponse(response =>
      new URL(response.url()).pathname === '/api/projects' && response.request().method() === 'POST')
    await session.page.getByPlaceholder('Workspace name', { exact: true }).press('Enter')
    const response = await created
    expect(response.status()).toBe(201)
    const ws = await response.json() as Workspace
    expect(ws.name).toBe(name)
    expect(ws.owner_id).toBe(owner.id)
    const listed = await projects(session.page)
    expect(listed.filter(p => p.name === name)).toHaveLength(1)
    expect(listed.some(p => p.id === original.id)).toBe(true)
    await expectRole(session.page, ws.id, 'admin')
    const newMembers = await members(session.page, ws.id)
    expect(newMembers).toEqual([{ clerk_user_id: owner.id, role: 'admin' }])
    await expectUsableToken(session.page, ws.id)
    expect(await members(session.page, ws.id)).toEqual(newMembers)
    await expectUsableToken(session.page, original.id)
    expect(await members(session.page, original.id)).toEqual(before)
  } finally { await session.context.close() }
})

test("@baseline workspace switching preserves roles and authorized OAuth/MCP access", async ({ browser }) => {
  const ownerA = await account("owner-a")
  const ownerB = await account("owner-b")
  const member = await account("member")
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, "tenant-a")
    const wb = await workspace(b.page, "tenant-b")
    const addA = await api(a.page, `/projects/${wa.id}/members`, "POST", { clerk_user_id: member.id, role: "developer" }, wa.id)
    expect(addA.status()).toBe(201)
    const m = await login(browser, member); contexts.push(m.context)
    const memberships = await projects(m.page)
    expect(memberships.some((p: { id: string }) => p.id === wa.id)).toBe(true)
    expect(memberships.some((p: { id: string }) => p.id === wb.id)).toBe(false)
    const addB = await api(b.page, `/projects/${wb.id}/members`, "POST", { clerk_user_id: member.id, role: "viewer" }, wb.id)
    expect(addB.status()).toBe(201)
    const beforeA = await members(a.page, wa.id)
    const beforeB = await members(b.page, wb.id)
    await m.page.goto("/workflows")
    for (const target of [wa, wb]) {
      await switchWorkspace(m.page, target)
      await expectUsableToken(m.page, target.id)
    }
    for (const [ws, role] of [[wa.id, "developer"], [wb.id, "viewer"]]) {
      await expectRole(m.page, ws, role)
    }
    expect(await members(a.page, wa.id)).toEqual(beforeA)
    expect(await members(b.page, wb.id)).toEqual(beforeB)
    await signOut(m.page)
  } finally {
    await Promise.all(contexts.map(context => context.close()))
  }
})

for (const returning of [true, false]) {
test(`${returning ? '@baseline' : '@onboarding'} invitation acceptance for ${returning ? 'existing' : 'first-login'} user`, async ({ browser }) => {
  const owner = await account("inviter")
  const member = await account("invitee")
  const contexts: BrowserContext[] = []
  try {
    if (returning) {
      const prior = await login(browser, member); contexts.push(prior.context)
      await projects(prior.page)
      await signOut(prior.page)
    }
    const a = await login(browser, owner); contexts.push(a.context)
    const ws = await workspace(a.page, "invitation")
    const invite = await api(a.page, `/projects/${ws.id}/members`, "POST", { email: member.email, role: "developer" }, ws.id)
    expect(invite.status()).toBe(201)
    const pending = await api(a.page, `/projects/${ws.id}/invites`, 'GET', undefined, ws.id)
    expect(pending.status()).toBe(200)
    expect((await pending.json()).some((i: { invited_email: string }) => i.invited_email === member.email)).toBe(true)
    expect((await members(a.page, ws.id)).some(m => m.clerk_user_id === member.id)).toBe(false)
    const m = await login(browser, member, ws.name); contexts.push(m.context)
    if (!returning) {
      await expect.poll(() => m.page.evaluate(() => {
        const clerk = (window as any).Clerk
        return {
          status: clerk?.session?.status,
          task: clerk?.session?.currentTask?.key ?? null,
          organization: clerk?.organization?.name,
        }
      }).catch(() => null), { timeout: 20_000 }).toEqual({
        status: 'active', task: null, organization: ws.name,
      })
    }
    expect((await projects(m.page)).some(p => p.id === ws.id)).toBe(true)
    await expectRole(m.page, ws.id, 'developer')
    const accepted = await api(a.page, `/projects/${ws.id}/invites`, 'GET', undefined, ws.id)
    expect(accepted.status()).toBe(200)
    expect((await accepted.json()).some((i: { invited_email: string }) => i.invited_email === member.email)).toBe(false)
    const before = await members(a.page, ws.id)
    expect(before.filter(m => m.clerk_user_id === member.id)).toEqual([{ clerk_user_id: member.id, role: 'developer' }])
    await expectUsableToken(m.page, ws.id)
    expect(await members(a.page, ws.id)).toEqual(before)
  } finally {
    await Promise.all(contexts.map(context => context.close()))
  }
})
}

for (const boundary of ['outsider-token', 'identity-path'] as const) {
test(`@security ${boundary} rejects an unrelated workspace`, async ({ browser }) => {
  const ownerA = await account('outsider-a')
  const ownerB = await account('outsider-b')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'isolated-a')
    const wb = await workspace(b.page, 'isolated-b')
    const before = await members(b.page, wb.id)
    expect(before.some(m => m.clerk_user_id === ownerA.id)).toBe(false)
    expect((await projects(a.page)).some(p => p.id === wb.id)).toBe(false)
    const response = boundary === 'outsider-token'
      ? await exchange(a.page, wb.id)
      : await api(a.page, `/workspaces/${wb.id}/agent-identities`, 'GET', undefined, wa.id)
    expect.soft([403, 404], `${boundary} must deny unrelated workspace access`).toContain(response.status())
    expect.soft(await members(b.page, wb.id), 'Denied access must not enroll an outsider').toEqual(before)
    if (boundary === 'identity-path') {
      const root = `/workspaces/${wb.id}`
      const created = await api(b.page, `${root}/agent-identities`, 'POST', { name: `${prefix}-protected` }, wb.id)
      expect(created.status()).toBe(201)
      const identityId = (await created.json()).id as string
      const original = await api(b.page, `${root}/agent-identities`, 'GET', undefined, wb.id)
      expect(original.status()).toBe(200)
      const identities = await original.json()
      const attacks: [string, string, unknown][] = [
        [`${root}/agent-identities`, 'POST', { name: 'unauthorized' }],
        [`${root}/agent-identities/${identityId}`, 'PATCH', { risk_tier: 'tier_3' }],
        [`${root}/agent-identities/${identityId}/regenerate`, 'POST', undefined],
        [`${root}/agent-identities/${identityId}`, 'DELETE', undefined],
        [`${root}/api-tokens`, 'POST', { name: 'unauthorized' }],
      ]
      for (const [path, method, body] of attacks) {
        const denied = await api(a.page, path, method, body, wa.id)
        expect.soft(denied.status(), `${method} must reject a conflicting workspace path`).toBe(403)
      }
      const after = await api(b.page, `${root}/agent-identities`, 'GET', undefined, wb.id)
      expect(after.status()).toBe(200)
      expect(await after.json()).toEqual(identities)
    }
  } finally { await Promise.all(contexts.map(context => context.close())) }
})
}

test('@security removed member cannot refresh or obtain new workspace credentials', async ({ browser }) => {
  const owner = await account('revoke-a')
  const member = await account('revoke-b')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, owner); contexts.push(a.context)
    const m = await login(browser, member); contexts.push(m.context)
    const ws = await workspace(a.page, 'refresh-revocation')
    const added = await api(a.page, `/projects/${ws.id}/members`, 'POST', { clerk_user_id: member.id, role: 'developer' }, ws.id)
    expect(added.status()).toBe(201)
    const issued = await exchange(m.page, ws.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()
    let rotated
    try {
      rotated = await m.page.request.post(`${base}/api/oauth/token`, { form: {
        grant_type: 'refresh_token', refresh_token: pair.refresh_token,
      } })
    } catch { throw new Error('OAuth refresh transport failed; credentials omitted') }
    expect(rotated.status()).toBe(200)
    const current = await rotated.json()
    const removed = await api(a.page, `/projects/${ws.id}/members/${member.id}`, 'DELETE', undefined, ws.id)
    expect(removed.status()).toBe(204)
    const before = await members(a.page, ws.id)
    expect(before.some(row => row.clerk_user_id === member.id)).toBe(false)
    for (const endpoint of ['oauth', 'cli']) {
      let denied
      try {
        denied = endpoint === 'oauth'
          ? await m.page.request.post(`${base}/api/oauth/token`, { form: {
            grant_type: 'refresh_token', refresh_token: current.refresh_token,
          } })
          : await m.page.request.post(`${base}/api/auth/refresh`, { data: { refresh_token: current.refresh_token } })
      } catch { throw new Error('Refresh transport failed; credentials omitted') }
      expect([401, 403]).toContain(denied.status())
      expect(await members(a.page, ws.id)).toEqual(before)
    }
    expect((await exchange(m.page, ws.id)).status()).toBe(403)
    expect(await members(a.page, ws.id)).toEqual(before)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary account owns a distinct disposable workspace', async ({ browser }) => {
  const owner = await account('cown')
  const session = await login(browser, owner)
  try {
    const ws = await workspace(session.page, 'canary-owned')
    expect(ws.owner_id).toBe(owner.id)
    expect((await projects(session.page)).filter(project => project.id === ws.id)).toEqual([ws])
  } finally { await session.context.close() }
})

test('@prod-canary anonymous forged forwarding headers do not authenticate', async ({ request }) => {
  const response = await request.get('/api/projects', { headers: {
    'X-Workspace-Id': crypto.randomUUID(),
    'X-Forwarded-For': '127.0.0.1',
    'X-Real-IP': '127.0.0.1',
    'X-Forwarded-Proto': 'https',
  } })
  expect(response.status()).toBe(401)
})

test('@prod-canary owner token lists MCP tools only for its workspace', async ({ browser }) => {
  const owner = await account('cmcp')
  const session = await login(browser, owner)
  try {
    const ws = await workspace(session.page, 'canary-mcp')
    await expectUsableToken(session.page, ws.id)
  } finally { await session.context.close() }
})

test('@prod-canary foreign and unknown workspaces cannot issue credentials', async ({ browser }) => {
  const ownerA = await account('cia')
  const ownerB = await account('cib')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-issue-a')
    const wb = await workspace(b.page, 'canary-issue-b')
    const identitiesA = await identities(a.page, wa.id)
    const identitiesB = await identities(b.page, wb.id)
    const membersB = await members(b.page, wb.id)

    expect((await exchange(a.page, wb.id)).status()).toBe(403)
    expect((await exchange(a.page, crypto.randomUUID())).status()).toBe(403)
    expect(await identities(a.page, wa.id)).toEqual(identitiesA)
    expect(await identities(b.page, wb.id)).toEqual(identitiesB)
    expect(await members(b.page, wb.id)).toEqual(membersB)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary foreign resource paths reject conflicting workspace context', async ({ browser }) => {
  const ownerA = await account('cpa')
  const ownerB = await account('cpb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-path-a')
    const wb = await workspace(b.page, 'canary-path-b')
    const projectMembers = await api(a.page, `/projects/${wb.id}/members`, 'GET', undefined, wa.id)
    const identityList = await api(a.page, `/workspaces/${wb.id}/agent-identities`, 'GET', undefined, wa.id)
    expect([403, 404]).toContain(projectMembers.status())
    expect([403, 404]).toContain(identityList.status())
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary environment CRUD remains isolated to its workspace', async ({ browser }) => {
  const ownerA = await account('cea')
  const ownerB = await account('ceb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-env-a')
    const wb = await workspace(b.page, 'canary-env-b')
    const before = await environments(b.page, wb.id)
    const created = await api(b.page, '/environments', 'POST', { name: `${prefix}-canary-env` }, wb.id)
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment
    try {
      expect((await environments(b.page, wb.id)).some(row => row.id === environment.id)).toBe(true)
      expect((await environments(a.page, wa.id)).some(row => row.id === environment.id)).toBe(false)
      const foreignUpdate = await api(a.page, `/environments/${environment.id}`, 'PATCH', {
        allowed_hosts: ['example.invalid'],
      }, wa.id)
      expect(foreignUpdate.status()).toBe(404)
    } finally {
      expect((await api(b.page, `/environments/${environment.id}`, 'DELETE', undefined, wb.id)).status()).toBe(204)
    }
    expect(await environments(b.page, wb.id)).toEqual(before)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary identity creation rejects an environment from another workspace', async ({ browser }) => {
  const ownerA = await account('cra')
  const ownerB = await account('crb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-ref-a')
    const wb = await workspace(b.page, 'canary-ref-b')
    const before = await identities(a.page, wa.id)
    const created = await api(b.page, '/environments', 'POST', { name: `${prefix}-foreign-env` }, wb.id)
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment
    try {
      const rejected = await api(a.page, `/workspaces/${wa.id}/agent-identities`, 'POST', {
        name: `${prefix}-must-not-exist`, environment_id: environment.id,
      }, wa.id)
      expect(rejected.status()).toBe(404)
      expect(await identities(a.page, wa.id)).toEqual(before)
    } finally {
      expect((await api(b.page, `/environments/${environment.id}`, 'DELETE', undefined, wb.id)).status()).toBe(204)
    }
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary run-token lookup rejects an identity from another workspace', async ({ browser }) => {
  const ownerA = await account('cta')
  const ownerB = await account('ctb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-token-a')
    const wb = await workspace(b.page, 'canary-token-b')
    const before = await identities(b.page, wb.id)
    const created = await api(b.page, `/workspaces/${wb.id}/agent-identities`, 'POST', {
      name: `${prefix}-foreign-identity`,
    }, wb.id)
    expect(created.status()).toBe(201)
    const identity = await created.json() as Identity
    try {
      const rejected = await api(
        a.page,
        `/workspaces/${wa.id}/agent-identities/${identity.id}/run-tokens`,
        'GET',
        undefined,
        wa.id,
      )
      expect(rejected.status()).toBe(404)
    } finally {
      expect((await api(
        b.page,
        `/workspaces/${wb.id}/agent-identities/${identity.id}`,
        'DELETE',
        undefined,
        wb.id,
      )).status()).toBe(204)
    }
    expect(await identities(b.page, wb.id)).toEqual(before)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary refresh tokens rotate and reject replay', async ({ browser }) => {
  const owner = await account('rpa')
  const member = await account('rpb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, owner); contexts.push(a.context)
    const m = await login(browser, member); contexts.push(m.context)
    const ws = await workspace(a.page, 'canary-replay')
    expect((await api(a.page, `/projects/${ws.id}/members`, 'POST', {
      clerk_user_id: member.id, role: 'developer',
    }, ws.id)).status()).toBe(201)
    try {
      const issued = await exchange(m.page, ws.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      const rotated = await m.page.request.post(`${base}/api/oauth/token`, { form: {
        grant_type: 'refresh_token', refresh_token: pair.refresh_token,
      } })
      expect(rotated.status()).toBe(200)
      const rotatedPair = await rotated.json()
      expect(rotatedPair.refresh_token).not.toBe(pair.refresh_token)
      const replay = await m.page.request.post(`${base}/api/oauth/token`, { form: {
        grant_type: 'refresh_token', refresh_token: pair.refresh_token,
      } })
      expect([401, 403]).toContain(replay.status())
    } finally {
      await api(a.page, `/projects/${ws.id}/members/${member.id}`, 'DELETE', undefined, ws.id)
    }
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary member removal revokes existing access, refresh, and issuance', async ({ browser }) => {
  const owner = await account('rva')
  const member = await account('rvb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, owner); contexts.push(a.context)
    const m = await login(browser, member); contexts.push(m.context)
    const ws = await workspace(a.page, 'canary-revoke')
    expect((await api(a.page, `/projects/${ws.id}/members`, 'POST', {
      clerk_user_id: member.id, role: 'developer',
    }, ws.id)).status()).toBe(201)
    const issued = await exchange(m.page, ws.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()
    expect((await m.page.request.post(`${base}/api/guard/mcp?workspace_id=${ws.id}`, {
      headers: { Authorization: `Bearer ${pair.access_token}` },
      data: { jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} },
    })).status()).toBe(200)

    expect((await api(a.page, `/projects/${ws.id}/members/${member.id}`, 'DELETE', undefined, ws.id)).status()).toBe(204)
    const oldAccess = await m.page.request.post(`${base}/api/guard/mcp?workspace_id=${ws.id}`, {
      headers: { Authorization: `Bearer ${pair.access_token}` },
      data: { jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} },
    })
    const oldRefresh = await m.page.request.post(`${base}/api/oauth/token`, { form: {
      grant_type: 'refresh_token', refresh_token: pair.refresh_token,
    } })
    expect([401, 403]).toContain(oldAccess.status())
    expect([401, 403]).toContain(oldRefresh.status())
    expect((await exchange(m.page, ws.id)).status()).toBe(403)
    expect((await members(a.page, ws.id)).some(row => row.clerk_user_id === member.id)).toBe(false)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary Codex Flight Recorder persists correlated pre/post events', async ({ browser }) => {
  const owner = await account('frc')
  const session = await login(browser, owner)
  try {
    const ws = await workspace(session.page, 'canary-flight-recorder')
    const issued = await exchange(session.page, ws.id)
    expect(issued.status()).toBe(200)
    const { access_token: accessToken } = await issued.json() as { access_token: string }
    const hookSessionId = `canary-${randomBytes(12).toString('hex')}`
    const common = {
      workspace_id: ws.id,
      ai_tool: 'codex-desktop',
      tool_call: 'read',
      decision: 'allowed',
      session_id: hookSessionId,
      hook_session_id: hookSessionId,
    }
    expect((await guardEvent(session.page, accessToken, common)).status()).toBe(201)
    expect((await guardEvent(session.page, accessToken, {
      ...common,
      execution_status: 'success',
      result_summary: 'canary complete',
    })).status()).toBe(201)

    const listed = await session.page.request.get(`${base}/api/guard/events?workspace_id=${ws.id}&limit=50`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    expect(listed.status()).toBe(200)
    const rows = await listed.json() as Array<Record<string, unknown>>
    const pair = rows.filter(row => row.hook_session_id === hookSessionId)
    expect(pair).toHaveLength(2)
    expect(pair.every(row => row.ai_tool === 'codex-desktop')).toBe(true)
    expect(pair.some(row => row.execution_status === 'success')).toBe(true)
  } finally { await session.context.close() }
})
