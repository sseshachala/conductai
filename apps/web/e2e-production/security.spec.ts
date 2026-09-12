import { randomUUID } from "node:crypto"
import { expect, test, type APIResponse, type Browser, type BrowserContext, type Page } from "@playwright/test"

type Account = { email: string; password: string }
type Session = { context: BrowserContext; page: Page; userId: string }
type Workspace = { id: string; name: string; owner_id: string }
type Member = { clerk_user_id: string; role: string }
type Identity = { id: string; name: string }
type Environment = { id: string; name: string }

const apiBase = "https://api.conductai.ai"
const accountA = (): Account => ({
  email: process.env.PROD_E2E_A_EMAIL!,
  password: process.env.PROD_E2E_A_PASSWORD!,
})
const accountB = (): Account => ({
  email: process.env.PROD_E2E_B_EMAIL!,
  password: process.env.PROD_E2E_B_PASSWORD!,
})

async function login(browser: Browser, account: Account, label: "A" | "B"): Promise<Session> {
  const context = await browser.newContext({ baseURL: "https://app.conductai.ai" })
  const page = await context.newPage()
  let stage = "open-sign-in"
  const authStatuses: { operation: string; status: number }[] = []
  page.on("response", response => {
    const url = new URL(response.url())
    if (!url.hostname.includes("clerk")) return
    const operation = url.pathname.split("/").filter(Boolean).at(-1) ?? "unknown"
    authStatuses.push({
      operation: operation.replace(/^(?:client|sess|sia|user|org)_[A-Za-z0-9]+$/, ":id"),
      status: response.status(),
    })
  })
  try {
    await page.goto("/sign-in")
    stage = "submit-email"
    await page.getByLabel(/email address/i).fill(account.email)
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    stage = "submit-password"
    await page.locator('input[name="password"]').fill(account.password)
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    stage = "await-active-session"
    if (await page.locator('input[autocomplete="one-time-code"]').isVisible({ timeout: 10_000 }).catch(() => false)) {
      console.log(`Enter the Clerk verification code for production test account ${label} in the browser`)
    }
    await expect.poll(
      () => page.evaluate(() => ({
        userId: (window as any).Clerk?.user?.id ?? null,
        status: (window as any).Clerk?.session?.status ?? null,
      })).catch(() => null),
      { timeout: 120_000, message: "Dedicated production account must reach an active Clerk session" },
    ).toMatchObject({ status: "active" })
    const userId = await page.evaluate(() => (window as any).Clerk.user.id as string)
    return { context, page, userId }
  } catch {
    const state = await page.evaluate(() => ({
      path: location.pathname,
      sessionStatus: (window as any).Clerk?.session?.status ?? null,
      passwordVisible: Boolean(document.querySelector('input[name="password"]')),
      verificationVisible: Boolean(document.querySelector('input[autocomplete="one-time-code"]')),
    })).catch(() => null)
    await context.close().catch(() => {})
    throw new Error(`Production test-account login failed at ${stage}; ${JSON.stringify({ state, authStatuses })}`)
  }
}

async function jwt(page: Page): Promise<string> {
  const token = await page.evaluate(async () => {
    const clerk = (window as any).Clerk
    return clerk?.session?.getToken ? clerk.session.getToken() : null
  })
  if (!token) throw new Error("Production Clerk session did not issue a token")
  return token
}

async function api(page: Page, path: string, method = "GET", body?: unknown, workspaceId?: string) {
  return page.request.fetch(`${apiBase}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${await jwt(page)}`,
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
    },
    data: body,
  })
}

async function ownedWorkspace(session: Session): Promise<Workspace> {
  const response = await api(session.page, "/projects")
  expect(response.status()).toBe(200)
  const projects = await response.json() as Workspace[]
  const owned = projects.filter(project => project.owner_id === session.userId)
  if (owned.length !== 1) {
    throw new Error("Each production test account must own exactly one disposable workspace")
  }
  return owned[0]
}

async function members(page: Page, workspaceId: string): Promise<Member[]> {
  const response = await api(page, `/projects/${workspaceId}/members`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Member[])
    .map(({ clerk_user_id, role }) => ({ clerk_user_id, role }))
    .sort((a, b) => a.clerk_user_id.localeCompare(b.clerk_user_id))
}

