// Security journeys: ingress smoke, signup/login baseline, onboarding and workspace boundaries.
import { randomBytes } from "node:crypto"
import { test, expect, type BrowserContext } from "@playwright/test"
import { setupClerkTestingToken } from "@clerk/testing/playwright"
import {
  type Workspace,
  createdUsers,
  attemptedEmails,
  prefix,
  base,
  account,
  login,
  verifyCode,
  finishClerkOnboarding,
  api,
  workspace,
  projects,
  expectRole,
  members,
  exchange,
  expectUsableToken,
  signOut,
  openWorkspaceMenu,
  switchWorkspace,
  registerJourneyHooks,
} from "./support/journeys"

registerJourneyHooks()

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