async function identities(page: Page, workspaceId: string): Promise<Identity[]> {
  const response = await api(page, `/workspaces/${workspaceId}/agent-identities`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Identity[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function removeIdentity(page: Page, workspaceId: string, identityId: string): Promise<void> {
  const response = await api(
    page,
    `/workspaces/${workspaceId}/agent-identities/${identityId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

async function removeStaleCanaryIdentities(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-(?:must-not-exist|foreign-identity)$/
  const stale = (await identities(page, workspaceId)).filter(identity => staleName.test(identity.name))
  for (const identity of stale) await removeIdentity(page, workspaceId, identity.id)
}

async function exchange(page: Page, workspaceId: string) {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
    subject_token: await jwt(page),
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    resource: workspaceId,
  } })
}

async function environments(page: Page, workspaceId: string): Promise<Environment[]> {
  const response = await api(page, "/environments", "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Environment[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function addMember(owner: Session, workspaceId: string, userId: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members`,
    "POST",
    { clerk_user_id: userId, role: "developer" },
    workspaceId,
  )
  expect(response.status()).toBe(201)
}

async function removeMember(owner: Session, workspaceId: string, userId: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members/${userId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

async function refresh(page: Page, refreshToken: string): Promise<APIResponse> {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  } })
}

async function mcp(page: Page, workspaceId: string, accessToken: string): Promise<APIResponse> {
  return page.request.post(`${apiBase}/guard/mcp?workspace_id=${workspaceId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} },
  })
}

type Harness = {
  a: Session
  b: Session
  workspaceA: Workspace
  workspaceB: Workspace
  originalMembersB: Member[]
}

test.describe("bounded production security canaries", () => {
  let harness: Harness
  const runPrefix = `prod-e2e-${randomUUID().slice(0, 8)}`

  test.beforeAll(async ({ browser }) => {
    const sessions: Session[] = []
    try {
      const a = await login(browser, accountA(), "A"); sessions.push(a)
      const b = await login(browser, accountB(), "B"); sessions.push(b)
      if (a.userId === b.userId) throw new Error("Production test accounts must be distinct")

      const workspaceA = await ownedWorkspace(a)
      const workspaceB = await ownedWorkspace(b)
      if (workspaceA.id === workspaceB.id) throw new Error("Production test workspaces must be distinct")

      await removeStaleCanaryIdentities(a.page, workspaceA.id)
      await removeStaleCanaryIdentities(b.page, workspaceB.id)

      const originalMembersB = await members(b.page, workspaceB.id)
      if (originalMembersB.some(member => member.clerk_user_id === a.userId)) {
        throw new Error("Account A must begin outside account B's disposable workspace")
      }
      harness = { a, b, workspaceA, workspaceB, originalMembersB }
    } catch (error) {
      await Promise.all(sessions.map(session => session.context.close().catch(() => {})))
      throw error
    }
  })

  test.afterAll(async () => {
    if (!harness) return
    const { a, b, workspaceB, originalMembersB } = harness
    try {
      const current = await members(b.page, workspaceB.id).catch(() => [])
      if (!originalMembersB.some(member => member.clerk_user_id === a.userId)
          && current.some(member => member.clerk_user_id === a.userId)) {
        await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
      }
    } finally {
      await Promise.all([a.context.close().catch(() => {}), b.context.close().catch(() => {})])
    }
  })

  test("@prod account ownership and disposable workspace preflight", async () => {
    const { a, b, workspaceA, workspaceB, originalMembersB } = harness
    expect(a.userId).not.toBe(b.userId)
    expect(workspaceA.id).not.toBe(workspaceB.id)
    expect(workspaceA.owner_id).toBe(a.userId)
    expect(workspaceB.owner_id).toBe(b.userId)
    expect(originalMembersB.some(member => member.clerk_user_id === a.userId)).toBe(false)
  })

  test("@prod anonymous and forged forwarding headers do not authenticate", async () => {
    const { a, workspaceA } = harness
    const response = await a.page.request.get(`${apiBase}/projects`, {
      headers: {
        "X-Workspace-Id": workspaceA.id,
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
        "X-Forwarded-Proto": "https",
      },
    })
    expect(response.status()).toBe(401)
  })

  test("@prod owner token can list MCP tools in its workspace", async () => {
    const { a, workspaceA } = harness
    const issued = await exchange(a.page, workspaceA.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()
    expect(typeof pair.access_token === "string" && pair.access_token.startsWith("cond_agt_")).toBe(true)

    const response = await mcp(a.page, workspaceA.id, pair.access_token)
    expect(response.status()).toBe(200)
    expect(Array.isArray((await response.json()).result?.tools)).toBe(true)
  })

  test("@prod foreign and unknown workspaces cannot issue credentials", async () => {
    const { a, b, workspaceA, workspaceB, originalMembersB } = harness
    const identitiesABefore = await identities(a.page, workspaceA.id)
    const identitiesBBefore = await identities(b.page, workspaceB.id)

    expect((await exchange(a.page, workspaceB.id)).status()).toBe(403)
    expect((await exchange(a.page, randomUUID())).status()).toBe(403)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
    expect(await identities(a.page, workspaceA.id)).toEqual(identitiesABefore)
    expect(await identities(b.page, workspaceB.id)).toEqual(identitiesBBefore)
  })

  test("@prod foreign project and identity paths reject conflicting workspace context", async () => {
    const { a, workspaceA, workspaceB } = harness
    const projectMembers = await api(
      a.page,
      `/projects/${workspaceB.id}/members`,
      "GET",
      undefined,
      workspaceA.id,
    )
    expect([403, 404]).toContain(projectMembers.status())

    const identityList = await api(
      a.page,
      `/workspaces/${workspaceB.id}/agent-identities`,
      "GET",
      undefined,
      workspaceA.id,
    )
    expect([403, 404]).toContain(identityList.status())
  })

  test("@prod environment CRUD remains isolated to its workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await environments(b.page, workspaceB.id)
    const created = await api(
      b.page,
      "/environments",
      "POST",
      { name: `${runPrefix}-environment` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment

    try {
      expect((await environments(b.page, workspaceB.id)).some(row => row.id === environment.id)).toBe(true)
      expect((await environments(a.page, workspaceA.id)).some(row => row.id === environment.id)).toBe(false)

      const foreignUpdate = await api(
        a.page,
        `/environments/${environment.id}`,
        "PATCH",
        { allowed_hosts: ["example.invalid"] },
        workspaceA.id,
      )
      expect(foreignUpdate.status()).toBe(404)
    } finally {
      const removed = await api(b.page, `/environments/${environment.id}`, "DELETE", undefined, workspaceB.id)
      expect(removed.status()).toBe(204)
    }
    expect(await environments(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod identity creation rejects an environment from another workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const identitiesBefore = await identities(a.page, workspaceA.id)
    const created = await api(
      b.page,
      "/environments",
      "POST",
      { name: `${runPrefix}-foreign-environment` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment
    let unexpectedIdentityId: string | undefined

    try {
      const rejected = await api(
        a.page,
        `/workspaces/${workspaceA.id}/agent-identities`,
        "POST",
        { name: `${runPrefix}-must-not-exist`, environment_id: environment.id },
        workspaceA.id,
      )
      if (rejected.status() === 201) {
        unexpectedIdentityId = (await rejected.json() as Identity).id
      }
      expect(rejected.status()).toBe(404)
      expect(await identities(a.page, workspaceA.id)).toEqual(identitiesBefore)
    } finally {
      if (unexpectedIdentityId) {
        await removeIdentity(a.page, workspaceA.id, unexpectedIdentityId)
      }
      const removed = await api(b.page, `/environments/${environment.id}`, "DELETE", undefined, workspaceB.id)
      expect(removed.status()).toBe(204)
    }
  })

  test("@prod run-token lookup rejects an identity from another workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await identities(b.page, workspaceB.id)
    const created = await api(
      b.page,
      `/workspaces/${workspaceB.id}/agent-identities`,
      "POST",
      { name: `${runPrefix}-foreign-identity` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const identity = await created.json() as Identity

    try {
      const rejected = await api(
        a.page,
        `/workspaces/${workspaceA.id}/agent-identities/${identity.id}/run-tokens`,
        "GET",
        undefined,
        workspaceA.id,
      )
      expect(rejected.status()).toBe(404)
    } finally {
      await removeIdentity(b.page, workspaceB.id, identity.id)
    }
    expect(await identities(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod refresh tokens rotate and reject replay", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    await addMember(b, workspaceB.id, a.userId)
    try {
      const issued = await exchange(a.page, workspaceB.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      expect(typeof pair.refresh_token === "string" && pair.refresh_token.startsWith("cond_ref_")).toBe(true)

      const rotated = await refresh(a.page, pair.refresh_token)
      expect(rotated.status()).toBe(200)
      const rotatedPair = await rotated.json()
      expect(typeof rotatedPair.refresh_token === "string" && rotatedPair.refresh_token.startsWith("cond_ref_")).toBe(true)
      expect(rotatedPair.refresh_token).not.toBe(pair.refresh_token)

      const replay = await refresh(a.page, pair.refresh_token)
      expect([401, 403]).toContain(replay.status())
    } finally {
      await removeMember(b, workspaceB.id, a.userId)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod member removal revokes access, refresh, and new issuance", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    await addMember(b, workspaceB.id, a.userId)
    let removed = false
    try {
      const issued = await exchange(a.page, workspaceB.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      expect((await mcp(a.page, workspaceB.id, pair.access_token)).status()).toBe(200)

      await removeMember(b, workspaceB.id, a.userId)
      removed = true
      expect([401, 403]).toContain((await mcp(a.page, workspaceB.id, pair.access_token)).status())
      expect([401, 403]).toContain((await refresh(a.page, pair.refresh_token)).status())
      expect((await exchange(a.page, workspaceB.id)).status()).toBe(403)
    } finally {
      if (!removed) await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })
})
